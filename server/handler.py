"""ctxhub — the remote half of ctx.

Stores contexts as versioned markdown. Deliberately model-free: the server does
storage, a keyed merge, and version history. Nothing here needs inference.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid

import boto3
from boto3.dynamodb.conditions import Key

TABLE = os.environ.get("CTX_TABLE", "ctx")
SECRET = os.environ.get("CTX_JWT_SECRET", "dev-only-change-me").encode()
TTL = 60 * 60 * 24 * 30  # 30 days

ddb = boto3.resource("dynamodb")
tbl = ddb.Table(TABLE)

FACT_RE = re.compile(r"^\s*-\s+\*\*(?P<key>[^*]+)\*\*\s*[—→-]\s*(?P<value>.*)$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
GENERIC = {"src", "app", "api", "web", "lib", "code", "work", "dev", "test",
           "tmp", "project", "repo", "main", "new", "untitled", "workspace"}


# ------------------------------------------------------------------- helpers

def b64u(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def b64u_dec(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(email, org):
    body = {"sub": email, "org": org, "exp": int(time.time()) + TTL}
    head = b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64u(json.dumps(body).encode())
    sig = b64u(hmac.new(SECRET, f"{head}.{payload}".encode(), hashlib.sha256).digest())
    return f"{head}.{payload}.{sig}"


def read_token(token):
    try:
        head, payload, sig = token.split(".")
    except ValueError:
        return None
    want = b64u(hmac.new(SECRET, f"{head}.{payload}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, want):
        return None
    body = json.loads(b64u_dec(payload))
    if body.get("exp", 0) < time.time():
        return None
    return body


def hash_pw(password, salt=None):
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{b64u(salt)}${b64u(dk)}"


def check_pw(password, stored):
    try:
        salt_b64, _ = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_pw(password, b64u_dec(salt_b64)), stored)


def parse_facts(text):
    """{key: block}. A block is the fact line plus indented continuations."""
    facts, key, block = {}, None, []

    def flush():
        if key is not None:
            facts[key] = "\n".join(block).rstrip()

    for line in (text or "").splitlines():
        m = FACT_RE.match(line)
        if m:
            flush()
            key, block = m.group("key").strip(), [line.rstrip()]
        elif key is not None and line.strip() and line[:1].isspace():
            block.append(line.rstrip())
        else:
            flush()
            key, block = None, []
    flush()
    return facts


def apply_changes(text, changes):
    """Later wins, per key. Never a whole-file replacement."""
    facts = parse_facts(text)
    body = text or ""
    for ch in changes:
        key, op, block = ch.get("key"), ch.get("op"), ch.get("block", "")
        if not key:
            continue
        if op == "delete":
            if key in facts:
                body = body.replace(facts[key] + "\n", "", 1).replace(facts[key], "", 1)
                facts.pop(key)
        elif key in facts:
            body = body.replace(facts[key], block, 1)
            facts[key] = block
        else:
            body = body.rstrip() + "\n" + block + "\n"
            facts[key] = block
    return body.rstrip() + "\n"


def resp(code, body):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body),
    }


def err(code, message):
    return resp(code, {"error": message})


# ------------------------------------------------------------------- storage

def get_context(org, name):
    r = tbl.get_item(Key={"pk": f"ORG#{org}", "sk": f"CTX#{name}"})
    return r.get("Item")


def put_version(org, name, facts, version, by):
    tbl.put_item(Item={
        "pk": f"CTX#{org}#{name}", "sk": f"V#{version:09d}",
        "facts": facts, "by": by, "at": int(time.time()), "version": version,
    })


# -------------------------------------------------------------------- routes

def register(body):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    org = (body.get("org") or "").strip().lower()
    if not email or "@" not in email:
        return err(400, "a real email, please")
    if len(password) < 8:
        return err(400, "password needs at least 8 characters")
    if not NAME_RE.match(org):
        return err(400, "org must be 3-40 chars, lowercase letters, digits and dashes")

    if tbl.get_item(Key={"pk": f"USER#{email}", "sk": "PROFILE"}).get("Item"):
        return err(409, "that email is already registered — log in instead")

    existing = tbl.get_item(Key={"pk": f"ORG#{org}", "sk": "META"}).get("Item")
    if existing:
        return err(409, f"org `{org}` is taken")

    tbl.put_item(Item={"pk": f"USER#{email}", "sk": "PROFILE",
                       "pw": hash_pw(password), "org": org,
                       "created": int(time.time())})
    tbl.put_item(Item={"pk": f"ORG#{org}", "sk": "META",
                       "owner": email, "created": int(time.time())})
    return resp(200, {"token": make_token(email, org), "org": org, "email": email})


def login(body):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    item = tbl.get_item(Key={"pk": f"USER#{email}", "sk": "PROFILE"}).get("Item")
    if not item or not check_pw(password, item["pw"]):
        return err(401, "email or password is wrong")
    return resp(200, {"token": make_token(email, item["org"]),
                      "org": item["org"], "email": email})


def create_context(claims, body):
    org = claims["org"]
    name = (body.get("name") or "").strip().lower()
    if not NAME_RE.match(name):
        return err(400, "name must be 3-40 chars, lowercase letters, digits and dashes")
    if name in GENERIC:
        return err(400, f"`{name}` is too generic to claim")
    if get_context(org, name):
        return err(409, f"{org}:{name} already exists")

    facts = body.get("facts") or ""
    now = int(time.time())
    tbl.put_item(Item={"pk": f"ORG#{org}", "sk": f"CTX#{name}",
                       "name": name, "org": org, "facts": facts,
                       "version": 1, "updated": now, "created": now,
                       "owner": claims["sub"]})
    put_version(org, name, facts, 1, claims["sub"])
    return resp(200, {"org": org, "name": name, "version": 1})


def read_context(org, name):
    item = get_context(org, name)
    if not item:
        return err(404, f"{org}:{name} not found")
    facts = item.get("facts", "")
    return resp(200, {"org": org, "name": name, "facts": facts,
                      "version": int(item.get("version", 0)),
                      "count": len(parse_facts(facts)),
                      "requires": item.get("requires", [])})


def sync_context(claims, org, name, body):
    if claims["org"] != org:
        return err(403, "not your org")
    item = get_context(org, name)
    if not item:
        return err(404, f"{org}:{name} not found")

    server_facts = item.get("facts", "")
    server_version = int(item.get("version", 0))
    client_version = int(body.get("version", 0))
    changes = body.get("changes") or []

    updated = apply_changes(server_facts, changes) if changes else server_facts
    version = server_version
    if updated != server_facts:
        version = server_version + 1
        now = int(time.time())
        tbl.update_item(
            Key={"pk": f"ORG#{org}", "sk": f"CTX#{name}"},
            UpdateExpression="SET facts=:f, version=:v, updated=:u",
            ExpressionAttributeValues={":f": updated, ":v": version, ":u": now},
        )
        put_version(org, name, updated, version, claims["sub"])

    # hand back only what the client is behind on
    down = {}
    if client_version < server_version:
        mine = parse_facts(updated)
        theirs = parse_facts(apply_changes("", changes)) if changes else {}
        down = {k: v for k, v in mine.items() if theirs.get(k) != v}

    return resp(200, {"version": version, "facts": down})


def list_contexts(claims, org):
    if claims["org"] != org:
        return err(403, "not your org")
    r = tbl.query(KeyConditionExpression=Key("pk").eq(f"ORG#{org}")
                  & Key("sk").begins_with("CTX#"))
    out = []
    for it in r.get("Items", []):
        out.append({"name": it["name"], "version": int(it.get("version", 0)),
                    "facts": len(parse_facts(it.get("facts", ""))),
                    "updated": int(it.get("updated", 0)),
                    "owner": it.get("owner", "")})
    return resp(200, {"org": org, "contexts": sorted(out, key=lambda c: c["name"])})


def list_versions(claims, org, name):
    if claims["org"] != org:
        return err(403, "not your org")
    r = tbl.query(KeyConditionExpression=Key("pk").eq(f"CTX#{org}#{name}")
                  & Key("sk").begins_with("V#"),
                  ScanIndexForward=False, Limit=50)
    return resp(200, {"versions": [
        {"version": int(i["version"]), "by": i.get("by", ""), "at": int(i.get("at", 0)),
         "facts": len(parse_facts(i.get("facts", "")))}
        for i in r.get("Items", [])]})


def revert(claims, org, name, body):
    if claims["org"] != org:
        return err(403, "not your org")
    want = int(body.get("version", 0))
    r = tbl.get_item(Key={"pk": f"CTX#{org}#{name}", "sk": f"V#{want:09d}"})
    old = r.get("Item")
    if not old:
        return err(404, f"no version {want}")
    item = get_context(org, name)
    version = int(item.get("version", 0)) + 1
    now = int(time.time())
    tbl.update_item(
        Key={"pk": f"ORG#{org}", "sk": f"CTX#{name}"},
        UpdateExpression="SET facts=:f, version=:v, updated=:u",
        ExpressionAttributeValues={":f": old["facts"], ":v": version, ":u": now},
    )
    put_version(org, name, old["facts"], version, claims["sub"])
    return resp(200, {"version": version, "reverted_to": want})


# ------------------------------------------------------------------ dispatch

def handler(event, _context=None):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")
    if method == "OPTIONS":
        return resp(200, {})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return err(400, "body is not JSON")

    auth = (event.get("headers") or {}).get("authorization", "")
    claims = read_token(auth[7:]) if auth.lower().startswith("bearer ") else None

    parts = [p for p in path.split("/") if p]          # v1, ...
    if not parts or parts[0] != "v1":
        return err(404, "no such route")
    parts = parts[1:]

    try:
        if parts == ["auth", "register"] and method == "POST":
            return register(body)
        if parts == ["auth", "login"] and method == "POST":
            return login(body)
        if parts == ["me"] and method == "GET":
            return err(401, "log in") if not claims else resp(200, claims)

        if parts == ["contexts"] and method == "POST":
            return err(401, "log in") if not claims else create_context(claims, body)

        if len(parts) == 3 and parts[0] == "orgs" and parts[2] == "contexts":
            return err(401, "log in") if not claims else list_contexts(claims, parts[1])

        if len(parts) == 3 and parts[0] == "contexts" and method == "GET":
            return read_context(parts[1], parts[2])

        if len(parts) == 4 and parts[0] == "contexts":
            org, name, action = parts[1], parts[2], parts[3]
            if not claims:
                return err(401, "log in")
            if action == "sync" and method == "POST":
                return sync_context(claims, org, name, body)
            if action == "versions" and method == "GET":
                return list_versions(claims, org, name)
            if action == "revert" and method == "POST":
                return revert(claims, org, name, body)
    except Exception as e:                                   # noqa: BLE001
        print("error:", repr(e))
        return err(500, "server error")

    return err(404, "no such route")
