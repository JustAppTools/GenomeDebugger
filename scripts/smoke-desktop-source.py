"""Exercise the local desktop entry point against isolated, disposable test data."""
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import httpx

root = Path(__file__).resolve().parents[1]
data = root / '.build' / ('desktop-smoke-' + uuid.uuid4().hex[:8])
data.mkdir(parents=True)
process = subprocess.Popen([sys.executable, str(root/'scripts/desktop.py'), '--no-browser', '--port','8766','--data-dir',str(data)],
                           cwd=root, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
owned = False
try:
    with httpx.Client(base_url='http://127.0.0.1:8766',timeout=2) as client:
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError('Source desktop launcher exited: '+(data/'desktop.log').read_text())
            try:
                info = client.get('/api/workspace/data').json()
                if Path(info.get('database_path','')).resolve() == (data/'investigations.db').resolve() and info.get('desktop_mode'):
                    owned=True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.25)
        if not owned:
            raise RuntimeError('The isolated desktop server did not become ready')
        assert client.get('/').status_code == 200
        demo=client.get('/api/demos/transcript-switch').json()
        result=client.post('/api/investigations',json=demo)
        result.raise_for_status()
        assert result.json()['identity']['status']=='verified'
        assert client.get('/api/workspace/backup').content.startswith(b'SQLite format 3')
        print('Source desktop launcher: built UI, comparison, backup, and application stop verified in '+str(data))
        client.post('/api/workspace/stop').raise_for_status()
        owned=False
    process.wait(timeout=10)
    assert process.returncode==0
finally:
    if owned:
        try:
            httpx.post('http://127.0.0.1:8766/api/workspace/stop',timeout=2)
        except httpx.HTTPError:
            pass
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
