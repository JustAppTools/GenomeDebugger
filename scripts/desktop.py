"""Portable local launcher. No Node.js or separate Python installation at runtime."""
import argparse
import ctypes
import json
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser


def main():
    parser = argparse.ArgumentParser(description='GenomeDebugger local desktop workspace')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--restore-backup', type=Path)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a loopback port between 1024 and 65535')
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
    data = (args.data_dir or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'GenomeDebugger' / 'data').resolve()
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data / 'desktop.log', level=logging.INFO, encoding='utf-8')
    url = f'http://127.0.0.1:{args.port}'
    expected = (data / 'investigations.db').resolve()
    with socket.socket() as probe:
        occupied = probe.connect_ex(('127.0.0.1', args.port)) == 0
    if occupied:
        if args.restore_backup:
            raise RuntimeError('Stop this local application before restoring its database')
        try:
            with urllib.request.urlopen(url + '/api/workspace/data', timeout=2) as response:
                status = json.load(response)
            if Path(status['database_path']).resolve() != expected or not status.get('desktop_mode'):
                raise ValueError('Port belongs to a different workspace')
            if not args.no_browser:
                webbrowser.open(url)
            return
        except (urllib.error.URLError, ValueError, KeyError):
            raise RuntimeError(f'Port {args.port} is already in use. Close the other application or choose --port with another local port.')
    os.environ['GENOMEDEBUGGER_DB'] = str(expected)
    os.environ['GENOMEDEBUGGER_RESOURCES'] = str(root)
    os.environ['GENOMEDEBUGGER_STATIC_DIR'] = str(root / 'frontend' / 'dist')
    if not getattr(sys, 'frozen', False):
        sys.path.insert(0, str(root / 'backend'))
    if args.restore_backup:
        from app.manage import restore_backup
        previous = restore_backup(args.restore_backup, expected)
        logging.info('Database restored; previous copy: %s', previous)
        if sys.platform == 'win32' and not args.no_browser:
            ctypes.windll.user32.MessageBoxW(None, 'Backup restored. A previous database, if present, was preserved. Reopen GenomeDebugger to continue.', 'GenomeDebugger', 0)
        return
    import uvicorn
    from app.main import app
    from app.storage import backup
    if expected.is_file():
        # Preserve the pre-update database once per application release.
        from app.version import APP_VERSION
        destination = data / 'backups' / f'before-{APP_VERSION}.db'
        if not destination.exists():
            backup(expected, destination)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port, log_config=None,
                                         access_log=False, loop='asyncio', http='h11', ws='none'))
    app.state.desktop_server = server
    def ready():
        for _ in range(120):
            if server.started:
                if not args.no_browser:
                    webbrowser.open(url)
                return
            if server.should_exit:
                return
            time.sleep(.25)
    threading.Thread(target=ready, daemon=True).start()
    server.run()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        logging.exception('Desktop startup failed')
        if sys.platform == 'win32' and '--no-browser' not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, f'{exc}\n\nDetails are in the local GenomeDebugger desktop.log file.', 'GenomeDebugger could not start', 0x10)
        raise SystemExit(1)
