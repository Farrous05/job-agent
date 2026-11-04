"""CV actions shared by the job page and the Telegram bot: build PDFs, show suggested changes,
accept or reject them, list application drafts. Everything here runs git and LaTeX on YOUR Mac."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

BRANCH = "cv-edits"


def _run(root: Path, *cmd: str, env: dict | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), cwd=root, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, **(env or {})})


def build_pdfs(root: Path) -> str:
    """Compiles cv/cv.tex and every tailored CV into cv/build/ (one-page check)."""
    try:
        r = _run(root, "bash", "scripts/build_cv.sh")
    except (OSError, subprocess.SubprocessError) as e:
        return f"couldn't build: {e}"
    return (r.stdout or r.stderr).strip()


def pending_changes(root: Path) -> int:
    """Number of changed lines on the cv-edits branch compared with your current CV (0 = nothing waiting)."""
    for ref in (BRANCH, f"origin/{BRANCH}"):
        r = _run(root, "git", "diff", "--numstat", "HEAD", ref, "--", "cv/cv.tex")
        if r.returncode == 0:
            if not r.stdout.strip():
                return 0
            added, removed = (r.stdout.split() + ["0", "0"])[:2]
            return int(added or 0) + int(removed or 0)
    return 0


def changes_pdf(root: Path) -> Path | None:
    """Builds cv/build/cv-changes.pdf (red = removed, blue = added). None if nothing to show or it failed."""
    if not pending_changes(root):
        return None
    try:
        _run(root, "bash", "scripts/cv_diff.sh", env={"NO_OPEN": "1"})
    except (OSError, subprocess.SubprocessError):
        return None
    p = root / "cv" / "build" / "cv-changes.pdf"
    return p if p.exists() else None


def changes_images(root: Path, pdf: Path) -> list[Path]:
    """PNG pages of the changes PDF (phones can't show PDFs inside a page). Needs pdftoppm (poppler)."""
    for old in pdf.parent.glob("cv-changes-*.png"):
        old.unlink()
    try:
        _run(root, "pdftoppm", "-png", "-r", "110", str(pdf), str(pdf.parent / "cv-changes"))
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted(pdf.parent.glob("cv-changes-*.png"))


def changes_text(root: Path) -> str:
    r = _run(root, "git", "diff", "--word-diff", "HEAD", BRANCH, "--", "cv/cv.tex")
    return r.stdout if r.returncode == 0 else ""


def accept(root: Path) -> str:
    """Merges the suggested CV changes into your CV, rebuilds the PDFs and saves to GitHub."""
    if not pending_changes(root):
        return "No suggested CV changes to accept."
    dirty = _run(root, "git", "status", "--porcelain", "--", "cv/cv.tex").stdout.strip()
    if dirty:
        return ("cv/cv.tex has unsaved edits of your own, so I didn't merge. Save them first "
                "(python3 -m jobagent save) or undo them, then press Accept again.")
    m = _run(root, "git", "merge", "--no-edit", BRANCH)
    if m.returncode != 0:
        reason = (m.stderr or m.stdout).strip().splitlines()
        _run(root, "git", "merge", "--abort")
        return ("Couldn't merge automatically, so nothing changed. Git said: "
                + (" ".join(reason[:2])[:300] or "unknown error") + " Ask Claude to redo the CV review.")
    build = build_pdfs(root)
    from .gitsave import save
    return f"Accepted: CV updated. {build.splitlines()[0] if build else ''} GitHub: {save(root, 'Accept CV changes')}"


def reject(root: Path) -> str:
    """Throws the suggested CV changes away (your CV stays as it is)."""
    if not pending_changes(root):
        return "No suggested CV changes to reject."
    _run(root, "git", "branch", "-D", BRANCH)
    _run(root, "git", "push", "-q", "origin", "--delete", BRANCH)
    return "Rejected: the suggested changes were discarded. Your CV is unchanged."


def pdfs(root: Path) -> dict[str, Path]:
    """name -> PDF for the main CV and the tailored ones."""
    out = {}
    for p in sorted((root / "cv" / "build").glob("*.pdf")):
        if p.stem != "cv-changes":
            out[p.stem] = p
    return out


def applications(root: Path) -> list[dict]:
    """Each applications/<folder>/ with its cover letter PDF, answers and checklist (newest first)."""
    out = []
    base = root / "applications"
    for d in sorted((p for p in base.glob("*") if p.is_dir()), key=lambda p: -p.stat().st_mtime) if base.exists() else []:
        out.append({"name": d.name, "dir": d,
                    "letter": d / "cover_letter.pdf" if (d / "cover_letter.pdf").exists() else None,
                    "answers": (d / "answers.md").read_text() if (d / "answers.md").exists() else "",
                    "checklist": (d / "checklist.md").read_text() if (d / "checklist.md").exists() else ""})
    return out


def find_application(root: Path, query: str) -> dict | None:
    q = query.lower().replace(" ", "-")
    apps = applications(root)
    return next((a for a in apps if q in a["name"]), None)
