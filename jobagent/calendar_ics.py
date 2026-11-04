"""Closing dates as a calendar (.ics): subscribe once on your phone and deadlines appear with alerts.

Which jobs: marked Interested, plus unmarked roles in the latest run with Claude fit 4+, that have a
closing date that hasn't passed. Applied / Not for me jobs are left out (nothing left to do).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import pipeline
from .report import deadline_date
from .store import SeenStore

SKIP = {"not_interested", "applied", "interviewing", "offer", "rejected"}


def events(root: Path, min_fit: int = 4) -> list[dict]:
    store = SeenStore(root / "seen_jobs.json")
    sts = store.statuses()
    today = date.today()
    out: dict[str, dict] = {}
    for jid, j in store.data["jobs"].items():
        d = deadline_date(j.get("deadline") or "")
        if j.get("status") == "interested" and d and d >= today:
            out[jid] = {"id": jid, "company": j.get("company", ""), "title": j.get("title", ""),
                        "url": j.get("url", ""), "date": d, "why": "you marked it Interested",
                        "fit": j.get("fit")}
    rd = pipeline.latest_run(root / "data")
    if rd and (rd / "matches.json").exists():
        for m in json.loads((rd / "matches.json").read_text()).get("matches", []):
            sid = m.get("source_id", "")
            d = deadline_date(m.get("deadline") or "")
            if (sid in out or sts.get(sid) in SKIP or not d or d < today
                    or int(m.get("fit") or 0) < min_fit):
                continue
            out[sid] = {"id": sid, "company": m.get("company", ""), "title": m.get("title", ""),
                        "url": m.get("url", ""), "date": d, "why": f"Claude fit {m.get('fit')}/5, not marked yet",
                        "fit": m.get("fit")}
    return sorted(out.values(), key=lambda e: e["date"])


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines over 75 octets continue on the next line after a space."""
    b = line.encode()
    if len(b) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        e = ch.encode()
        if len(cur) + len(e) > (75 if not parts else 74):
            parts.append(cur.decode())
            cur = b""
        cur += e
    parts.append(cur.decode())
    return "\r\n ".join(parts)


def ics(root: Path) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//job-agent//deadlines//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Job deadlines", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
             "X-PUBLISHED-TTL:PT6H"]
    for e in events(root):
        uid = hashlib.sha1(e["id"].encode()).hexdigest()[:16] + "@job-agent"
        d = e["date"]
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_esc('Closes: ' + e['company'] + ' – ' + e['title'])}",
                  f"DESCRIPTION:{_esc(e['why'] + chr(10) + e['url'])}", f"URL:{_esc(e['url'])}",
                  "TRANSP:TRANSPARENT"]
        for trig, label in (("-P2DT15H", "3 days"), ("-PT15H", "tomorrow")):   # 09:00, 3 days / 1 day before
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:{trig}",
                      f"DESCRIPTION:{_esc(e['company'] + ' closes in ' + label)}", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def write(root: Path) -> Path:
    f = root / "data" / "deadlines.ics"
    f.parent.mkdir(exist_ok=True)
    f.write_text(ics(root), newline="")
    return f
