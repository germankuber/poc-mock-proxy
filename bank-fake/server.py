import json
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CERTS = "/certs"


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.do_handshake()
        super().setup()

    def do_GET(self):
        subject = dict(item[0] for item in self.connection.getpeercert()["subject"])
        body = json.dumps(
            {"origin": "bank", "path": self.path, "client_cert_cn": subject.get("commonName")}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(f"{CERTS}/bank-fake.crt", f"{CERTS}/bank-fake.key")
context.load_verify_locations(f"{CERTS}/bank-ca.crt")
context.verify_mode = ssl.CERT_REQUIRED

server = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
server.serve_forever()
