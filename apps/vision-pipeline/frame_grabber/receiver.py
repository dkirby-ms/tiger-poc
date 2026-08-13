"""Minimal HTTP receiver defining the frame-grabber to pre-processor contract."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os


class FrameHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/frames":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        print(
            "received frame "
            f"camera={self.headers.get('X-Camera-Id', 'unknown')} "
            f"sequence={self.headers.get('X-Frame-Sequence', 'unknown')}"
        )
        self.send_response(202)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    port = int(os.getenv("PREPROCESSOR_PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), FrameHandler).serve_forever()


if __name__ == "__main__":
    main()