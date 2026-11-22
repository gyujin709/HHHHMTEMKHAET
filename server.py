import argparse
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROUTES = json.loads((ROOT / "routes.json").read_text(encoding="utf-8"))
BUSES = {}
LOCK = threading.Lock()
EXPIRE = 12
DEFAULT_TRAVEL_SECONDS = 25
TRAFFIC_LEVELS = ("원활", "원활", "서행", "원활", "정체", "서행")


def position(route, step):
    stops = ROUTES[route]["stops"]
    last = len(stops) - 1
    stop = step if step <= last else 2 * last - step
    direction = "out" if step < last else "back"
    next_stop = stop + (1 if direction == "out" else -1)
    return {"stop": stop, "direction": direction, "next": next_stop}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, kind="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self.reply(200, (ROOT / "dist/index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/state":
            with LOCK:
                now = time.monotonic()
                buses = {
                    route: {
                        **position(route, step), "age": round(now - seen, 1),
                        "sinceStop": round(now - arrived, 1), "travelSeconds": round(typical, 1),
                    }
                    for route, (step, seen, arrived, typical) in BUSES.items() if now - seen < EXPIRE
                }
            phase = int(time.time() // 60)
            traffic = {
                route: [TRAFFIC_LEVELS[(phase + i * 2 + segment) % len(TRAFFIC_LEVELS)]
                        for segment in range(len(info["stops"]) - 1)]
                for i, (route, info) in enumerate(ROUTES.items())
            }
            return self.reply(200, {"routes": ROUTES, "buses": buses, "traffic": traffic})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/share":
            return self.reply(404, {"error": "not found"})
        if not secrets.compare_digest(self.headers.get("X-Model-Key", "").encode(), self.server.key.encode()):
            return self.reply(403, {"error": "invalid key"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                raise ValueError
            self.connection.settimeout(3)
            data = json.loads(self.rfile.read(length))
            me = data["me"]
            route, step = me["line"], me["step"]
            if route not in ROUTES or type(step) is not int or not 0 <= step < 2 * (len(ROUTES[route]["stops"]) - 1):
                raise ValueError
        except (ValueError, TypeError, KeyError, TimeoutError):
            return self.reply(400, {"error": "invalid route or step"})
        with LOCK:
            now = time.monotonic()
            arrived, typical = now, DEFAULT_TRAVEL_SECONDS
            previous = BUSES.get(route)
            if previous and now - previous[1] < EXPIRE:
                old_step, _, old_arrived, typical = previous
                if step == old_step:
                    arrived = old_arrived
                elif step == (old_step + 1) % (2 * (len(ROUTES[route]["stops"]) - 1)):
                    elapsed = now - old_arrived
                    if 3 <= elapsed <= 300:
                        typical = typical * 0.6 + elapsed * 0.4
            BUSES[route] = (step, now, arrived, typical)
        self.reply(200, {"ok": True})

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lan", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--key", help="Optional key for automated local checks")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0" if args.lan else "127.0.0.1", args.port), Handler)
    key_file = ROOT / ".model-key"
    if args.lan and args.key is None:
        try:
            with key_file.open("x", encoding="ascii") as handle:
                handle.write(secrets.token_hex(12))
        except FileExistsError:
            pass
        server.key = key_file.read_text(encoding="ascii").strip()
        if not server.key:
            parser.error(".model-key is empty")
    else:
        server.key = args.key or secrets.token_hex(12)
    print(f"PC: http://127.0.0.1:{args.port}", flush=True)
    if args.lan:
        for ip in sorted({v[4][0] for v in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}):
            if not ip.startswith("127."):
                print(f"LAN: http://{ip}:{args.port}", flush=True)
        print(f"ESP32 MODEL_KEY: {server.key}", flush=True)
    with server:
        server.serve_forever()


if __name__ == "__main__":
    main()
