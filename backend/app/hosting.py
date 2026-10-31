"""Explicit public-preview mode; local installations remain loopback-only.

Anonymous visitors receive unguessable, signed browser workspace cookies. Their
SQLite files are separate and temporary; no local installation data is exposed.
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import shutil
import time
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

REQUEST_DATABASE: ContextVar[Path | None] = ContextVar('request_database', default=None)
COOKIE = '__Host-genomedebugger-workspace'
IDENTIFIER = re.compile(r'^[0-9a-f]{64}$')


@dataclass
class PublicHosting:
    enabled: bool = False
    origin: str = ''
    secret: bytes = b''
    root: Path = Path('/tmp/genomedebugger-workspaces')
    max_workspaces: int = 200
    total_bytes: int = 256 * 1024 * 1024
    idle_seconds: int = 24 * 60 * 60
    active: dict[str, int] = field(default_factory=dict)
    epoch: str = field(default_factory=lambda: secrets.token_hex(16))
    last_cleanup: float = 0

    @classmethod
    def from_environment(cls):
        mode = os.environ.get('GENOMEDEBUGGER_DEPLOYMENT', 'local')
        if mode == 'local':
            return cls()
        if mode != 'public-free':
            raise ValueError('GENOMEDEBUGGER_DEPLOYMENT must be local or public-free')
        origin = os.environ.get('GENOMEDEBUGGER_PUBLIC_ORIGIN', os.environ.get('RENDER_EXTERNAL_URL', '')).rstrip('/')
        parsed = urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError('Public deployment requires an exact HTTPS public origin')
        secret = os.environ.get('GENOMEDEBUGGER_SESSION_SECRET', '').encode('utf-8')
        if len(secret) < 32:
            raise ValueError('Public deployment requires a session secret of at least 32 bytes')
        return cls(enabled=True, origin=origin, secret=secret,
                   root=Path(os.environ.get('GENOMEDEBUGGER_WORKSPACES_DIR', '/tmp/genomedebugger-workspaces')).resolve())

    def metadata(self):
        return {'hosted': self.enabled, 'storage': 'temporary' if self.enabled else 'local',
                'workspace_epoch': self.epoch if self.enabled else None,
                'idle_hours': self.idle_seconds // 3600 if self.enabled else None}

    def sign(self, identifier):
        signature = hmac.new(self.secret, identifier.encode('ascii'), hashlib.sha256).hexdigest()
        return identifier + '.' + signature

    def identify(self, cookie):
        if isinstance(cookie, str) and len(cookie) == 129:
            identifier, _, signature = cookie.partition('.')
            if IDENTIFIER.fullmatch(identifier) and IDENTIFIER.fullmatch(signature) and hmac.compare_digest(self.sign(identifier), cookie):
                return identifier
        return None

    def cleanup(self, now):
        if now - self.last_cleanup < 60:
            return
        self.last_cleanup = now
        root = self.root.resolve()
        for folder in root.iterdir():
            if (not IDENTIFIER.fullmatch(folder.name) or folder.is_symlink() or not folder.is_dir()
                    or folder.resolve().parent != root or self.active.get(folder.name)):
                continue
            if now - folder.stat().st_mtime > self.idle_seconds:
                # Only server-created expired visitor directories under this
                # verified root are removed. Active requests retain their files.
                try:
                    shutil.rmtree(folder)
                except OSError:
                    pass

    def admit(self, identifier, writing):
        self.root.mkdir(parents=True, exist_ok=True)
        now = time.time()
        self.cleanup(now)
        folder = self.root / identifier
        if folder.is_symlink() or folder.resolve().parent != self.root.resolve():
            raise ValueError('Invalid workspace directory')
        folders = [p for p in self.root.iterdir() if IDENTIFIER.fullmatch(p.name) and p.is_dir() and not p.is_symlink()]
        if not folder.exists() and len(folders) >= self.max_workspaces:
            return None
        if writing or not folder.exists():
            used = sum(p.stat().st_size for directory in folders for p in directory.iterdir() if p.is_file() and not p.is_symlink())
            if used >= self.total_bytes:
                return None
        folder.mkdir(exist_ok=True)
        folder.touch(exist_ok=True)
        return folder / 'investigations.db'

    async def handle(self, request, next_handler):
        if request.url.path == '/healthz' and request.method in {'GET', 'HEAD'}:
            return JSONResponse({'status': 'ok'})
        expected = urlsplit(self.origin)
        if (request.url.hostname != expected.hostname or request.url.scheme != 'https'
                or (request.url.port or 443) != (expected.port or 443)):
            return JSONResponse({'detail': 'Untrusted public origin'}, status_code=400)
        # Static assets have no workspace data. The HTML response establishes
        # the cookie before the application's parallel initial API requests.
        workspace_request = request.url.path.startswith('/api/') or request.url.path in {'/', '/index.html', '/docs', '/openapi.json', '/redoc'}
        if not workspace_request:
            return await next_handler(request)
        identifier = self.identify(request.cookies.get(COOKIE))
        fresh = identifier is None
        identifier = identifier or secrets.token_hex(32)
        database = self.admit(identifier, request.method not in {'GET', 'HEAD', 'OPTIONS'})
        if database is None:
            return JSONResponse({'detail': 'The free preview is at capacity. Existing visitors can download their work; please try again later.'}, status_code=503,
                                headers={'Cache-Control': 'no-store', 'Retry-After': '60'})
        self.active[identifier] = self.active.get(identifier, 0) + 1
        token = REQUEST_DATABASE.set(database)
        try:
            response = await next_handler(request)
        finally:
            REQUEST_DATABASE.reset(token)
            self.active[identifier] -= 1
            if not self.active[identifier]:
                del self.active[identifier]
            if database.parent.exists():
                database.parent.touch(exist_ok=True)
        if fresh:
            response.set_cookie(COOKIE, self.sign(identifier), max_age=7 * 24 * 3600,
                                secure=True, httponly=True, samesite='lax', path='/')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Vary'] = ', '.join(filter(None, [response.headers.get('Vary'), 'Cookie']))
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        return response
