"""A fake OpenAI-compatible endpoint server for the pytest suite.

Serves on 127.0.0.1 (ephemeral port):
  GET  /v1/models                     -> model list
  POST /v1/chat/completions           -> canned title/summary JSON
  POST /v1/audio/transcriptions       -> canned transcript text
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BOUNDARY_SPLIT = "boundary="


class FakeEndpointServer:
    def __init__(self):
        self.chat_reply: str | None = None
        self.transcription_reply: str | None = None
        self.fail_transcriptions = False
        self.models = ["fake-llm", "fake-whisper"]
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence request logs
                pass

            def do_GET(self):
                if self.path.rstrip("/").endswith("/models"):
                    body = json.dumps(
                        {"data": [{"id": name} for name in outer.models]}
                    ).encode()
                    self._send(200, body)
                else:
                    self._send(404, b"{}")

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                data = self.rfile.read(length)
                path = self.path.rstrip("/")
                if path.endswith("/chat/completions"):
                    content = (
                        outer.chat_reply
                        or json.dumps({"title": "Fake Title", "summary": "Fake summary sentence."})
                    )
                    reply = {
                        "choices": [
                            {"message": {"role": "assistant", "content": content}}
                        ]
                    }
                    self._send(200, json.dumps(reply).encode())
                elif path.endswith("/audio/transcriptions"):
                    if outer.fail_transcriptions:
                        self._send(500, b'{"error": "boom"}')
                        return
                    if outer.transcription_reply is not None:
                        text = outer.transcription_reply
                    else:
                        ctype = self.headers.get("Content-Type", "")
                        boundary = ctype.split(BOUNDARY_SPLIT, 1)[1].encode()
                        text = f"TRANSCRIPT FROM {self._filename(data, boundary)}"
                    reply = {"text": text}
                    self._send(200, json.dumps(reply).encode())
                else:
                    self._send(404, b"{}")

            @staticmethod
            def _filename(data: bytes, boundary: bytes) -> str:
                for part in data.split(b"--" + boundary):
                    if b'name="file"' in part:
                        for line in part.split(b"\r\n"):
                            if line.startswith(b"Content-Disposition"):
                                marker = "filename=\""
                                decoded = line.decode("utf-8", "replace")
                                if marker in decoded:
                                    return decoded.split(marker, 1)[1].split('"')[0]
                return "unknown.m4a"

            def _send(self, code: int, body: bytes):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    def start(self):
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc_info):
        self.stop()
        return False
