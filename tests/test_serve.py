"""The self-hosted server end to end: serve.py on SQLite, serving the site and
the API on one port, with the CLI pointed at it by `ctx remote <server>` and
`ctx clone <org>:<name> <server>` — and everything still there after a restart."""
import http.client
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTX = str(ROOT / "src" / "keepctx.py")
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


env = {k: v for k, v in os.environ.items() if k != "CTX_REMOTE"}   # the argument alone picks the server


def ctx(cwd, *args, typed=""):
    r = subprocess.run([sys.executable, CTX, *args], cwd=cwd, input=typed, text=True,
                       capture_output=True, env=env)
    return r.stdout + r.stderr


def cfg(d):
    return json.loads((d / ".ctx" / "config.json").read_text())


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

# the CLI, pointed at it by argument — a bare host:port on this machine means http
spec = importlib.util.spec_from_file_location("keepctx", CTX)
K = importlib.util.module_from_spec(spec)
spec.loader.exec_module(K)
check("url: a bare name gets https", K.server_url("keepctx.example.com") == "https://keepctx.example.com")
check("url: a full URL is kept as typed",
      K.server_url("https://keepctx.example.com/") == "https://keepctx.example.com")
check("url: localhost gets http", K.server_url("localhost:8080") == "http://localhost:8080")

me = "owner@x.com\npassword1\n"
A, B = tmp / "a", tmp / "b"
A.mkdir()
B.mkdir()
ctx(A, "init", "proj")
ctx(A, "remember", "operations", "deploy.command", "`make ship`")
out = ctx(A, "remote", f"127.0.0.1:{port}", typed=me + "\n")
check("cli: ctx remote <server> goes live there", "team:proj is live" in out, out)
check("cli: the directory remembers the server", cfg(A)["remote"] == f"http://127.0.0.1:{port}", cfg(A))
check("cli: sign-up hint points at this server's console", f"127.0.0.1:{port}/app.html" in out, out)

out = ctx(B, "clone", "team:proj", f"http://127.0.0.1:{port}", typed=me)
check("cli: ctx clone <org>:<name> <server>", "make ship" in (B / ".ctx" / "proj" / "facts.md").read_text(), out)

out = ctx(A, "clone", "team:other", "https://keepctx.other.example.com")
check("cli: one server per directory", "already syncs with" in out, out)

# restart on the same data: accounts, contexts and sign-ins all survive
srv.shutdown()
srv.server_close()
srv, port2 = start(data)
for d in (A, B):
    c = cfg(d)
    c["remote"] = f"http://127.0.0.1:{port2}"
    (d / ".ctx" / "config.json").write_text(json.dumps(c))
ctx(A, "remember", "environments", "logs.location", "Splunk")
out = ctx(B, "pull")
check("restart: data and sign-ins survive, pull and push still work",
      "Splunk" in (B / ".ctx" / "proj" / "facts.md").read_text(), out)

srv.shutdown()
print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
