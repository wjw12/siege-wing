#!/usr/bin/env python3
"""Siege Wing play server: static files on localhost only.

usage: serve.py [port] [--dev] [--lan]
  --dev  also accept the test harness uploads (/__shot, /__log write into shots/)
  --lan  listen on all interfaces instead of 127.0.0.1
"""
import http.server, socketserver, os, sys, base64, json, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]; DEV = '--dev' in sys.argv; LAN = '--lan' in sys.argv
PORT = int(ARGS[0]) if ARGS else 8765
class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.glb': 'model/gltf-binary', '.wasm': 'application/wasm'}
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def log_message(self, *a): pass
    def do_POST(self):
        if not DEV: self.send_response(404); self.end_headers(); return
        n = int(self.headers.get('Content-Length', 0)); body = self.rfile.read(n)
        if self.path.startswith('/__shot'):
            name = self.path.split('name=')[-1].replace('/', '_').replace('..', '_')
            data = body.split(b',', 1)[-1]
            os.makedirs('shots', exist_ok=True)
            open(os.path.join('shots', name), 'wb').write(base64.b64decode(data))
        elif self.path.startswith('/__log'):
            os.makedirs('shots', exist_ok=True)
            open('shots/log.txt', 'ab').write(body + b'\n')
        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True; allow_reuse_address = True
print(f'Siege Wing: open http://localhost:{PORT}/  (Ctrl+C to stop)')
S(('0.0.0.0' if LAN else '127.0.0.1', PORT), H).serve_forever()
