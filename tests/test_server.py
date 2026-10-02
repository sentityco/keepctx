"""Server behaviour: accounts, orgs, membership, who can read and write."""
import json
import sys

from fakes import H, call, fresh

fresh()
fails = 0


def F(value, t="2026-10-01T10:00:00.000Z", removed=False):
    return {"value": value, "updated": t, "removed": removed}


def check(label, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  -> {detail}"))
    fails += 0 if cond else 1


# legacy account: made before membership rows existed (profile.org + META.owner)
H.tbl.put_item({"pk": "USER#old@x.com", "sk": "PROFILE", "pw": H.hash_pw("password1"),
                "org": "oldorg"})
H.tbl.put_item({"pk": "ORG#oldorg", "sk": "META", "owner": "old@x.com"})
H.tbl.put_item({"pk": "ORG#oldorg", "sk": "CTX#proj", "name": "proj", "org": "oldorg",
                "facts": json.dumps({"knowledge.a": F("1")}), "version": 1})
c, s = call("POST", "/v1/auth/login", {"email": "old@x.com", "password": "password1"})
check("legacy owner logs in and sees their org as admin",
      c == 200 and s["orgs"] == [{"org": "oldorg", "role": "admin"}] and s["org"] == "oldorg", s)
old = s["token"]
c, s = call("GET", "/v1/orgs/oldorg/contexts", token=old)
check("legacy owner can still list contexts", c == 200 and len(s["contexts"]) == 1, s)
c, s = call("POST", "/v1/contexts/oldorg/proj/push", {"facts": {"knowledge.a": F("2", "2026-10-01T11:00:00.000Z")}}, token=old)
check("legacy owner can still push", c == 200, s)

# flow 1: account + org
c, s = call("POST", "/v1/auth/register", {"email": "ann@x.com", "password": "password1"})
check("register without an org", c == 200 and s["orgs"] == [] and s["org"] is None, s)
ann = s["token"]
c, s = call("POST", "/v1/orgs", {"org": "acme"}, token=ann)
check("create an org -> admin", c == 200 and s["orgs"] == [{"org": "acme", "role": "admin"}], s)
c, s = call("POST", "/v1/orgs", {"org": "acme"}, token=ann)
check("org names are unique", c == 409, s)
c, s = call("POST", "/v1/auth/register", {"email": "zed@x.com", "password": "password1", "org": "zorg"})
check("register never makes an org, even if asked", c == 200 and s["orgs"] == [], s)
call("POST", "/v1/orgs", {"org": "zorg"}, token=s["token"])

# flow 2: added by an admin — before signing up
c, s = call("POST", "/v1/orgs/acme/members", {"email": "bob@x.com"}, token=ann)
check("admin adds someone with no account yet",
      c == 200 and {"email": "bob@x.com", "role": "member", "owner": False, "account": False} in s["members"], s)
c, s = call("POST", "/v1/auth/register", {"email": "bob@x.com", "password": "password1"})
check("they sign up and are already in the org", c == 200 and s["orgs"] == [{"org": "acme", "role": "member"}], s)
bob = s["token"]

# flow 2b: added after signing up; token is identity-only so no re-login needed
c, s = call("POST", "/v1/auth/register", {"email": "cat@x.com", "password": "password1"})
cat = s["token"]
c, s = call("GET", "/v1/orgs/acme/contexts", token=cat)
check("non-member is refused", c == 403, s)
call("POST", "/v1/orgs/acme/members", {"email": "cat@x.com", "role": "admin"}, token=ann)
c, s = call("GET", "/v1/orgs/acme/contexts", token=cat)
check("added after sign-up works with the same token", c == 200, s)
c, s = call("GET", "/v1/me", token=cat)
check("/me lists orgs", s.get("orgs") == [{"org": "acme", "role": "admin"}], s)

# permissions
c, s = call("POST", "/v1/orgs/acme/members", {"email": "eve@x.com"}, token=bob)
check("a member can't add people", c == 403, s)
c, s = call("POST", "/v1/orgs/acme/members/remove", {"email": "ann@x.com"}, token=cat)
check("the owner can't be removed", c == 400, s)
c, s = call("GET", "/v1/orgs/acme/members", token=bob)
check("a member can see who's in the org", c == 200 and len(s["members"]) == 3, s)

# contexts in the new model
c, s = call("POST", "/v1/contexts", {"name": "shop", "facts": {"knowledge.x": F("1")}}, token=bob)
check("single-org user creates a context without naming the org (old CLI)", c == 200 and s["org"] == "acme", s)
call("POST", "/v1/orgs", {"org": "second"}, token=bob)
c, s = call("POST", "/v1/contexts", {"name": "shop2"}, token=bob)
check("multi-org user must name the org", c == 400, s)
c, s = call("POST", "/v1/contexts", {"name": "shop2", "org": "second"}, token=bob)
check("…and can when they do", c == 200 and s["org"] == "second", s)
c, s = call("POST", "/v1/contexts", {"name": "nope1", "org": "zorg"}, token=bob)
check("can't create a context in someone else's org", c == 403, s)
c, s = call("POST", "/v1/contexts/acme/shop/push", {"facts": {"knowledge.x": F("2", "2026-10-01T11:00:00.000Z")}}, token=bob)
check("its creator pushes", c == 200 and s["version"] == 2, s)

# reads are members-only
call("POST", "/v1/contexts", {"name": "secret", "facts": {"knowledge.k": F("v")}, "org": "acme"}, token=ann)
c, s = call("GET", "/v1/contexts/acme/secret")
check("reading a context without signing in is refused", c == 401, s)
c, s = call("GET", "/v1/contexts/acme/secret", token=old)
check("reading another org's context is refused", c == 403, s)
c, s = call("GET", "/v1/contexts/acme/secret", token=bob)
check("a member can read it", c == 200 and s["facts"]["knowledge.k"]["value"] == "v", s)

# removal
call("POST", "/v1/orgs/acme/members/remove", {"email": "bob@x.com"}, token=ann)
c, s = call("GET", "/v1/contexts/acme/shop", token=bob)
check("removed member loses access immediately", c == 403, s)
c, s = call("GET", "/v1/me", token=bob)
check("…and the org leaves their list", s["orgs"] == [{"org": "second", "role": "admin"}], s)

# who can write: a context's owner and org admins; every other member reads
c, s = call("POST", "/v1/auth/register", {"email": "own@x.com", "password": "password1"})
own = s["token"]
call("POST", "/v1/orgs", {"org": "team"}, token=own)
c, s = call("POST", "/v1/auth/register", {"email": "mem@x.com", "password": "password1"})
mem = s["token"]
c, s = call("POST", "/v1/auth/register", {"email": "adm@x.com", "password": "password1"})
adm = s["token"]
call("POST", "/v1/orgs/team/members", {"email": "mem@x.com"}, token=own)
call("POST", "/v1/orgs/team/members", {"email": "adm@x.com", "role": "admin"}, token=own)
call("POST", "/v1/auth/register", {"email": "mk@x.com", "password": "password1"})
call("POST", "/v1/contexts", {"name": "proj", "facts": {"knowledge.a": F("1")}, "org": "team"}, token=own)
c, s = call("GET", "/v1/contexts/team/proj", token=own)
check("the owner can write it", s.get("can_write") is True, s)
c, s = call("GET", "/v1/contexts/team/proj", token=mem)
check("a member reads it but can't write", c == 200 and s.get("can_write") is False, s)
c, s = call("POST", "/v1/contexts/team/proj/push", {"facts": {"knowledge.b": F("2")}}, token=mem)
check("a member's push is refused", c == 403 and "read-only" in s.get("error", ""), s)
c, s = call("POST", "/v1/contexts/team/proj/revert", {"version": 1}, token=mem)
check("a member's revert is refused", c == 403, s)
c, s = call("POST", "/v1/contexts/team/proj/push",
            {"facts": {"knowledge.b": F("2")}}, token=adm)
check("an org admin can write it", c == 200 and s["version"] == 2, s)
c, s = call("GET", "/v1/orgs/team/contexts", token=mem)
check("the list says who can write", s["contexts"][0]["can_write"] is False, s)

# push: for every fact the most recent change wins, and the merged whole comes back
T1, T2, T3 = "2026-10-01T12:00:00.000Z", "2026-10-01T13:00:00.000Z", "2026-10-01T14:00:00.000Z"
c, s = call("POST", "/v1/contexts/team/proj/push",
            {"facts": {"knowledge.a": F("new", T2), "knowledge.c": F("3", T1)}}, token=own)
check("push: newer facts are taken", c == 200 and s["accepted"] == 2
      and s["facts"]["knowledge.a"]["value"] == "new" and "knowledge.b" in s["facts"], s)
c, s = call("POST", "/v1/contexts/team/proj/push", {"facts": {"knowledge.a": F("stale", T1)}}, token=own)
check("push: an older change loses, and nothing new is stored",
      s["accepted"] == 0 and s["facts"]["knowledge.a"]["value"] == "new" and s["version"] == 3, s)
c, s = call("POST", "/v1/contexts/team/proj/push",
            {"facts": {"knowledge.c": F("3", T3, removed=True)}}, token=own)
c, s = call("GET", "/v1/contexts/team/proj", token=own)
check("push: a removal is kept as a marked key, and not counted",
      s["facts"]["knowledge.c"]["removed"] is True and s["count"] == 2, s)
c, s = call("POST", "/v1/contexts/team/proj/push", {"facts": {"knowledge.c": F("3", T2)}}, token=own)
check("push: an older copy can't bring a removed fact back", s["accepted"] == 0, s)
c, s = call("GET", "/v1/contexts/team/proj/versions", token=own)
check("push: every accepted push is a version", [v["version"] for v in s["versions"]] == [4, 3, 2, 1], s)
c, s = call("POST", "/v1/contexts/team/proj/push", {"facts": {"no-category": F("x")}}, token=own)
check("push: keys must be category.key", c == 400, s)
c, s = call("POST", "/v1/contexts/team/proj/push", {"facts": {"knowledge.d": {"value": "x"}}}, token=own)
check("push: every fact needs its time", c == 400, s)

# the console edits one fact at a time, stamped now
c, s = call("POST", "/v1/contexts/team/proj/facts", {"key": "people.owner", "value": "Jason"}, token=own)
check("edit: a person adds a fact", c == 200 and s["facts"]["people.owner"]["value"] == "Jason"
      and s["facts"]["people.owner"]["updated"] > T3, s)
c, s = call("POST", "/v1/contexts/team/proj/facts", {"key": "people.owner", "removed": True}, token=own)
check("edit: and removes it", s["facts"]["people.owner"]["removed"] is True, s)
c, s = call("POST", "/v1/contexts/team/proj/facts", {"key": "people.x", "value": "y"}, token=mem)
check("edit: read-only members can't", c == 403, s)

# revert: the old facts come back as a new change, so they win on every copy
c, s = call("POST", "/v1/contexts/team/proj/revert", {"version": 2}, token=own)
c, s = call("GET", "/v1/contexts/team/proj", token=own)
f = s["facts"]
check("revert: back to how that version had it, stamped now",
      f["knowledge.a"]["value"] == "1" and f["knowledge.a"]["updated"] > T3
      and f["knowledge.c"]["removed"] and f["people.owner"]["removed"] and not f["knowledge.b"]["removed"], f)

# API Gateway base64-encodes bodies it doesn't recognise as text
import base64  # noqa: E402
ev = {"requestContext": {"http": {"method": "POST"}}, "rawPath": "/v1/auth/login", "headers": {},
      "isBase64Encoded": True,
      "body": base64.b64encode(json.dumps({"email": "own@x.com", "password": "password1"}).encode()).decode()}
r = H.handler(ev)
check("base64 bodies are decoded", r["statusCode"] == 200, r)

# secrets: refused at the door, and nothing from that push is kept
fake_aws = "AKIA" + "ABCDEFGHIJKLMNOP"
c, s = call("POST", "/v1/contexts/team/proj/push",
            {"facts": {"knowledge.e": F("ok", T3), "environments.aws.key": F(fake_aws, T3)}}, token=own)
c2, v = call("GET", "/v1/contexts/team/proj", token=own)
check("secrets: a fact holding a key is refused, with nothing kept",
      c == 400 and "AWS access key" in s["error"] and "knowledge.e" not in v["facts"], s)
c, s = call("POST", "/v1/contexts/team/proj/facts",
            {"key": "knowledge.gh", "value": "token ghp_" + "a" * 36}, token=own)
check("secrets: a console edit holding a token is refused", c == 400 and "GitHub" in s["error"], s)
c, s = call("POST", "/v1/contexts/team/proj/push",
            {"facts": {"environments.auth.password": F("never in the repo; ask ops", T3)}}, token=own)
check("secrets: talking about passwords is fine", c == 200, s)
c, s = call("POST", "/v1/contexts", {"name": "leaky", "org": "team",
            "facts": {"knowledge.k": F("-----BEGIN RSA PRIVATE KEY-----")}}, token=own)
check("secrets: a new context holding one is refused", c == 400, s)

c, s = call("POST", "/v1/contexts/team/proj/push", {"facts": {}}, token=ann)  # ann is in acme
check("push: members of the org only", c == 403, s)

print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
