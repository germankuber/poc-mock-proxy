#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"

failures=0
check() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$actual" == *"$expected"* ]]; then
    echo "PASS  $name"
  else
    echo "FAIL  $name"
    failures=$((failures + 1))
  fi
  echo "      -> $actual"
}

call() { curl -s --max-time 25 "http://localhost:$1/accounts/42"; }

[[ -f certs/bank-ca.crt ]] || ./scripts/gen-certs.sh
./scripts/seed-mock.sh >/dev/null
./scripts/toggle.sh off >/dev/null
docker compose up -d --force-recreate
for port in 9000 9001 9002; do
  for _ in $(seq 1 40); do
    curl -s -o /dev/null "http://localhost:$port/health" && break
    sleep 0.5
  done
done
sleep 2

./scripts/toggle.sh off
check "a) mock OFF via proxy -> bank, mTLS end to end" '"origin": "bank", "path": "/v1/accounts/42", "client_cert_cn": "middleware-client"' "$(call 9000)"

./scripts/toggle.sh on
check "b) mock ON via proxy -> mock" '"upstream": {"origin": "mock"}' "$(call 9000)"

./scripts/toggle.sh off
check "c) flip OFF again, no restart -> bank" '"origin": "bank"' "$(call 9000)"

./scripts/toggle.sh on
check "d) prod (no HTTPS_PROXY) with mock flag ON -> bank directly" '"origin": "bank"' "$(call 9002)"

check "e) mock ON, middleware without dev CA -> TLS verify error" 'CERTIFICATE_VERIFY_FAILED' "$(call 9001)"
./scripts/toggle.sh off

echo
if [[ $failures -eq 0 ]]; then echo "ALL PASS"; else echo "$failures FAILED"; exit 1; fi
