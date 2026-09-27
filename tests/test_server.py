"""Server behaviour: accounts, orgs, membership, who can read and write."""
import sys

from fakes import H, call, fresh

fresh()
fails = 0


def check(label, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  -> {detail}"))
    fails += 0 if cond else 1


# legacy account: made before membership rows existed (profile.org + META.owner)
H.tbl.put_item({"pk": "USER#old@x.com", "sk": "PROFILE", "pw": H.hash_pw("password1"),
                "org": "oldorg"})
H.tbl.put_item({"pk": "ORG#oldorg", "sk": "META", "owner": "old@x.com"})
H.tbl.put_item({"pk": "ORG#oldorg", "sk": "CTX#proj", "name": "proj", "org": "oldorg",
                "facts": "- **a** — 1\n", "version": 1})
c, s = call("POST", "/v1/auth/login", {"email": "old@x.com", "password": "password1"})
check("legacy owner logs in and sees their org as admin",
      c == 200 and s["orgs"] == [{"org": "oldorg", "role": "admin"}] and s["org"] == "oldorg", s)
old = s["token"]
c, s = call("GET", "/v1/orgs/oldorg/contexts", token=old)
check("legacy owner can still list contexts", c == 200 and len(s["contexts"]) == 1, s)
c, s = call("POST", "/v1/contexts/oldorg/proj/sync", {"changes": [], "version": 1}, token=old)
check("legacy owner can still sync", c == 200, s)

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
c, s = call("POST", "/v1/contexts", {"name": "shop", "facts": "- **x** — 1\n"}, token=bob)
check("single-org user creates a context without naming the org (old CLI)", c == 200 and s["org"] == "acme", s)
call("POST", "/v1/orgs", {"org": "second"}, token=bob)
c, s = call("POST", "/v1/contexts", {"name": "shop2"}, token=bob)
check("multi-org user must name the org", c == 400, s)
c, s = call("POST", "/v1/contexts", {"name": "shop2", "org": "second"}, token=bob)
check("…and can when they do", c == 200 and s["org"] == "second", s)
c, s = call("POST", "/v1/contexts", {"name": "nope1", "org": "zorg"}, token=bob)
check("can't create a context in someone else's org", c == 403, s)
c, s = call("POST", "/v1/contexts/acme/shop/sync", {"changes": [], "version": 1}, token=bob)
check("member syncs", c == 200, s)

# reads are members-only
call("POST", "/v1/contexts", {"name": "secret", "facts": "- **k** — v\n", "org": "acme"}, token=ann)
c, s = call("GET", "/v1/contexts/acme/secret")
check("reading a context without signing in is refused", c == 401, s)
c, s = call("GET", "/v1/contexts/acme/secret", token=old)
check("reading another org's context is refused", c == 403, s)
c, s = call("GET", "/v1/contexts/acme/secret", token=bob)
check("a member can read it", c == 200 and "**k**" in s["facts"], s)

# removal
call("POST", "/v1/orgs/acme/members/remove", {"email": "bob@x.com"}, token=ann)
c, s = call("POST", "/v1/contexts/acme/shop/sync", {"changes": [], "version": 1}, token=bob)
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
call("POST", "/v1/contexts", {"name": "proj", "facts": "- **a** — 1\n", "org": "team"}, token=own)
c, s = call("GET", "/v1/contexts/team/proj", token=own)
check("the owner can write it", s.get("can_write") is True, s)
c, s = call("GET", "/v1/contexts/team/proj", token=mem)
check("a member reads it but can't write", c == 200 and s.get("can_write") is False, s)
c, s = call("POST", "/v1/contexts/team/proj/sync",
            {"changes": [{"key": "b", "block": "- **b** — 2", "op": "add"}], "version": 1}, token=mem)
check("a member's sync is refused", c == 403 and "read-only" in s.get("error", ""), s)
c, s = call("POST", "/v1/contexts/team/proj/revert", {"version": 1}, token=mem)
check("a member's revert is refused", c == 403, s)
c, s = call("POST", "/v1/contexts/team/proj/sync",
            {"changes": [{"key": "b", "block": "- **b** — 2", "op": "add"}], "version": 1}, token=adm)
check("an org admin can write it", c == 200 and s["version"] == 2, s)
c, s = call("GET", "/v1/orgs/team/contexts", token=mem)
check("the list says who can write", s["contexts"][0]["can_write"] is False, s)

# the same owner in two places: per-key merge, and deletions travel
c, s = call("POST", "/v1/contexts/team/proj/sync",
            {"changes": [{"key": "a", "block": "", "op": "delete"}], "version": 2}, token=own)
check("sync reports every key the server holds", sorted(s.get("keys", [])) == ["b"], s)

# API Gateway base64-encodes bodies it doesn't recognise as text
import base64, json  # noqa: E401,E402
ev = {"requestContext": {"http": {"method": "POST"}}, "rawPath": "/v1/auth/login", "headers": {},
      "isBase64Encoded": True,
      "body": base64.b64encode(json.dumps({"email": "own@x.com", "password": "password1"}).encode()).decode()}
r = H.handler(ev)
check("base64 bodies are decoded", r["statusCode"] == 200, r)

print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
