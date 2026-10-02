"""The self-hosted server end to end: serve.py on SQLite, serving the site and
the API on one port, and everything still there after a restart. (The CLI
doesn't talk to a server for now; this keeps the server working for later.)"""
import http.client
import json
import pathlib
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
import serve  # noqa: E402

fails = 0


def check(label, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"\n     -> {detail}"))
    fails += 0 if cond else 1


def start(data):
    srv = serve.make_server("127.0.0.1", 0, data)
    srv.quiet = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def get(port, path):
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request("GET", path)
    r = c.getresponse()
    return r.status, r.getheader("content-type") or "", r.read()


def post(port, path, body, token=None):
    c = http.client.HTTPConnection("127.0.0.1", port)
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    c.request("POST", path, json.dumps(body), h)
    r = c.getresponse()
    return r.status, json.loads(r.read())


tmp = pathlib.Path(tempfile.mkdtemp())
data = tmp / "data"
srv, port = start(data)

# the site, same as keepctx.com
code, ctype, body = get(port, "/")
check("site: / is the landing page", code == 200 and "text/html" in ctype and b"keepctx" in body)
code, ctype, _ = get(port, "/app.js")
check("site: the console's script is served as javascript", code == 200 and "javascript" in ctype)
code, _, _ = get(port, "/../server/handler.py")
check("site: nothing outside web/ is served", code == 404)
check("secret: made on first start, owner-only",
      (data / "secret").exists() and oct((data / "secret").stat().st_mode)[-3:] == "600")

# the API, on SQLite
code, out = post(port, "/v1/auth/register", {"email": "owner@x.com", "password": "password1"})
check("api: register", code == 200 and out.get("token"), out)
post(port, "/v1/orgs", {"org": "team"}, token=out["token"])

tok = out["token"]
T = "2026-10-01T10:00:00.000Z"
code, out = post(port, "/v1/contexts", {"name": "proj", "org": "team",
                 "facts": {"operations.deploy.command": {"value": "`make ship`", "updated": T, "removed": False}}}, tok)
check("api: a context is stored", code == 200, out)

# restart on the same data: accounts, contexts and sign-ins all survive
srv.shutdown()
srv.server_close()
srv, port2 = start(data)
code, out = post(port2, "/v1/contexts/team/proj/push",
                 {"facts": {"environments.logs.location": {"value": "Splunk", "updated": T, "removed": False}}}, tok)
check("restart: the sign-in still works, and the context is still there",
      code == 200 and out["facts"]["operations.deploy.command"]["value"] == "`make ship`"
      and "environments.logs.location" in out["facts"], out)

srv.shutdown()
print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
