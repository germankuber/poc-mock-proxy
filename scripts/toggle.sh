#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  on) enabled=true ;;
  off) enabled=false ;;
  *) echo "usage: toggle.sh on|off" >&2; exit 1 ;;
esac
python3 - "$(dirname "$0")/../state/state.json" "$enabled" <<'PY'
import json, sys
path, enabled = sys.argv[1], sys.argv[2] == "true"
with open(path) as handle:
    state = json.load(handle)
state["bank-fake"]["enabled"] = enabled
with open(path, "w") as handle:
    json.dump(state, handle)
    handle.write("\n")
PY
echo "bank-fake mock enabled=$enabled"
