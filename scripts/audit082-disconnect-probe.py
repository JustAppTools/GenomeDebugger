"""Check real backup cancellation against an owned isolated loopback server."""
import json
from contextlib import closing
import os
from pathlib import Path
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.storage import initialize

if len(sys.argv)>1 and sys.argv[1]=='--serve':
    import uvicorn
    from app.main import app
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=int(sys.argv[2]),log_level='warning'))
    @app.post('/__audit_stop')
    def stop_owned_probe():
        server.should_exit=True
        return {'stopping':True}
    server.run()
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix='audit082-disconnect-',dir=ROOT/'.build') as folder:
    root=Path(folder).resolve();assert root.is_relative_to((ROOT/'.build').resolve())
    generated=root/'generated';generated.mkdir();database=root/'workspace.db';initialize(database)
    with closing(sqlite3.connect(database)) as db:
        db.execute('CREATE TABLE audit_padding(bytes BLOB)');db.execute('INSERT INTO audit_padding VALUES(zeroblob(24000000))');db.commit()
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    env={**os.environ,'GENOMEDEBUGGER_DB':str(database),'TEMP':str(generated),'TMP':str(generated)}
    with (root/'server.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            for _ in range(60):
                if process.poll() is not None:raise RuntimeError('Owned probe server exited')
                try:
                    if httpx.get(f'http://127.0.0.1:{port}/api/health',timeout=1).status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.2)
            else:raise RuntimeError('Owned probe server did not become ready')
            client=socket.socket();client.settimeout(5);client.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4096)
            client.connect(('127.0.0.1',port));client.sendall(f'GET /api/workspace/backup HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n'.encode())
            received=b''
            while b'SQLite format 3' not in received:
                chunk=client.recv(4096)
                if not chunk:raise RuntimeError('Probe did not receive the database response')
                received+=chunk
            client.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('HH' if os.name=='nt' else 'ii',1,0));client.close()
            time.sleep(2)
            retained=list(generated.glob('genomedebugger-backup-*/genomedebugger-backup.db'))
            print(json.dumps({'probe':'real_client_disconnected_mid_backup','response_bytes_received':len(received),
                'database_bytes':database.stat().st_size,'retained_temporary_backups':len(retained)},indent=2))
        finally:
            if process.poll() is None:
                try:httpx.post(f'http://127.0.0.1:{port}/__audit_stop',timeout=2)
                except httpx.HTTPError:pass
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate();process.wait(timeout=10)
