"""
小说阅读器 — 本地服务器 + 代理
用法: python proxy.py

电脑访问: http://localhost:7890
iPhone访问: http://<显示的IP>:7890  (需在同一WiFi)
"""
import os, socket, struct, zlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
import urllib.request, urllib.error

PORT = 7890
BASE = os.path.dirname(os.path.abspath(__file__))

MIME = {
    '.html': 'text/html; charset=utf-8',
    '.json': 'application/json',
    '.js':   'application/javascript',
    '.png':  'image/png',
    '.svg':  'image/svg+xml',
    '.txt':  'text/plain; charset=utf-8',
}

FETCH_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'identity',
}


class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path   = parsed.path.rstrip('/') or '/'

        # ── Health check ───────────────────────────────────────────────
        if path == '/ping':
            self._text(200, 'pong')
            return

        # ── Proxy request ──────────────────────────────────────────────
        if 'url' in params:
            self._proxy(unquote(params['url'][0]))
            return

        # ── Static file serving ────────────────────────────────────────
        if path == '/':
            path = '/reader.html'
        filepath = os.path.join(BASE, path.lstrip('/'))

        if not os.path.isfile(filepath):
            self._text(404, f'Not found: {path}')
            return

        ext = os.path.splitext(filepath)[1].lower()
        mime = MIME.get(ext, 'application/octet-stream')
        with open(filepath, 'rb') as f:
            body = f.read()
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self, target):
        try:
            req = urllib.request.Request(
                target,
                headers={**FETCH_HEADERS, 'Referer': target}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                final_url    = resp.url
                content_type = resp.headers.get('Content-Type', 'text/html')
                raw          = resp.read()
        except urllib.error.HTTPError as e:
            self._text(502, f'Remote HTTP {e.code}: {e.reason}'); return
        except Exception as e:
            self._text(502, str(e)); return

        html = self._decode(raw, content_type)
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Final-Url', final_url)
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _decode(self, raw, content_type):
        encoding = 'utf-8'
        if 'charset=' in content_type:
            encoding = content_type.split('charset=')[-1].split(';')[0].strip()
        snip = raw[:2000].lower()
        for pat in (b'charset=gb2312', b'charset=gbk', b'charset=gb18030', b'charset=big5'):
            if pat in snip:
                encoding = pat.decode().split('=')[1]; break
        for enc in (encoding, 'utf-8', 'gbk', 'gb18030', 'gb2312', 'big5'):
            try:    return raw.decode(enc)
            except: pass
        return raw.decode('utf-8', errors='replace')

    def _text(self, code, msg):
        body = msg.encode()
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Expose-Headers', 'X-Final-Url')

    def log_message(self, *args):
        pass


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'


if __name__ == '__main__':
    ip = local_ip()
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'\n✓ 服务器已启动\n')
    print(f'  电脑浏览器:  http://localhost:{PORT}')
    print(f'  iPhone/iPad: http://{ip}:{PORT}')
    print(f'\n  iPhone 步骤: Safari 打开上方网址 → 分享 → 添加到主屏幕')
    print(f'  按 Ctrl+C 停止\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('已停止')
