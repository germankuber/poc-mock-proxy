#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for lang in go java rust dotnet; do
  DOCKER_BUILDKIT=0 docker build -q -t "poc-mock-proxy-middleware-$lang" "middleware-$lang" >/dev/null
  echo "built poc-mock-proxy-middleware-$lang"
done
