#!/usr/bin/env python3
"""Run your own keepctx server: the same API and the same site as keepctx.com,
on one port, stored in one SQLite file. Standard library only.

    keepctx-server                       # http://127.0.0.1:8080
    keepctx-server --host 0.0.0.0 --port 9000 --data /srv/keepctx

It speaks plain HTTP. Put HTTPS in front of it before anyone signs in over a
network — passwords travel in the request.
"""
import argparse
import importlib
import json
import os
import pathlib
import secrets
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
# Installed, the data sits beside the code; run from a checkout, out of the repo.
DEFAULT_DATA = pathlib.Path(os.environ.get("CTX_DATA") or (
    HERE / "data" if (HERE / "web").is_dir()
    else pathlib.Path.home() / ".local" / "share" / "keepctx-server" / "data"))
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "application/javascript; charset=utf-8", ".sh": "text/x-shellscript; charset=utf-8",
         ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}


# ------------------------------------------------------------------- storage
# The handler was written against DynamoDB: items keyed by pk + sk, queried by
# pk and an sk prefix. This is that, and only that, on SQLite.

class Cond:
    def __init__(self, sql, args):
        self.sql, self.args = sql, args

    def __and__(self, other):
        return Cond(f"{self.sql} AND {other.sql}", self.args + other.args)


class Key:
    def __init__(self, name):
        assert name in ("pk", "sk")
        self.name = name

    def eq(self, v):
        return Cond(f"{self.name} = ?", [v])

    def begins_with(self, v):
        return Cond(f"substr({self.name}, 1, ?) = ?", [len(v), v])


class Table:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS items "
                        "(pk TEXT, sk TEXT, data TEXT, PRIMARY KEY (pk, sk))")
        self.lock = threading.Lock()

    def get_item(self, Key):
        with self.lock:
            row = self.db.execute("SELECT data FROM items WHERE pk = ? AND sk = ?",
                                  (Key["pk"], Key["sk"])).fetchone()
        return {"Item": json.loads(row[0])} if row else {}

    def put_item(self, Item):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO items VALUES (?, ?, ?)",
                            (Item["pk"], Item["sk"], json.dumps(Item)))

    def delete_item(self, Key):
        with self.lock, self.db:
            self.db.execute("DELETE FROM items WHERE pk = ? AND sk = ?", (Key["pk"], Key["sk"]))

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues):
        with self.lock, self.db:
            row = self.db.execute("SELECT data FROM items WHERE pk = ? AND sk = ?",
                                  (Key["pk"], Key["sk"])).fetchone()
            it = json.loads(row[0]) if row else dict(Key)
            for part in UpdateExpression.replace("SET ", "", 1).split(","):
                k, v = part.strip().split("=")
                it[k.strip()] = ExpressionAttributeValues[v.strip()]
            self.db.execute("INSERT OR REPLACE INTO items VALUES (?, ?, ?)",
                            (Key["pk"], Key["sk"], json.dumps(it)))

    def query(self, KeyConditionExpression, ScanIndexForward=True, Limit=None):
        c = KeyConditionExpression
        sql = (f"SELECT data FROM items WHERE {c.sql} ORDER BY sk "
               f"{'ASC' if ScanIndexForward else 'DESC'}" + (" LIMIT ?" if Limit else ""))
        with self.lock:
            rows = self.db.execute(sql, c.args + ([Limit] if Limit else [])).fetchall()
        return {"Items": [json.loads(r[0]) for r in rows]}


# ------------------------------------------------------------------- setup

def secret(data):
    """Tokens are signed with this. Made once, kept beside the database — a new
    one on every start would sign everybody out."""
    p = data / "secret"
    if not p.exists():
        p.write_text(secrets.token_urlsafe(48))
        p.chmod(0o600)
    return p.read_text().strip()


def load_handler(data):
    """Import handler.py with this server's secret and storage."""
    data.mkdir(parents=True, exist_ok=True)
    os.environ["CTX_JWT_SECRET"] = secret(data)
    sys.path.insert(0, str(HERE))
    H = importlib.import_module("handler")
    H.tbl, H.Key = Table(data / "keepctx.db"), Key
    return H


def web_dir():
    """Installed, the site sits beside this file; in a checkout, one level up."""
    for d in (HERE / "web", HERE.parent / "web"):
        if (d / "app.html").exists():
            return d
    raise SystemExit("keepctx-server: can't find the web/ directory.")


def make_server(host, port, data):
    H, web = load_handler(data), web_dir()

    class Request(BaseHTTPRequestHandler):
        server_version = "keepctx"

        def api(self, method):
            n = int(self.headers.get("content-length") or 0)
            r = H.handler({"requestContext": {"http": {"method": method}},
                           "rawPath": self.path.split("?")[0],
                           "body": self.rfile.read(n).decode() if n else "{}",
                           "headers": {"authorization": self.headers.get("authorization", "")}})
            self.send(r["statusCode"], r["body"].encode(), r.get("headers", {}))

        def page(self):
            path = self.path.split("?")[0].split("#")[0]
            f = (web / (path.lstrip("/") or "index.html")).resolve()
            if web.resolve() not in f.parents or not f.is_file():
                self.send(404, b"not found", {"Content-Type": "text/plain"})
                return
            self.send(200, f.read_bytes(),
                      {"Content-Type": TYPES.get(f.suffix, "application/octet-stream"),
                       "Cache-Control": "no-cache"})

        def send(self, code, body, headers):
            self.send_response(code)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def route(self, method):
            if self.path.startswith("/v1/"):
                self.api(method)
            elif method in ("GET", "HEAD"):
                self.page()
            else:
                self.send(404, b"not found", {"Content-Type": "text/plain"})

        def do_GET(self):
            self.route("GET")

        def do_HEAD(self):
            self.route("HEAD")

        def do_POST(self):
            self.route("POST")

        def do_OPTIONS(self):
            self.route("OPTIONS")

        def log_message(self, fmt, *args):
            if not getattr(self.server, "quiet", False):
                sys.stderr.write(f"{self.command} {self.path.split('?')[0]} {args[1]}\n")

    return ThreadingHTTPServer((host, port), Request)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="keepctx-server",
                                 description="Run your own keepctx server.")
    ap.add_argument("--host", default=os.environ.get("CTX_HOST", "127.0.0.1"),
                    help="address to listen on (default 127.0.0.1; 0.0.0.0 for every interface)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("CTX_PORT", 8080)))
    ap.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA,
                    help=f"where the database and signing secret live (default {DEFAULT_DATA})")
    a = ap.parse_args(argv)

    srv = make_server(a.host, a.port, a.data)
    shown = "127.0.0.1" if a.host in ("0.0.0.0", "") else a.host
    print(f"keepctx server on http://{shown}:{a.port}")
    print(f"  data     {a.data}")
    print(f"  console  http://{shown}:{a.port}/app.html — make the first account there")
    print()
    print("Put HTTPS in front before anyone signs in over a network. With Caddy:")
    print(f"  caddy reverse-proxy --from keepctx.example.com --to :{a.port}")
    print("Then: ctx remote keepctx.example.com")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
