"""테스트용 가짜 OpenRouter. /chat/completions 요청을 기록하고, 정해 둔 답을 돌려준다."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOpenRouter:
    def __init__(self):
        self.requests = []          # [(headers dict, body dict)]
        self.reply = "답"           # 문자열이면 choices[0].message.content 로, dict 면 JSON 으로 감싸서
        self.status = 200
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(({k.lower(): v for k, v in self.headers.items()}, body))
                if fake.status != 200:
                    out = json.dumps({"error": {"message": "fake error"}}).encode()
                else:
                    content = fake.reply if isinstance(fake.reply, str) else json.dumps(fake.reply, ensure_ascii=False)
                    out = json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]}).encode()
                self.send_response(fake.status if self.path == "/chat/completions" else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
