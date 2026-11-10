#!/bin/sh
# Siege Wing - start the local server; then open http://localhost:8765/ in Chrome or Edge
cd "$(dirname "$0")" && exec python3 tools/serve.py 8765
