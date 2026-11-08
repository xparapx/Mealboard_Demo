"""녹화용 Ollama 대역(127.0.0.1:11434) — 관리 화면 'AI 모델 선택' 드롭다운에 Pi 의 Ollama 와 같은 모델 목록을 채우기 위해 /api/version·/api/tags 만 응답한다.
chat/completions 는 일부러 구현하지 않는다(점검 결과를 꾸미지 않기 위해 — 영상에서는 '점검 실행' 을 누르지 않는다)."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

MODELS = [{"name": "gemma4:e2b", "model": "gemma4:e2b", "size": 4_600_000_000, "details": {"parameter_size": "4.6B", "quantization_level": "Q4_K_M"}},
          {"name": "qwen3.5:4b", "model": "qwen3.5:4b", "size": 3_300_000_000, "details": {"parameter_size": "4B", "quantization_level": "Q4_K_M"}},
          {"name": "qwen3.5:2b-q4_K_M", "model": "qwen3.5:2b-q4_K_M", "size": 1_900_000_000, "details": {"parameter_size": "2B", "quantization_level": "Q4_K_M"}},
          {"name": "ingu627/exaone4.0:1.2b", "model": "ingu627/exaone4.0:1.2b", "size": 812_000_000, "details": {"parameter_size": "1.2B", "quantization_level": "Q4_K_M"}}]


class H(BaseHTTPRequestHandler):
    def _j(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/version"): return self._j(200, {"version": "0.40.6"})
        if self.path.startswith("/api/tags"): return self._j(200, {"models": MODELS})
        if self.path.startswith("/v1/models"): return self._j(200, {"object": "list", "data": [{"id": m["name"], "object": "model"} for m in MODELS]})
        return self._j(404, {"error": "stub"})

    def do_POST(self):
        return self._j(501, {"error": "녹화용 대역 — 생성은 지원하지 않음"})

    def log_message(self, *a):  # 조용히
        pass


HTTPServer(("127.0.0.1", 11434), H).serve_forever()
