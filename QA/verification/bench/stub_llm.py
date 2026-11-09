"""A stand-in LLM that answers instantly, so the benchmark measures OUR code, not the model's thinking time."""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps({
            "id": "stub", "object": "chat.completion", "created": 0, "model": "stub",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "This is an instant stub reply."}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), H).serve_forever()
