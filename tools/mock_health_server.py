"""本地"健康/不健康"开关靶点，用于测 MTTR（巡检发现→恢复）闭环。

用法（另开一个终端）：
    python -m tools.mock_health_server 8899

访问 http://127.0.0.1:8899/health 返回 200 + {"status":"ok"}（健康）。
Ctrl+C 停掉它 -> 巡检就会把这靶点当作"故障"（连接失败），生成 incident；
再重新运行它 -> 巡检恢复 -> incident 关闭，MTTR 被计算出来。
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/health"):
            body = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args) -> None:  # 静默，避免刷屏
        pass


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"[mock] 健康靶点 http://127.0.0.1:{port}/health 已启动（{json.dumps({'status': 'ok'})}）。Ctrl+C 停止。")
    HTTPServer(("127.0.0.1", port), _Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
