"""RackOps Lab live-lab target: a tiny, isolated HTTP service owned by the lab.

It binds to 127.0.0.1 only and serves GET /health. Stopping and starting it is a safe,
real service-outage exercise that never touches host services.

Run directly:  python -m app.livelab.target --port 18081 --log /path/to/target.log
"""
import argparse
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARKER = "rackops-lab-target"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18081)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()
    logging.basicConfig(filename=args.log, level=logging.INFO, format="%(asctime)sZ %(name)s[%(process)d]: %(message)s")
    logging.Formatter.converter = __import__("time").gmtime
    log = logging.getLogger(MARKER)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path != "/health":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"service": MARKER, "status": "ok", "pid": os.getpid(),
                               "time": datetime.now(timezone.utc).isoformat()}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)

    def _term(signum, frame):
        log.info("received SIGTERM, shutting down")
        srv.server_close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _term)
    log.info("listening on 127.0.0.1:%d", args.port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
