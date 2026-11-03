"""Markdown output for shortlist/YYYY-MM-DD.md."""
from __future__ import annotations

import re
from pathlib import Path

ID_LINE = re.compile(r"<!--\s*id:\s*(?P<id>[^|]+?)\s*\|\s*(?P<company>[^|]*?)\s*\|\s*(?P<title>[^|]*?)\s*\|\s*(?P<url>\S*)\s*-->")


def _cell(s: str) -> str:
    return (s or "—").replace("|", "/").replace("\n", " ").strip()


def write_shortlist(path: Path, run_date: str, rows: list[dict], notes: list[str]) -> None:
    """rows: dicts with keys source_id, title, company, location, url, deadline, sponsorship, why, applied, flags."""
    lines = [f"# Shortlist: {run_date}", "",
             f"{len(rows)} new roles. Ranked by CV fit, start-date fit, sponsorship clarity, then company.", "",
             "| # | Role | Company | Location | Deadline | Sponsorship | Why it fits | Link |",
             "|---|------|---------|----------|----------|-------------|-------------|------|"]
    for i, r in enumerate(rows, 1):
        company = r["company"] + (" **(already applied)**" if r.get("applied") else "")
        why = r.get("why", "")
        if r.get("flags"):
            why += " ⚠ " + "; ".join(r["flags"])
        lines.append(f"| {i} | {_cell(r['title'])} | {_cell(company)} | {_cell(r['location'])} | "
                     f"{_cell(r.get('deadline'))} | {_cell(r.get('sponsorship'))} | {_cell(why)} | "
                     f"[apply]({r['url']}) |")
    lines.append("")
    for r in rows:   # machine-readable ids, used by `python3 -m jobagent mark`
        lines.append(f"<!-- id: {r['source_id']} | {_cell(r['company'])} | {_cell(r['title'])} | {r['url']} -->")
    if notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def read_ids(path: Path) -> list[dict]:
    return [m.groupdict() for m in ID_LINE.finditer(path.read_text())]
