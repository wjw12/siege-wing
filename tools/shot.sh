#!/bin/bash
# usage: tools/shot.sh "<query string>" [timeout_s]  -> runs headless Edge until page logs DONE (or timeout); shots in shots/
cd "$(dirname "$0")/.."
Q="$1"; T="${2:-60}"
curl -s -o /dev/null http://localhost:8765/ || { (nohup python3 tools/serve.py 8765 --dev > /tmp/serve.log 2>&1 &); sleep 1; }
rm -f shots/log.txt
EDGE="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
"$EDGE" --headless=new --no-first-run --user-data-dir='C:\Users\shaoy\AppData\Local\Temp\sw_edge' --enable-gpu --use-angle=d3d11 --ignore-gpu-blocklist --autoplay-policy=no-user-gesture-required --window-size=${W:-1600},${H:-900} "http://localhost:8765/?$Q" >/dev/null 2>&1 &
for i in $(seq 1 $((T*2))); do sleep 0.5; grep -q "DONE" shots/log.txt 2>/dev/null && break; done
powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { \$_.CommandLine -like '*sw_edge *' -or \$_.CommandLine -like '*sw_edge\"*' -or \$_.CommandLine -like '*Temp\\sw_edge --*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }" >/dev/null 2>&1
cat shots/log.txt 2>/dev/null | cut -c1-600 | tail -${TAILN:-40}
