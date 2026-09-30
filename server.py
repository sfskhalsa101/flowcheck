"""Local demo server; Python 3.11+. Run: python3 server.py"""
import argparse
import csv
import io
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from flowcheck.engine import ValidationError
from flowcheck.store import Store

ROOT = Path(__file__).resolve().parent


def handler_for(store):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, mime="application/json", download=None):
            if mime == "application/json":
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/runs":
                return self.send(200, store.history())
            match = re.fullmatch(r"/api/runs/([0-9]+)(/export)?", path)
            if match:
                try:
                    run = store.get(int(match[1]))
                except KeyError:
                    return self.send(404, {"error": "Run not found."})
                if not match[2]:
                    return self.send(200, run)
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=["shipment_id", "sku", "rule", "warehouse_qty", "transport_qty", "delta", "action"])
                writer.writeheader()
                writer.writerows(run['issues'])
                return self.send(200, output.getvalue(), "text/csv", f"flowcheck-run-{run['id']}.csv")
            assets = {"/": ("static/index.html", "text/html"), "/app.js": ("static/app.js", "text/javascript"),
                      "/styles.css": ("static/styles.css", "text/css"),
                      "/samples/warehouse.csv": ("samples/warehouse.csv", "text/csv"),
                      "/samples/transport.csv": ("samples/transport.csv", "text/csv"),
                      "/samples/transport-fixed.csv": ("samples/transport-fixed.csv", "text/csv")}
            if path in assets:
                file, mime = assets[path]
                return self.send(200, (ROOT / file).read_bytes(), mime)
            self.send(404, {"error": "Not found."})

        def do_POST(self):
            if self.path != "/api/runs":
                return self.send(404, {"error": "Not found."})
            # Browsers must originate from this local application; JSON disallows simple cross-origin form posts.
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host')}":
                return self.send(403, {"error": "Cross-origin writes are not allowed."})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.send(415, {"error": "Content-Type must be application/json."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1_100_000:
                    return self.send(413, {"error": "Request must be between 1 byte and 1.1 MB."})
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValidationError("Expected a JSON object.")
                result = store.run(payload.get("label"), payload.get("warehouse"), payload.get("transport"))
                self.send(200 if result['reused'] else 201, result)
            except (ValueError, UnicodeError) as exc:
                self.send(400, {"error": str(exc)})

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=str(ROOT / "work" / "flowcheck.db"))
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(Store(args.db)))
    print(f"FlowCheck is ready: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
