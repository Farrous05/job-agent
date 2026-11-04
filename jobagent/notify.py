"""Phone notifications. Two options (both git-ignored, set up with `python3 -m jobagent notify-setup`):
- Telegram (recommended, reliable on iPhone): your own private bot. Token + chat id in config/telegram.json.
- ntfy (https://ntfy.sh): no account; private random topic in config/ntfy_topic.
If Telegram is set up it's used; otherwise ntfy."""
from __future__ import annotations

import json
import secrets
import time
import urllib.parse
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


# --------------------------------------------------------------------------- Telegram
def telegram_file(root: Path) -> Path:
    return root / "config" / "telegram.json"


def get_telegram(root: Path) -> dict | None:
    f = telegram_file(root)
    try:
        d = json.loads(f.read_text()) if f.exists() else None
    except json.JSONDecodeError:
        return None
    return d if d and d.get("token") and d.get("chat_id") else None


def _tg(token: str, method: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=20) as r:
        return json.loads(r.read().decode())


def telegram_setup(root: Path, token: str) -> str:
    """Finds your chat id from the last message you sent the bot, then saves token + chat id."""
    token = token.strip()
    try:
        me = _tg(token, "getMe", {})
        if not me.get("ok"):
            return "That token didn't work. Copy it again from @BotFather."
        ups = _tg(token, "getUpdates", {}).get("result", [])
    except urllib.error.HTTPError as e:
        if e.code in (401, 404):
            return "That token didn't work. Copy it again from @BotFather (the whole line, like 123456:ABC-def...)."
        return f"Couldn't reach Telegram: {e}"
    except Exception as e:  # noqa: BLE001
        return f"Couldn't reach Telegram: {e}"
    chats = [u.get("message", {}).get("chat", {}) for u in ups if u.get("message")]
    chats = [c for c in chats if c.get("type") == "private"]
    if not chats:
        return (f"Bot @{me['result'].get('username')} found, but it has no message from you yet. Open Telegram, "
                f"send any message (e.g. 'hi') to @{me['result'].get('username')}, then run this again.")
    chat = chats[-1]
    telegram_file(root).write_text(json.dumps({"token": token, "chat_id": chat["id"]}) + "\n")
    return f"Saved. Notifications will go to {chat.get('first_name', 'you')} via @{me['result'].get('username')}."


def send_telegram(root: Path, title: str, message: str) -> str:
    tg = get_telegram(root)
    text = f"{title}\n{message}" if message else title
    try:
        r = _tg(tg["token"], "sendMessage", {"chat_id": tg["chat_id"], "text": text[:4000],
                                              "disable_web_page_preview": "true"})
        return "sent (Telegram)" if r.get("ok") else f"Telegram error: {r.get('description')}"
    except Exception as e:  # noqa: BLE001 - a failed notification must never break a run
        return f"couldn't send (Telegram): {e}"


def send(root: Path, title: str, message: str, click: str = "", priority: str = "default") -> str:
    if get_telegram(root):
        return send_telegram(root, title, message)
    t = get_topic(root)
    if not t:
        return "notifications not set up: run `python3 -m jobagent notify-setup --telegram` first"
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
