"""Run the regression checks replacing the original 0.8.0 audit probes.

Uses isolated pytest databases; does not touch the development workspace.
"""
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    raise SystemExit(subprocess.run([sys.executable, '-m', 'pytest', 'backend/tests/test_v081_fixes.py', '-q'], cwd=root).returncode)
