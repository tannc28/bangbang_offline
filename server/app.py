"""Bang Bang Private — HTTP + login + static + start policy/socket threads."""
from __future__ import annotations

import argparse
import os
import json
import logging
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
WWW = ROOT / "www"
DATA = ROOT / "data"

sys.path.insert(0, str(Path(__file__).resolve().parent))


from auth_store import Store
from storage_import import initialize
from storage import connection, SCHEMA_VERSION
from server_logging import configure, get_logger, LEVELS

log = get_logger('http')

STORE = Store()


import gzip
import threading
from collections import OrderedDict

_GZIP_LOCK = threading.Lock()
_GZIP_CACHE: OrderedDict[tuple[str, int, int], bytes] = OrderedDict()
_GZIP_CACHE_BYTES = 0
_GZIP_MAX_BYTES = 64 * 1024 * 1024
_GZIP_SUFFIXES = frozenset(('.json', '.js', '.css', '.html', '.svg', '.xml'))


def _cached_gzip(key: tuple[str, int, int], raw: bytes) -> bytes:
    global _GZIP_CACHE_BYTES
    with _GZIP_LOCK:
        hit = _GZIP_CACHE.get(key)
        if hit is not None:
            _GZIP_CACHE.move_to_end(key)
            return hit
    compressed = gzip.compress(raw, compresslevel=5)
    if len(compressed) <= _GZIP_MAX_BYTES // 2:
        with _GZIP_LOCK:
            existing = _GZIP_CACHE.get(key)
            if existing is not None:
                _GZIP_CACHE.move_to_end(key)
                return existing
            while _GZIP_CACHE and (_GZIP_CACHE_BYTES + len(compressed) > _GZIP_MAX_BYTES or len(_GZIP_CACHE) >= 96):
                _, evicted = _GZIP_CACHE.popitem(last=False)
                _GZIP_CACHE_BYTES = max(0, _GZIP_CACHE_BYTES - len(evicted))
            _GZIP_CACHE[key] = compressed
            _GZIP_CACHE_BYTES += len(compressed)
    return compressed


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WWW), **kwargs)

    def end_headers(self) -> None:
        path = urlparse(getattr(self, 'path', '')).path
        import admin_buff
        if admin_buff.page_path(path):
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'")
        elif path.endswith(('/', '.html', '.js', '.css', '.json')):
            # Code and pages revalidate on every load (a 304 when unchanged), so an
            # update shows up without a hard refresh. Images, audio and SWF stay cached.
            self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def _to_game(self) -> None:
        """The HTML5 client is the only game client; it has its own login."""
        self.send_response(302)
        self.send_header("Location", "/html5/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._to_game()
        import admin_buff
        if path.startswith('/api/admin/'):
            return admin_buff.handle(self)
        if admin_buff.page_path(path):
            if not admin_buff.protect_page(self):
                return
        super().do_HEAD()

    def log_message(self, fmt: str, *args) -> None:
        log.info('[http] ' + fmt, *args)

    def log_request(self, code='-', size='-') -> None:
        status = int(code) if str(code).isdigit() else 0
        level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
        if not log.isEnabledFor(level):
            return
        # Log status failures, including JSON responses that do not call send_error.
        # Avoid copying query tokens into persistent diagnostics.
        log.log(level, '[http] %s %s %s %s', self.command,
                urlparse(getattr(self, 'path', '')).path, code, size)

    def log_error(self, fmt: str, *args) -> None:
        # The status/path is recorded once by log_request().
        log.debug('[http] ' + fmt, *args)

    def _json(self, code: int, obj: dict, set_cookie: str | None = None, clear_cookie: bool = False) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        if clear_cookie:
            self.send_header(
                "Set-Cookie",
                "bb_web_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
            )
        elif set_cookie:
            self.send_header(
                "Set-Cookie",
                f"bb_web_session={set_cookie}; Path=/; Max-Age=86400; HttpOnly; SameSite=Lax",
            )
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return {}

    def _cookie(self) -> str | None:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == "bb_web_session":
                    return v
        return None

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        import admin_buff
        if path.startswith('/api/admin/'):
            return admin_buff.handle(self)
        if admin_buff.page_path(path):
            if not admin_buff.protect_page(self):
                return
        if path == "/html5/ws":
            from html5_bridge import handle_websocket
            session = STORE.session_from_cookie(self._cookie())
            return handle_websocket(self, session=session, store=STORE)
        if path == "/health":
            from cpp_backend import status as acceleration_status
            with connection() as db:
                db.execute('SELECT 1 FROM worlds LIMIT 1').fetchone()
            return self._json(200, {"ok": True, "service": "bangbang-private",
                                    "storage": "sqlite", "schema": SCHEMA_VERSION, "instance": os.environ.get("BB_LAUNCH_ID", ""),
                                    "combat_acceleration": acceleration_status()})
        from guild_protocol import HTTP_ROUTES
        from character_info import HTTP_ROUTES as CHARACTER_ROUTES
        if path.startswith("/capi") or path == "/goodsshopquery.php" or path.lstrip('/').lower() in HTTP_ROUTES | CHARACTER_ROUTES:
            from capi import handle

            hit = handle(self.path)
            if hit is None:
                self.send_error(404)
                return
            body, ctype = hit
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/", "/index.html"):
            return self._to_game()

        file_path = WWW / path.lstrip("/")
        if not file_path.exists():
            # Dynamically fetch & cache any missing asset from netzone mirror
            if path.startswith("/rez/") or path.endswith((".swf", ".png", ".jpg", ".dat", ".cub", ".xml")):
                try:
                    import urllib.request
                    import ssl
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    upstream_url = f"https://netzone.id.vn{path}"
                    req = urllib.request.Request(upstream_url, headers={"User-Agent": "Mozilla/5.0 BB-private-mirror"})
                    with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                        if resp.status == 200:
                            data = resp.read()
                            file_path.parent.mkdir(parents=True, exist_ok=True)
                            file_path.write_bytes(data)
                            log.info(f"[http] Proxy-cached {path} ({len(data)} bytes) from netzone")
                            self.send_response(200)
                            ctype = self.guess_type(str(file_path))
                            self.send_header("Content-Type", ctype)
                            self.send_header("Content-Length", str(len(data)))
                            self.end_headers()
                            self.wfile.write(data)
                            return
                except Exception:
                    pass

            if path.endswith(".xml"):
                log.warning(f"[http] Missing XML fallback for {path}")
                empty_xml = b'<?xml version="1.0" encoding="utf-8"?><config><localDatas></localDatas></config>'
                self.send_response(200)
                self.send_header("Content-Type", "application/xml; charset=utf-8")
                self.send_header("Content-Length", str(len(empty_xml)))
                self.end_headers()
                self.wfile.write(empty_xml)
                return

        if (file_path.is_file() and file_path.suffix.lower() in _GZIP_SUFFIXES
                and "Range" not in self.headers
                and WWW in file_path.resolve().parents):
            try:
                st = file_path.stat()
                etag = f'W/"{st.st_mtime_ns:x}-{st.st_size:x}"'
                if self.headers.get("If-None-Match") == etag:
                    self.send_response(304)
                    self.send_header("ETag", etag)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                accept_gz = "gzip" in (self.headers.get("Accept-Encoding") or "").lower()
                if accept_gz and st.st_size >= 1024:
                    raw = file_path.read_bytes()
                    gz = _cached_gzip((str(file_path), st.st_mtime_ns, st.st_size), raw)
                    self.send_response(200)
                    self.send_header("Content-Type", self.guess_type(str(file_path)))
                    self.send_header("Content-Encoding", "gzip")
                    self.send_header("Vary", "Accept-Encoding")
                    self.send_header("ETag", etag)
                    self.send_header("Content-Length", str(len(gz)))
                    self.end_headers()
                    self.wfile.write(gz)
                    return
            except OSError:
                pass

        return super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.startswith('/api/admin/'):
            import admin_buff
            return admin_buff.handle(self)
        if path in ('/api/bots/get','/api/bots/save'):
            session = STORE.session_from_cookie(self._cookie())
            if not session:
                return self._json(401,dict(success=False,message='Đăng nhập lại để thiết lập trận.'))
            from bot_setup import load_setup, save_setup, AI_TANKS
            try:
                import characters
                from storage import for_profile
                with for_profile(characters.for_username(session['username'])):
                    setup = save_setup(self._read_json()) if path.endswith('/save') else load_setup()
                return self._json(200,dict(success=True,setup=setup,tanks=list(AI_TANKS.values())))
            except ValueError as exc:
                return self._json(400,dict(success=False,message=str(exc)))
        if path == "/api/login":
            payload = self._read_json()
            result = STORE.login(str(payload.get("username") or ""), str(payload.get("password") or ""))
            if result.get("success"):
                cookie = result.pop("cookie")
                return self._json(200, result, set_cookie=cookie)
            return self._json(200, result, clear_cookie=True)
        if path == "/api/session":
            result = STORE.refresh_from_cookie(self._cookie())
            if result is None:
                return self._json(200, {"success": False}, clear_cookie=True)
            return self._json(200, result)
        if path == "/api/logout":
            STORE.logout_cookie(self._cookie())
            return self._json(200, {"success": True}, clear_cookie=True)
        if path == "/capi":
            return self._json(200, {"ok": True})
        self.send_error(404)


class Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        log.exception('[http] Request failed from %s', client_address)


def start_side_servers(native_port=49119) -> None:
    """Native game roles on loopback; the HTML5 WebSocket bridge connects to them."""
    import sixcube_server, html5_bridge
    sixcube_server.LISTEN_PORT = native_port
    html5_bridge.TCP_DESTINATION = ("127.0.0.1", native_port)
    sixcube_server.start_sixcube(bind="127.0.0.1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-port", type=int, default=49119)
    parser.add_argument("--port", type=int, default=18083)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument('--enable-admin-buff', action='store_true',
                        help='Explicitly enable loopback-only gift-mail admin; never grants on startup')
    parser.add_argument('--admin-key-file', type=Path,
                        help='Private key file outside www; contents are never printed or logged')
    parser.add_argument("--log-level", choices=LEVELS, default="WARNING", type=str.upper,
                        help="WARNING by default; DEBUG also records raw TCP packets")
    args = parser.parse_args()
    if args.admin_key_file and not args.enable_admin_buff:
        parser.error('--admin-key-file requires --enable-admin-buff')
    configure(args.log_level)
    from cpp_backend import initialize as initialize_acceleration
    initialize_acceleration()
    DATA.mkdir(parents=True, exist_ok=True)
    WWW.mkdir(parents=True, exist_ok=True)
    initialize()
    import characters
    characters.initialize()
    import guilds
    guilds.initialize()
    import offline_mail
    offline_mail.initialize()
    import world_boss_store
    world_boss_store.initialize()
    if args.enable_admin_buff:
        import admin_buff
        key_path = admin_buff.enable(args.admin_key_file)
        print('[admin] Local gift-mail admin: http://127.0.0.1:' + str(args.port) + '/admin/buff/')
        print('[admin] Operator key file (open locally, never share): ' + str(key_path))
    start_side_servers(args.native_port)

    Server.allow_reuse_address = True
    for attempt in range(5):
        try:
            httpd = Server((args.bind, args.port), Handler)
            break
        except OSError as e:
            log.warning(f"[http] bind attempt {attempt+1} failed: {e}, retrying...")
            time.sleep(1)
    else:
        log.error(f"[http] ERROR: Could not bind port {args.port}!")
        return

    log.info(f"[http] http://{args.bind}:{args.port}/  www={WWW}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("[http] stop")


if __name__ == "__main__":
    main()
