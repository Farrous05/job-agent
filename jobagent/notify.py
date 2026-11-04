"""Phone notifications through ntfy (https://ntfy.sh): free, no account. Install the ntfy app on your phone
and subscribe to your private topic. The topic name lives in config/ntfy_topic (git-ignored): anyone who
knows it can read your messages, so it's a long random name."""
from __future__ import annotations

import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVER = "https://ntfy.sh"


def topic_file(root: Path) -> Path:
    return root / "config" / "ntfy_topic"


def get_topic(root: Path) -> str | None:
    f = topic_file(root)
    t = f.read_text().strip() if f.exists() else ""
    return t or None


def setup(root: Path) -> str:
    t = get_topic(root)
    if not t:
        t = "jobagent-" + secrets.token_urlsafe(18).replace("_", "x").replace("-", "y").lower()
        topic_file(root).write_text(t + "\n")
    return t


def send(root: Path, title: str, message: str, click: str = "", priority: str = "default") -> str:
    t = get_topic(root)
    if not t:
        return "no topic set: run `python3 -m jobagent notify-setup` first"
    req = urllib.request.Request(f"{SERVER}/{t}", data=message.encode("utf-8"), method="POST")
    req.add_header("Title", title.encode("ascii", "ignore").decode() or "Job agent")
    req.add_header("Tags", "briefcase")
    req.add_header("Priority", priority)
    if click:
        req.add_header("Click", click)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return "sent" if r.status == 200 else f"ntfy answered {r.status}"
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:      # rate limited: wait and retry
                time.sleep(10 * (attempt + 1))
                continue
            return f"couldn't send: {e}"
        except Exception as e:  # noqa: BLE001 - a failed notification must never break a run
            return f"couldn't send: {e}"
    return "couldn't send: rate limited"


def run_summary(shortlist: Path | None, rows: list[dict], reminders: list[str]) -> tuple[str, str, str]:
    """(title, message, priority) for the phone after a run."""
    lines = []
    if rows:
        for r in rows[:3]:
            fit = r["why"].split(":")[0] if "/5" in r["why"][:4] else ""
            lines.append(f"• {r['title'][:60]} · {r['company'].replace('**', '')[:30]}" + (f" ({fit})" if fit else ""))
    if reminders:
        lines.append("")
        lines += [f"⏰ {x}" for x in reminders[:3]]
    title = f"{len(rows)} new job{'s' if len(rows) != 1 else ''} picked" if rows else "Job agent: no new picks"
    urgent = any(x.startswith("Closes") for x in reminders)
    msg = "\n".join(lines) or "Nothing new today."
    return title, msg, "high" if urgent else "default"
