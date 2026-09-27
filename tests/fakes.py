"""An in-memory stand-in for the DynamoDB table, and a local HTTP server that
runs server/handler.py on it — so tests need no AWS and no network."""
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "server"))
import handler as H  # noqa: E402


class Cond:
    def __init__(self, fn):
        self.fn = fn

    def __and__(self, other):
        return Cond(lambda it: self.fn(it) and other.fn(it))


class Key:
    def __init__(self, name):
        self.name = name

    def eq(self, v):
        return Cond(lambda it: it.get(self.name) == v)

    def begins_with(self, v):
        return Cond(lambda it: str(it.get(self.name, "")).startswith(v))


class Table:
    def __init__(self):
        self.rows = {}

    def get_item(self, Key):
        it = self.rows.get((Key["pk"], Key["sk"]))
        return {"Item": dict(it)} if it else {}

    def put_item(self, Item):
        self.rows[(Item["pk"], Item["sk"])] = dict(Item)

    def delete_item(self, Key):
        self.rows.pop((Key["pk"], Key["sk"]), None)

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues):
        it = self.rows[(Key["pk"], Key["sk"])]
        for part in UpdateExpression.replace("SET ", "").split(","):
            k, v = part.strip().split("=")
            it[k] = ExpressionAttributeValues[v]

    def query(self, KeyConditionExpression, ScanIndexForward=True, Limit=None):
        items = [dict(i) for i in self.rows.values() if KeyConditionExpression.fn(i)]
        items.sort(key=lambda i: i["sk"], reverse=not ScanIndexForward)
        return {"Items": items[:Limit] if Limit else items}


def fresh():
    """Point the handler at a new, empty table."""
    H.tbl = Table()
    H.Key = Key
    return H


def call(method, path, body=None, token=None):
    ev = {"requestContext": {"http": {"method": method}}, "rawPath": path,
          "body": json.dumps(body or {}), "headers": {}}
    if token:
        ev["headers"]["authorization"] = "Bearer " + token
    r = H.handler(ev)
    return r["statusCode"], json.loads(r["body"])


def serve():
    """Run the handler over HTTP on a free local port. -> (url, stop)"""
    class R(BaseHTTPRequestHandler):
        def go(self, method):
            n = int(self.headers.get("content-length") or 0)
            ev = {"requestContext": {"http": {"method": method}}, "rawPath": self.path,
                  "body": self.rfile.read(n).decode() if n else "{}",
                  "headers": {"authorization": self.headers.get("authorization", "")}}
            r = H.handler(ev)
            self.send_response(r["statusCode"])
            self.end_headers()
            self.wfile.write(r["body"].encode())

        def do_GET(self):
            self.go("GET")

        def do_POST(self):
            self.go("POST")

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), R)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv.shutdown
