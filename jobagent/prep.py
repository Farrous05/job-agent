"""Interview prep packs: queued when you mark a job Interviewing (job page or bot); the Telegram bot runs
Claude's /prep for each queued job and sends you the pack. Files: applications/<folder>/interview_prep.md."""
from __future__ import annotations

import json
import re
from pathlib import Path

JOB_LINE = re.compile(r"<!--\s*job:\s*(.+?)\s*-->")


def queue_path(root: Path) -> Path:
    return root / "data" / "prep_queue.json"


def _load(root: Path) -> list[dict]:
    try:
        return json.loads(queue_path(root).read_text())
    except (OSError, json.JSONDecodeError):
        return []


def _save(root: Path, q: list[dict]) -> None:
    queue_path(root).parent.mkdir(exist_ok=True)
    queue_path(root).write_text(json.dumps(q, indent=1) + "\n")


def queued(root: Path) -> list[dict]:
    return _load(root)


def enqueue(root: Path, job_id: str, company: str, title: str, url: str = "") -> bool:
    """Adds a job to the prep queue unless it's already queued or already has a pack."""
    if find(root, job_id, company) or any(q["id"] == job_id for q in _load(root)):
        return False
    _save(root, _load(root) + [{"id": job_id, "company": company, "title": title, "url": url}])
    return True


def pop(root: Path) -> dict | None:
    q = _load(root)
    if not q:
        return None
    _save(root, q[1:])
    return q[0]


def packs(root: Path) -> dict[str, Path]:
    """job id -> interview_prep.md (from the file's first-line marker)."""
    out = {}
    for f in sorted((root / "applications").glob("*/interview_prep.md")):
        m = JOB_LINE.search(f.read_text(errors="replace")[:300])
        out[m.group(1) if m else f.parent.name] = f
    return out


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def find(root: Path, job_id: str = "", company: str = "") -> Path | None:
    p = packs(root)
    if job_id and job_id in p:
        return p[job_id]
    c = _slug(company)
    if c:
        return next((f for f in p.values() if f.parent.name.startswith(c)), None)
    return None


def prompt(root: Path, job: dict) -> str:
    body = (root / ".claude" / "commands" / "prep.md").read_text()
    parts = body.split("---", 2)
    arg = f"{job['company']}: {job['title']} (job id {job['id']}; {job.get('url', '')})"
    return ((parts[2] if len(parts) == 3 else body).replace("$ARGUMENTS", arg)
            + "\n\nYou're running unattended from my phone: don't ask questions, put them in the file as "
              "[ASK FARES: …] and in your final reply.")
