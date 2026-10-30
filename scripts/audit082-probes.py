"""Historical audit entry point: run corrected 0.8.3 backend regressions."""
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
raise SystemExit(subprocess.call([sys.executable,'-m','pytest','backend/tests/test_v083_fixes.py','-q'],cwd=root))
