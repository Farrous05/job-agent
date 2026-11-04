"""Save your results to GitHub automatically (commit + push), so you don't have to remember to."""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def save(root: Path, message: str, push: bool = True) -> str:
    """Commits every change git doesn't ignore and pushes it. Returns a one-line status. Never raises."""
    try:
        if _git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
            return "not a git repo: nothing saved"
        _git(root, "add", "-A")
        if _git(root, "diff", "--cached", "--quiet").returncode == 0:
            return "nothing new to save"
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        c = _git(root, "commit", "-q", "-m", f"{message} ({stamp})")
        if c.returncode != 0:
            return "commit failed: " + (c.stderr or c.stdout).strip()[:200]
        if not push:
            return "saved locally"
        _git(root, "pull", "-q", "--no-rebase", "--no-edit")
        p = _git(root, "push", "-q")
        return "saved and pushed to GitHub" if p.returncode == 0 else \
            "saved locally; push failed: " + p.stderr.strip()[:200]
    except (OSError, subprocess.SubprocessError) as e:
        return f"couldn't save: {e}"
