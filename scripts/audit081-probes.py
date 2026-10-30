"""Historical audit entry point: run corrected 0.8.2 regressions."""
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
raise SystemExit(subprocess.call([sys.executable,"-m","pytest","backend/tests/test_v082_fixes.py","-q"],cwd=root))
