"""Verify the corrected cross-port restore guard against an isolated source launcher."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]
def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]

with tempfile.TemporaryDirectory(prefix='genomedebugger-audit081-desktop-') as folder:
    data = Path(folder)
    port = free_port()
    other_port = free_port()
    while other_port == port:
        other_port = free_port()
    command = [sys.executable,str(ROOT/'scripts/desktop.py'),'--no-browser','--data-dir',str(data)]
    process = subprocess.Popen([*command,'--port',str(port)],cwd=ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=5) as client:
            for _ in range(80):
                if process.poll() is not None:
                    raise RuntimeError('Isolated source launcher exited')
                try:
                    details = client.get('/api/workspace/data').json()
                    if details.get('desktop_mode') and Path(details['database_path']) == data/'investigations.db':
                        break
                except (httpx.HTTPError,ValueError):
                    pass
                time.sleep(.25)
            else:
                raise RuntimeError('Isolated source launcher did not become ready')
            payload = client.get('/api/demos/transcript-switch').json()
            client.post('/api/investigations',json=payload).raise_for_status()
            source = data/'before-new-work.db'
            source.write_bytes(client.get('/api/workspace/backup').content)
            payload['title'] = 'New work made after backup'
            saved = client.post('/api/investigations',json=payload).json()
            assert client.get('/api/investigations/'+saved['id']).status_code == 200
            restore = subprocess.run([*command,'--port',str(other_port),'--restore-backup',str(source)],
                cwd=ROOT,capture_output=True,text=True,timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            assert restore.returncode != 0
            assert process.poll() is None
            assert client.get('/api/health').status_code == 200
            assert client.get('/api/investigations/'+saved['id']).status_code == 200
            assert not list(data.glob('investigations-before-restore-*.db'))
            assert 'Workspace is in use' in (data/'desktop.log').read_text(encoding='utf-8')
            client.post('/api/workspace/stop').raise_for_status();process.wait(timeout=10)
            offline=subprocess.run([*command,'--port',str(other_port),'--restore-backup',str(source)],
                cwd=ROOT,capture_output=True,text=True,timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            assert offline.returncode==0,offline.stderr
            assert list(data.glob('investigations-before-restore-*.db'))
            print(json.dumps({'probe':'restore_guard_follows_database_across_ports',
                'active_restore_rejected':True,'newer_record_preserved':True,
                'offline_restore_succeeded':True,'prior_copy_preserved':True}))
    finally:
        if process.poll() is None:
            try:
                httpx.post(f'http://127.0.0.1:{port}/api/workspace/stop',timeout=2)
                process.wait(timeout=10)
            except (httpx.HTTPError,subprocess.TimeoutExpired):
                process.terminate()
                process.wait(timeout=10)
