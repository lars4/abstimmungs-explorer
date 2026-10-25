#!/usr/bin/env bash
# Build real data and sync the static site to your own server (e.g. xirvik.ch/abstimmungen/).
#   XIRVIK_TARGET=user@host:/var/www/xirvik.ch/abstimmungen ./scripts/deploy.sh
# Requires ssh access + rsync. Nothing in this script touches anything outside $XIRVIK_TARGET.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${XIRVIK_TARGET:?set XIRVIK_TARGET=user@host:/path/to/abstimmungen}"
python3 -m pipeline.build live
python3 - <<'PY'
import json
d = json.load(open("web/data/votes.json"))
assert not d["meta"]["demo"] and d["meta"]["voteCount"] > 300, d["meta"]
PY
rsync -az --delete --exclude '.DS_Store' web/ "$XIRVIK_TARGET/"
echo "deployed -> $XIRVIK_TARGET"
