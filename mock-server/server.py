import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("mock-server")

ACCOUNT_PATH = re.compile(r"^/v1/accounts/[^/]+$")


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        log.info(
            "GET %s X-Forwarded-Host=%s X-Mock-Slug=%s",
            self.path,
            self.headers.get("X-Forwarded-Host"),
            self.headers.get("X-Mock-Slug"),
        )
        if ACCOUNT_PATH.match(self.path.split("?")[0]):
            return self.reply(200, {"origin": "mock"})
        self.reply(404, {"error": "not found"})

    def log_message(self, format, *args):
        pass


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
