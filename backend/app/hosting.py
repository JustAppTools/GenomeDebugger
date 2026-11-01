"""Explicit public-preview mode; local installations remain loopback-only.

Anonymous visitors receive unguessable, signed browser workspace cookies. Their
SQLite files are separate and temporary; no local installation data is exposed.
"""
from contextvars import ContextVar
from contextlib import closing
from dataclasses import dataclass, field
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import shutil
import time
import sqlite3
from threading import RLock
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

REQUEST_DATABASE: ContextVar[Path | None] = ContextVar('request_database', default=None)
REQUEST_HOSTING: ContextVar['PublicHosting | None'] = ContextVar('request_hosting', default=None)
COOKIE = '__Host-genomedebugger-workspace'
IDENTIFIER = re.compile(r'^[0-9a-f]{64}$')


class HostingCapacityError(Exception):
    pass


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
    quota_lock: object = field(default_factory=RLock, repr=False)

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

    def allocated_bytes(self, excluding=None):
        # Rollback journals are transient and can vanish during enumeration.
        # Only committed workspace databases count toward the allocation budget.
        used = 0
        for folder in self.root.iterdir():
            if not IDENTIFIER.fullmatch(folder.name) or folder.is_symlink():
                continue
            path = folder / 'investigations.db'
            if path == excluding or path.is_symlink():
                continue
            try:
                used += path.stat().st_size
            except FileNotFoundError:
                continue
        return used

    def admit(self, identifier):
        # Called under quota_lock by storage, not when serving HTML or rejecting
        # a request. One process owns this public workspace root.
        self.root.mkdir(parents=True, exist_ok=True)
        now = time.time()
        self.cleanup(now)
        folder = self.root / identifier
        if folder.is_symlink() or folder.resolve().parent != self.root.resolve():
            raise ValueError('Invalid workspace directory')
        folders = [p for p in self.root.iterdir() if IDENTIFIER.fullmatch(p.name) and p.is_dir() and not p.is_symlink()]
        if not folder.exists() and len(folders) >= self.max_workspaces:
            raise HostingCapacityError()
        if not folder.exists() and self.allocated_bytes() >= self.total_bytes:
            raise HostingCapacityError()
        folder.mkdir(exist_ok=True)
        folder.touch(exist_ok=True)
        return folder / 'investigations.db'

    def guard_allocation(self, path, db, before):
        allocation = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
        # Reads, deletion and writes reusing existing pages remain possible at
        # capacity. Growing transactions are checked before commit and roll back.
        if allocation > before and self.allocated_bytes(excluding=path) + allocation > self.total_bytes:
            raise HostingCapacityError()

    def begin_request(self, identifier):
        with self.quota_lock:
            self.active[identifier] = self.active.get(identifier, 0) + 1
            return not (self.root / identifier / 'investigations.db').exists()

    def finish_request(self, identifier, new, failed):
        with self.quota_lock:
            self.active[identifier] -= 1
            if not self.active[identifier]:
                del self.active[identifier]
            folder = self.root / identifier
            if not folder.exists():
                return
            if new and failed and not self.active.get(identifier):
                path = folder / 'investigations.db'
                # A failed lookup can have initialized an empty schema. Do not
                # retain that slot; keep any useful records saved before failure.
                try:
                    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
                        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
                        empty = all(not db.execute('SELECT 1 FROM "' + table.replace('"', '""') + '" LIMIT 1').fetchone() for (table,) in tables)
                except sqlite3.Error:
                    empty = not path.exists() or path.stat().st_size == 0
                if empty:
                    if folder.resolve().parent != self.root.resolve() or folder.is_symlink():
                        raise ValueError('Invalid workspace directory')
                    shutil.rmtree(folder)
                    return
            folder.touch(exist_ok=True)

    async def handle(self, request, next_handler):
        if request.url.path == '/healthz' and request.method in {'GET', 'HEAD'}:
            return JSONResponse({'status': 'ok'})
        expected = urlsplit(self.origin)
        try:
            trusted = (request.url.hostname == expected.hostname and request.url.scheme == 'https'
                       and (request.url.port or 443) == (expected.port or 443))
        except ValueError:
            trusted = False
        if not trusted:
            return JSONResponse({'detail': 'Untrusted public origin'}, status_code=400)
        # Static assets have no workspace data. The HTML response establishes
        # the cookie before the application's parallel initial API requests.
        workspace_request = request.url.path.startswith('/api/') or request.url.path in {'/', '/index.html', '/docs', '/openapi.json', '/redoc'}
        if not workspace_request:
            return await next_handler(request)
        identifier = self.identify(request.cookies.get(COOKIE))
        fresh = identifier is None
        identifier = identifier or secrets.token_hex(32)
        database = self.root / identifier / 'investigations.db'
        if request.url.path.startswith('/api/'):
            new = await run_in_threadpool(self.begin_request, identifier)
            token = REQUEST_DATABASE.set(database)
            settings_token = REQUEST_HOSTING.set(self)
            response = None
            try:
                response = await next_handler(request)
            finally:
                REQUEST_DATABASE.reset(token)
                REQUEST_HOSTING.reset(settings_token)
                await run_in_threadpool(self.finish_request, identifier, new, response is None or response.status_code >= 400)
        else:
            response = await next_handler(request)
        if fresh:
            response.set_cookie(COOKIE, self.sign(identifier), max_age=7 * 24 * 3600,
                                secure=True, httponly=True, samesite='lax', path='/')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Vary'] = ', '.join(filter(None, [response.headers.get('Vary'), 'Cookie']))
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        return response
