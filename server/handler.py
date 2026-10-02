"""ctxhub — the remote half of ctx.

Stores contexts as facts, each a value with the time it last changed, and keeps
every version. Merging is one rule, applied the same here and in the CLI: for
every fact, the most recent change wins. Deliberately model-free.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid

TABLE = os.environ.get("CTX_TABLE", "ctx")
SECRET = os.environ.get("CTX_JWT_SECRET", "dev-only-change-me").encode()
TTL = 60 * 60 * 24 * 30  # 30 days

# The storage is DynamoDB on Lambda. Anywhere else, whoever imports this sets
# `tbl` and `Key`: serve.py to SQLite, the tests to memory. So self-hosting
# needs no boto3, and no AWS account.
tbl = Key = None
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    import boto3
    from boto3.dynamodb.conditions import Key
    tbl = boto3.resource("dynamodb").Table(TABLE)

FULL_KEY_RE = re.compile(r"^[a-z0-9-]+\.[a-z0-9][a-z0-9._-]{0,120}$")
STAMP_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
MAX_FACTS = 5000
MAX_VALUE = 4000
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
# Shapes that are only ever credentials. Mechanical on purpose: no model, and
# nothing that fires on the word "password" in a sentence about passwords.
SECRETS = [
    ("an AWS access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("an API key", re.compile(r"\bsk-(ant-|proj-|live-)?[A-Za-z0-9_-]{20,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("a Stripe key", re.compile(r"\b(sk|rk)_live_[0-9A-Za-z]{20,}")),
]
GENERIC = {"src", "app", "api", "web", "lib", "code", "work", "dev", "test",
           "tmp", "project", "repo", "main", "new", "untitled", "workspace"}


# ------------------------------------------------------------------- helpers

def b64u(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def b64u_dec(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(email):
    # identity only. which orgs you're in is looked up per request, so being
    # added to or removed from an org takes effect without logging in again.
    body = {"sub": email, "exp": int(time.time()) + TTL}
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


def stamp():
    """UTC, fixed width, so comparing the strings compares the times."""
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t % 1 * 1000):03d}Z"


def newer(a, b):
    """The more recent of two versions of one fact — the CLI's rule exactly, ties
    included, so every copy settles on the same answer."""
    if a is None or b is None:
        return a or b
    ka = (a.get("updated", ""), a.get("removed", False), a.get("value", ""))
    kb = (b.get("updated", ""), b.get("removed", False), b.get("value", ""))
    return a if ka >= kb else b


def live(facts):
    return {k: f for k, f in facts.items() if not f.get("removed")}


def check_facts(facts):
    """-> an error message, or None. Every fact a client sends is checked."""
    if not isinstance(facts, dict):
        return "send the facts as {\"category.key\": {value, updated, removed}}"
    if len(facts) > MAX_FACTS:
        return f"a context holds at most {MAX_FACTS} facts"
    for k, f in facts.items():
        if not FULL_KEY_RE.match(k):
            return f"`{k}` isn't a key — it should look like category.key"
        if not isinstance(f, dict) or not isinstance(f.get("value"), str) \
                or not isinstance(f.get("removed", False), bool) \
                or not STAMP_RE.match(str(f.get("updated", ""))):
            return f"`{k}` needs a value, an updated time and whether it was removed"
        if len(f["value"]) > MAX_VALUE:
            return f"`{k}` is longer than {MAX_VALUE} characters"
        if not f.get("removed"):
            what = find_secret(f["value"])
            if what:
                return (f"`{k}` looks like it contains {what} — secrets never go in a "
                        "context. Nothing was stored.")
    return None


def clean(f):
    return {"value": f["value"], "updated": f["updated"], "removed": bool(f.get("removed"))}


def find_secret(text):
    for what, rx in SECRETS:
        if rx.search(text or ""):
            return what
    return None


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
#
# The facts are stored as one JSON string, the same in DynamoDB and SQLite.
# Every change is also kept as a version, for the history and revert.

def get_context(org, name):
    r = tbl.get_item(Key={"pk": f"ORG#{org}", "sk": f"CTX#{name}"})
    return r.get("Item")


def facts_of(item):
    try:
        return json.loads(item.get("facts") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def put_version(org, name, facts, version, by):
    tbl.put_item(Item={
        "pk": f"CTX#{org}#{name}", "sk": f"V#{version:09d}",
        "facts": json.dumps(facts), "by": by, "at": int(time.time()), "version": version,
    })


def save(org, name, item, facts, by):
    """Store a changed set of facts as the next version. -> the version."""
    version = int(item.get("version", 0)) + 1
    tbl.update_item(
        Key={"pk": f"ORG#{org}", "sk": f"CTX#{name}"},
        UpdateExpression="SET facts=:f, version=:v, updated=:u",
        ExpressionAttributeValues={":f": json.dumps(facts), ":v": version,
                                   ":u": int(time.time())},
    )
    put_version(org, name, facts, version, by)
    return version


# ---------------------------------------------------------------- membership
#
# Everyone has an account; not everyone makes an org. An org's admins add people
# by email — before or after that person signs up — and an account can belong
# to several orgs. Inside an org there is one role for contexts: everyone reads,
# everyone writes. "admin" only means you can manage who is in the org.
#
#   ORG#<org>   / MEMBER#<email>   role, added_by, at
#   USER#<email>/ ORG#<org>        role              (the same fact, indexed by user)

def get_user(email):
    return tbl.get_item(Key={"pk": f"USER#{email}", "sk": "PROFILE"}).get("Item")


def get_org(org):
    return tbl.get_item(Key={"pk": f"ORG#{org}", "sk": "META"}).get("Item")


def put_member(org, email, role, by):
    now = int(time.time())
    tbl.put_item(Item={"pk": f"ORG#{org}", "sk": f"MEMBER#{email}",
                       "email": email, "role": role, "added_by": by, "at": now})
    tbl.put_item(Item={"pk": f"USER#{email}", "sk": f"ORG#{org}",
                       "org": org, "role": role})


def role_in(email, org):
    """-> "admin" | "member" | None. An org's owner is always an admin — which
    also covers orgs created before membership rows existed."""
    it = tbl.get_item(Key={"pk": f"ORG#{org}", "sk": f"MEMBER#{email}"}).get("Item")
    if it:
        return it.get("role", "member")
    meta = get_org(org)
    return "admin" if meta and meta.get("owner") == email else None


def orgs_of(email):
    r = tbl.query(KeyConditionExpression=Key("pk").eq(f"USER#{email}")
                  & Key("sk").begins_with("ORG#"))
    out = {it["org"]: it.get("role", "member") for it in r.get("Items", [])}
    legacy = (get_user(email) or {}).get("org")      # accounts from before membership
    if legacy and legacy not in out and role_in(email, legacy):
        out[legacy] = "admin"
    return [{"org": o, "role": out[o]} for o in sorted(out)]


def new_org(email, org):
    if not NAME_RE.match(org):
        return err(400, "org must be 3-40 chars, lowercase letters, digits and dashes")
    if get_org(org):
        return err(409, f"org `{org}` is taken — if it's yours, ask its admin to add you")
    tbl.put_item(Item={"pk": f"ORG#{org}", "sk": "META",
                       "owner": email, "created": int(time.time())})
    put_member(org, email, "admin", email)
    return None


def session(email):
    orgs = orgs_of(email)
    # "org" is for clients from before multiple orgs: they read a single one
    return {"token": make_token(email), "email": email, "orgs": orgs,
            "org": orgs[0]["org"] if orgs else None}


# -------------------------------------------------------------------- routes

def register(body):
    """An account and nothing else. Orgs are made afterwards, signed in."""
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if not email or "@" not in email:
        return err(400, "a real email, please")
    if len(password) < 8:
        return err(400, "password needs at least 8 characters")
    if get_user(email):
        return err(409, "that email is already registered — log in instead")

    tbl.put_item(Item={"pk": f"USER#{email}", "sk": "PROFILE",
                       "pw": hash_pw(password), "created": int(time.time())})
    return resp(200, session(email))


def login(body):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    item = get_user(email)
    if not item or not check_pw(password, item["pw"]):
        return err(401, "email or password is wrong")
    return resp(200, session(email))


def me(claims):
    email = claims["sub"]
    return resp(200, {"email": email, "orgs": orgs_of(email)})


def create_org(claims, body):
    email = claims["sub"]
    org = (body.get("org") or "").strip().lower()
    problem = new_org(email, org)
    return problem or resp(200, {"org": org, "role": "admin", "orgs": orgs_of(email)})


def list_members(claims, org):
    if not role_in(claims["sub"], org):
        return err(403, f"you're not in `{org}`, or it doesn't exist")
    r = tbl.query(KeyConditionExpression=Key("pk").eq(f"ORG#{org}")
                  & Key("sk").begins_with("MEMBER#"))
    owner = (get_org(org) or {}).get("owner")
    rows = {it["email"]: it for it in r.get("Items", [])}
    if owner and owner not in rows:
        rows[owner] = {"email": owner, "role": "admin"}
    out = [{"email": e, "role": it.get("role", "member"), "owner": e == owner,
            "account": bool(get_user(e))} for e, it in rows.items()]
    return resp(200, {"org": org, "members": sorted(out, key=lambda m: m["email"])})


def add_member(claims, org, body):
    if role_in(claims["sub"], org) != "admin":
        return err(403, "only an org admin can add people")
    email = (body.get("email") or "").strip().lower()
    role = body.get("role") or "member"
    if not email or "@" not in email:
        return err(400, "a real email, please")
    if role not in ("admin", "member"):
        return err(400, "role is admin or member")
    # no account needed yet: they see the org as soon as they sign up
    put_member(org, email, role, claims["sub"])
    return list_members(claims, org)


def remove_member(claims, org, body):
    if role_in(claims["sub"], org) != "admin":
        return err(403, "only an org admin can remove people")
    email = (body.get("email") or "").strip().lower()
    if email == (get_org(org) or {}).get("owner"):
        return err(400, "the org's owner can't be removed")
    tbl.delete_item(Key={"pk": f"ORG#{org}", "sk": f"MEMBER#{email}"})
    tbl.delete_item(Key={"pk": f"USER#{email}", "sk": f"ORG#{org}"})
    return list_members(claims, org)


def pick_org(claims, body):
    """The org a new context goes in. Clients from before multiple orgs don't
    send one, which is fine as long as you're only in one."""
    org = (body.get("org") or "").strip().lower()
    if org:
        return org
    mine = orgs_of(claims["sub"])
    return mine[0]["org"] if len(mine) == 1 else None


def create_context(claims, body):
    org = pick_org(claims, body)
    if not org:
        return err(400, "say which org this goes in")
    if not role_in(claims["sub"], org):
        return err(403, f"you're not in `{org}`, or it doesn't exist")
    name = (body.get("name") or "").strip().lower()
    if not NAME_RE.match(name):
        return err(400, "name must be 3-40 chars, lowercase letters, digits and dashes")
    if name in GENERIC:
        return err(400, f"`{name}` is too generic to claim")
    if get_context(org, name):
        return err(409, f"{org}:{name} already exists")

    facts = body.get("facts") or {}
    problem = check_facts(facts)
    if problem:
        return err(400, problem)
    facts = {k: clean(f) for k, f in facts.items()}
    now = int(time.time())
    tbl.put_item(Item={"pk": f"ORG#{org}", "sk": f"CTX#{name}",
                       "name": name, "org": org, "facts": json.dumps(facts),
                       "version": 1, "updated": now, "created": now,
                       "owner": claims["sub"]})
    put_version(org, name, facts, 1, claims["sub"])
    return resp(200, {"org": org, "name": name, "version": 1})


def can_write(email, org, item):
    """For now a context has one writer — whoever created it — plus the org's
    admins. Every other member reads it. Newest-wins already copes with many
    writers (the same owner on two machines is exactly that), so opening writes
    to the whole org later is a permission change, not a rebuild."""
    return item.get("owner") == email or role_in(email, org) == "admin"


def read_context(claims, org, name):
    # a context holds hostnames, access steps and internal names: members only
    if not role_in(claims["sub"], org):
        return err(403, f"you're not in `{org}`, or it doesn't exist")
    item = get_context(org, name)
    if not item:
        return err(404, f"{org}:{name} not found")
    facts = facts_of(item)
    return resp(200, {"org": org, "name": name, "facts": facts,
                      "version": int(item.get("version", 0)),
                      "count": len(live(facts)),
                      "owner": item.get("owner", ""),
                      "can_write": can_write(claims["sub"], org, item)})


def writable_item(claims, org, name):
    """-> (item, None) or (None, error response)."""
    if not role_in(claims["sub"], org):
        return None, err(403, f"you're not in `{org}`, or it doesn't exist")
    item = get_context(org, name)
    if not item:
        return None, err(404, f"{org}:{name} not found")
    if not can_write(claims["sub"], org, item):
        return None, err(403, f"{org}:{name} is read-only for you — its owner and org admins maintain it")
    return item, None


def push_context(claims, org, name, body):
    """Every fact a copy has. Each one replaces the server's only if it is the
    more recent change; the merged whole comes back, so the copy can take in
    whatever others changed. No versions to match, nothing to retry."""
    item, problem = writable_item(claims, org, name)
    if problem:
        return problem
    incoming = body.get("facts")
    problem = check_facts(incoming)
    if problem:
        return err(400, problem)
    facts = facts_of(item)
    accepted = 0
    for k, f in incoming.items():
        f = clean(f)
        if newer(facts.get(k), f) is f and facts.get(k) != f:
            facts[k] = f
            accepted += 1
    version = save(org, name, item, facts, claims["sub"]) if accepted else int(item.get("version", 0))
    return resp(200, {"version": version, "accepted": accepted, "facts": facts})


def edit_fact(claims, org, name, body):
    """One fact, changed or removed by a person in the console. It is stamped
    now, so the next pull on every copy brings it in."""
    item, problem = writable_item(claims, org, name)
    if problem:
        return problem
    key = (body.get("key") or "").strip().lower()
    removed = bool(body.get("removed"))
    facts = facts_of(item)
    value = body.get("value")
    if removed:
        if key not in facts or facts[key].get("removed"):
            return err(404, f"no fact `{key}`")
        value = facts[key]["value"]
    f = {"value": (value or "").strip(), "updated": stamp(), "removed": removed}
    problem = check_facts({key: f})
    if problem:
        return err(400, problem)
    if not removed and not f["value"]:
        return err(400, "a fact needs a value")
    facts[key] = f
    version = save(org, name, item, facts, claims["sub"])
    return resp(200, {"version": version, "facts": facts})


def list_contexts(claims, org):
    if not role_in(claims["sub"], org):
        return err(403, f"you're not in `{org}`, or it doesn't exist")
    r = tbl.query(KeyConditionExpression=Key("pk").eq(f"ORG#{org}")
                  & Key("sk").begins_with("CTX#"))
    out = []
    for it in r.get("Items", []):
        out.append({"name": it["name"], "version": int(it.get("version", 0)),
                    "facts": len(live(facts_of(it))),
                    "updated": int(it.get("updated", 0)),
                    "owner": it.get("owner", ""),
                    "can_write": can_write(claims["sub"], org, it)})
    return resp(200, {"org": org, "contexts": sorted(out, key=lambda c: c["name"])})


def list_versions(claims, org, name):
    if not role_in(claims["sub"], org):
        return err(403, f"you're not in `{org}`, or it doesn't exist")
    r = tbl.query(KeyConditionExpression=Key("pk").eq(f"CTX#{org}#{name}")
                  & Key("sk").begins_with("V#"),
                  ScanIndexForward=False, Limit=50)
    return resp(200, {"versions": [
        {"version": int(i["version"]), "by": i.get("by", ""), "at": int(i.get("at", 0)),
         "facts": len(live(facts_of(i)))}
        for i in r.get("Items", [])]})


def revert(claims, org, name, body):
    if not role_in(claims["sub"], org):
        return err(403, f"you're not in `{org}`, or it doesn't exist")
    if not can_write(claims["sub"], org, get_context(org, name) or {}):
        return err(403, f"{org}:{name} is read-only for you — its owner and org admins maintain it")
    want = int(body.get("version", 0))
    r = tbl.get_item(Key={"pk": f"CTX#{org}#{name}", "sk": f"V#{want:09d}"})
    old = r.get("Item")
    if not old:
        return err(404, f"no version {want}")
    # Putting the old facts back as they were would lose to every copy's newer
    # changes on the next push. So a revert is a new change: every fact that
    # differs from that version is set back to it, stamped now.
    item = get_context(org, name)
    facts, then, t = facts_of(item), facts_of(old), stamp()
    for k in set(facts) | set(then):
        was, cur = then.get(k), facts.get(k)
        want_removed = was is None or was.get("removed", False)
        want_value = (was or cur)["value"]
        if cur and cur.get("removed", False) == want_removed and cur["value"] == want_value:
            continue
        facts[k] = {"value": want_value, "updated": t, "removed": want_removed}
    version = save(org, name, item, facts, claims["sub"])
    return resp(200, {"version": version, "reverted_to": want})


# ------------------------------------------------------------------ dispatch

def handler(event, _context=None):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")
    if method == "OPTIONS":
        return resp(200, {})

    try:
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):     # API Gateway does this for non-JSON content types
            raw = base64.b64decode(raw).decode()
        body = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
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
            return err(401, "log in") if not claims else me(claims)

        if parts == ["orgs"] and method == "POST":
            return err(401, "log in") if not claims else create_org(claims, body)

        if len(parts) >= 3 and parts[0] == "orgs" and parts[2] == "members":
            if not claims:
                return err(401, "log in")
            org = parts[1]
            if len(parts) == 3 and method == "GET":
                return list_members(claims, org)
            if len(parts) == 3 and method == "POST":
                return add_member(claims, org, body)
            if parts[3:] == ["remove"] and method == "POST":
                return remove_member(claims, org, body)

        if parts == ["contexts"] and method == "POST":
            return err(401, "log in") if not claims else create_context(claims, body)

        if len(parts) == 3 and parts[0] == "orgs" and parts[2] == "contexts":
            return err(401, "log in") if not claims else list_contexts(claims, parts[1])

        if len(parts) == 3 and parts[0] == "contexts" and method == "GET":
            return err(401, "log in") if not claims else read_context(claims, parts[1], parts[2])

        if len(parts) == 4 and parts[0] == "contexts":
            org, name, action = parts[1], parts[2], parts[3]
            if not claims:
                return err(401, "log in")
            if action == "push" and method == "POST":
                return push_context(claims, org, name, body)
            if action == "facts" and method == "POST":
                return edit_fact(claims, org, name, body)
            if action == "versions" and method == "GET":
                return list_versions(claims, org, name)
            if action == "revert" and method == "POST":
                return revert(claims, org, name, body)
    except Exception as e:                                   # noqa: BLE001
        print("error:", repr(e))
        return err(500, "server error")

    return err(404, "no such route")
