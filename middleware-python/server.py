import json
import os
import ssl
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CERTS = "/certs"
BANK_BASE_URL = os.environ["BANK_BASE_URL"]
CA_BUNDLE = os.environ.get("CA_BUNDLE", f"{CERTS}/bundle-with-dev-ca.crt")


def build_opener():
    context = ssl.create_default_context(cafile=CA_BUNDLE)
    context.load_cert_chain(f"{CERTS}/middleware-client.crt", f"{CERTS}/middleware-client.key")
    return urllib.request.build_opener(
        urllib.request.ProxyHandler(), urllib.request.HTTPSHandler(context=context)
    )


def proxy_in_use():
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"status": "ok"})
        parts = self.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "accounts":
            return self.reply(404, {"error": "not found"})
        url = f"{BANK_BASE_URL}/v1/accounts/{parts[1]}"
        try:
            with build_opener().open(url, timeout=15) as response:
                upstream = json.loads(response.read())
                status = response.status
        except urllib.error.HTTPError as error:
            return self.reply(502, {"error": f"upstream {error.code}", "proxy_env": proxy_in_use()})
        except Exception as error:
            return self.reply(502, {"error": f"{type(error).__name__}: {error}", "proxy_env": proxy_in_use()})
        self.reply(200, {"upstream_status": status, "upstream": upstream, "proxy_env": proxy_in_use()})


ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
