#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "state" / "state.json"
BANK_HOST = "bank-fake"

LANGUAGES = {
    "python": {"icon": "🐍", "port": 9000, "untrusted": "CERTIFICATE_VERIFY_FAILED"},
    "go": {"icon": "🐹", "port": 9010, "untrusted": "x509: certificate signed by unknown authority"},
    "java": {"icon": "☕", "port": 9020, "untrusted": "unable to find valid certification path"},
    "rust": {"icon": "🦀", "port": 9030, "untrusted": "UnknownIssuer"},
    "dotnet": {"icon": "🟣", "port": 9040, "untrusted": "RemoteCertificateValidationCallback"},
}


COLORS_ENABLED = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def paint(code, text):
    return f"\033[{code}m{text}\033[0m" if COLORS_ENABLED else text


def green(text):
    return paint("32", text)


def red(text):
    return paint("31", text)


def dim(text):
    return paint("90", text)


def bold(text):
    return paint("1", text)


class Results:
    def __init__(self):
        self.by_language = {}

    def record(self, language, passed):
        self.by_language.setdefault(language, []).append(passed)

    def failures(self):
        return sum(not passed for outcomes in self.by_language.values() for passed in outcomes)

    def total(self):
        return sum(len(outcomes) for outcomes in self.by_language.values())


def run(command, quiet=False):
    return subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.STDOUT if quiet else None,
    ).returncode


def set_mock(enabled):
    state = json.loads(STATE_FILE.read_text())
    state[BANK_HOST]["enabled"] = enabled
    STATE_FILE.write_text(json.dumps(state) + "\n")
    print(f"  🔀 mock {'ON' if enabled else 'OFF'}")


def prepare(skip_up):
    if not (ROOT / "certs" / "bank-ca.crt").exists():
        run(["./scripts/gen-certs.sh"])
    set_mock(False)
    if skip_up:
        return
    if run(["./scripts/build-images.sh"], quiet=True) != 0:
        sys.exit("image build failed")
    if run(["docker", "compose", "up", "-d", "--force-recreate", "--remove-orphans"], quiet=True) != 0:
        sys.exit("compose up failed")


def fetch(url, timeout=25):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except OSError as error:
        return 0, f"{type(error).__name__}: {error}"


def wait_ready(ports):
    for port in ports:
        for _ in range(240):
            if fetch(f"http://localhost:{port}/health", timeout=2)[0] == 200:
                break
            time.sleep(0.5)
        else:
            sys.exit(f"service on port {port} did not become ready")


def account(port):
    status, body = fetch(f"http://localhost:{port}/accounts/42")
    try:
        return status, json.loads(body), body
    except ValueError:
        return status, {}, body


def check(results, language, description, port, assertion):
    status, payload, raw = account(port)
    try:
        assertion(status, payload)
        passed = True
    except (AssertionError, KeyError, TypeError):
        passed = False
    results.record(language, passed)
    print(f"  {'✅' if passed else '❌'} {green('PASS') if passed else red('FAIL')}  {description}")
    if not passed:
        print(dim(f"       {raw[:300]}"))


def assert_bank_with_client_cert(status, payload):
    assert status == 200
    upstream = payload["upstream"]
    assert upstream["origin"] == "bank"
    assert upstream["path"] == "/v1/accounts/42"
    assert upstream["client_cert_cn"] == "middleware-client"
    assert payload["proxy_env"] is not None


def assert_mock(status, payload):
    assert status == 200
    assert payload["upstream"] == {"origin": "mock"}


def assert_bank(status, payload):
    assert status == 200
    assert payload["upstream"]["origin"] == "bank"


def assert_bank_direct(status, payload):
    assert_bank(status, payload)
    assert payload["proxy_env"] is None


def assert_untrusted(expected):
    def assertion(status, payload):
        assert status == 502
        assert expected in payload["error"]

    return assertion


def run_language(results, language):
    spec = LANGUAGES[language]
    port = spec["port"]
    print()
    print(bold(f"{spec['icon']} {language}"))
    set_mock(False)
    check(results, language, "a) mock OFF via proxy -> bank, mTLS end to end", port, assert_bank_with_client_cert)
    set_mock(True)
    check(results, language, "b) mock ON via proxy -> mock", port, assert_mock)
    set_mock(False)
    check(results, language, "c) flip OFF again, no restart -> bank", port, assert_bank)
    set_mock(True)
    check(results, language, "d) prod (no HTTPS_PROXY), mock flag ON -> bank directly", port + 2, assert_bank_direct)
    check(results, language, "e) mock ON, no dev CA -> TLS verify error", port + 1, assert_untrusted(spec["untrusted"]))
    set_mock(False)


def print_summary(results):
    print()
    print(bold("📊 Summary"))
    for language, outcomes in results.by_language.items():
        passed = sum(outcomes)
        line = f"  {LANGUAGES[language]['icon']} {language:<8} {passed}/{len(outcomes)}"
        print(green(line) if passed == len(outcomes) else red(line))
    print()
    failures = results.failures()
    passed = results.total() - failures
    if failures == 0:
        print(green(bold(f"🎉 ALL PASS ({passed}/{results.total()})")))
    else:
        print(red(bold(f"💥 {failures} FAILED, {passed}/{results.total()} passed")))


def main():
    if not __debug__:
        sys.exit("run without -O: checks rely on assert")
    parser = argparse.ArgumentParser(description="Run the mock proxy PoC cases for every middleware")
    parser.add_argument("language", nargs="?", choices=sorted(LANGUAGES))
    parser.add_argument("--no-up", action="store_true", help="skip docker compose up")
    arguments = parser.parse_args()
    selected = [arguments.language] if arguments.language else list(LANGUAGES)

    prepare(arguments.no_up)
    wait_ready([LANGUAGES[language]["port"] + offset for language in selected for offset in range(3)])
    time.sleep(2)

    results = Results()
    try:
        for language in selected:
            run_language(results, language)
    finally:
        set_mock(False)
    print_summary(results)
    sys.exit(1 if results.failures() else 0)


if __name__ == "__main__":
    main()
