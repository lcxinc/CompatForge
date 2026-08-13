#!/usr/bin/env python3
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>MacWin Firefox Compatibility</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #f4f6f8; color: #17212b; font: 18px "Microsoft YaHei", "SimSun", sans-serif; }
  header { background: #0b6e4f; color: white; padding: 36px 48px; }
  h1 { margin: 0 0 8px; font-size: 34px; }
  main { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 32px 48px; }
  section { min-height: 190px; padding: 22px; border: 2px solid #c8d2dc; background: white; }
  .accent { border-color: #e4572e; }
  #status { color: #0b6e4f; font-weight: 700; }
  canvas { width: 100%; height: 110px; border: 1px solid #8392a5; }
</style>
</head>
<body>
<header><h1>MacWin Firefox</h1><div id="headline"></div></header>
<main>
  <section><h2>Gecko / CSS Grid</h2><p id="status">Running</p><p id="api"></p></section>
  <section class="accent"><h2>Canvas / UTF-8</h2><canvas id="canvas" width="480" height="110"></canvas></section>
</main>
<script>
function runProbe() {
  const chinese = "\u4e2d\u6587\u5b57\u4f53\u4e0e\u6d4f\u89c8\u5668\u6e32\u67d3\u6b63\u5e38";
  document.getElementById("headline").textContent = chinese;
  const apiRequest = new XMLHttpRequest();
  apiRequest.open("GET", "/api", false);
  apiRequest.send();
  const api = JSON.parse(apiRequest.responseText);
  document.getElementById("api").textContent = api.message;

  const canvas = document.getElementById("canvas");
  const context = canvas.getContext("2d");
  context.fillStyle = "#0b6e4f";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#ffffff";
  context.font = "24px Microsoft YaHei, SimSun, sans-serif";
  context.fillText(chinese, 24, 66);
  const canvasPixel = Array.from(context.getImageData(10, 10, 1, 1).data);

  const randomValues = new Uint32Array(4);
  crypto.getRandomValues(randomValues);
  const decoded = new TextDecoder("utf-8").decode(new TextEncoder().encode(chinese));
  const result = {
    api,
    canvasPixel,
    cryptoRandom: Array.from(randomValues).some(value => value !== 0),
    cssGrid: getComputedStyle(document.querySelector("main")).display === "grid",
    fontAvailable: document.fonts.check("20px sans-serif", chinese),
    utf8RoundTrip: decoded === chinese,
    userAgent: navigator.userAgent
  };
  document.getElementById("status").textContent = "PASS";
  const resultRequest = new XMLHttpRequest();
  resultRequest.open("POST", "/result", false);
  resultRequest.setRequestHeader("Content-Type", "application/json");
  resultRequest.send(JSON.stringify(result));
}
try {
  runProbe();
} catch (error) {
  document.getElementById("status").textContent = "FAIL: " + error;
  const failureRequest = new XMLHttpRequest();
  failureRequest.open("POST", "/result", false);
  failureRequest.setRequestHeader("Content-Type", "application/json");
  failureRequest.send(JSON.stringify({error: String(error)}));
}
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    result_path = None

    def send_bytes(self, status, content_type, content):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path == "/health":
            self.send_bytes(200, "text/plain; charset=utf-8", b"ok")
        elif self.path == "/api":
            body = json.dumps(
                {"message": "\u6d4f\u89c8\u5668\u7f51\u7edc\u6b63\u5e38", "score": 100},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_bytes(200, "application/json; charset=utf-8", body)
        elif self.path == "/" or self.path.startswith("/?"):
            self.send_bytes(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        else:
            self.send_bytes(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self):
        if self.path != "/result":
            self.send_bytes(404, "text/plain; charset=utf-8", b"not found")
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.result_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.send_bytes(200, "application/json; charset=utf-8", b'{"saved":true}')

    def log_message(self, format_string, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    Handler.result_path = args.result
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
