import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
MAKE = shutil.which("make") or "make"


def make(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHON_COLORS": "0"}  # CI sets FORCE_COLOR; 3.14's argparse would color --help
    return subprocess.run(
        [MAKE, "--no-print-directory", "-f", str(ROOT / "Makefile"), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_make_course_starts_the_tutorial_with_args():
    # --help exits before the menu, so nothing touches progress, feedback notes or the network.
    result = make("course", f"PYTHON={sys.executable}", "ARGS=--help")
    assert result.returncode == 0, result.stderr
    assert "usage: tutorial.py" in result.stdout and "--lesson" in result.stdout


def test_make_course_without_setup_says_what_to_run(tmp_path):
    result = make("course", f"PYTHON={tmp_path / 'missing' / 'python'}")
    assert result.returncode != 0
    assert "make setup" in result.stdout + result.stderr


def test_make_setup_refuses_a_python_older_than_3_11(tmp_path):
    # Stands in for Apple's python3 (3.9). Runs from tmp_path so setup can never touch the repo's .venv.
    old_python = tmp_path / "python3"
    old_python.write_text('#!/bin/sh\n[ "$1" = --version ] && echo "Python 3.9.6"\nexit 1\n')
    old_python.chmod(0o755)
    result = make("setup", f"SYSTEM_PYTHON={old_python}", cwd=tmp_path)
    assert result.returncode != 0
    out = result.stdout + result.stderr
    assert "Python 3.11 or newer" in out and "Python 3.9.6" in out
    assert "-m venv" not in out
