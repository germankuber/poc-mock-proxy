import json
import logging

from mitmproxy import http, tls

STATE_FILE = "/state/state.json"
MOCK_SERVER_HOST = "mock-server"
MOCK_SERVER_PORT = 8080

log = logging.getLogger("mock-proxy")


def read_state():
    try:
        with open(STATE_FILE) as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        log.warning("state unreadable: %s", error)
        return {}


def mock_for(host):
    entry = read_state().get(host)
    if entry and entry.get("enabled"):
        return entry
    return None


class MockRouter:
    def tls_clienthello(self, data: tls.ClientHelloData):
        host = data.context.server.address[0]
        if mock_for(host) is None:
            data.ignore_connection = True
            log.info("TUNNEL %s", host)
        else:
            log.info("INTERCEPT %s", host)

    def request(self, flow: http.HTTPFlow):
        host = flow.request.host
        entry = mock_for(host)
        if entry is None:
            return
        flow.request.headers["X-Forwarded-Host"] = f"{flow.request.scheme}://{host}:{flow.request.port}"
        flow.request.headers["X-Mock-Slug"] = entry.get("slug", "")
        flow.request.scheme = "http"
        flow.request.host = MOCK_SERVER_HOST
        flow.request.port = MOCK_SERVER_PORT


addons = [MockRouter()]
