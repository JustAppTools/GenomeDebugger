"""Run the public preview behind the host's HTTPS ingress, without local data."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

if __name__ == '__main__':
    if os.environ.get('GENOMEDEBUGGER_DEPLOYMENT') != 'public-free':
        raise SystemExit('Set GENOMEDEBUGGER_DEPLOYMENT=public-free for this entry point')
    os.environ.setdefault('GENOMEDEBUGGER_RESOURCES', str(ROOT))
    os.environ.setdefault('GENOMEDEBUGGER_STATIC_DIR', str(ROOT / 'frontend' / 'dist'))
    import uvicorn
    from app.main import app
    port = int(os.environ.get('PORT', '10000'))
    if not 1 <= port <= 65535:
        raise SystemExit('PORT must be between 1 and 65535')
    # Render terminates HTTPS at its ingress and supplies forwarded headers.
    # This entry point is for that ingress, with an exact public-origin check.
    uvicorn.run(app, host='0.0.0.0', port=port, workers=1, proxy_headers=True,
                forwarded_allow_ips='*', access_log=False, ws='none')
