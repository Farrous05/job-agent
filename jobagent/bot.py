"""Telegram bot: your phone remote for the job agent. Runs on your Mac (python3 -m jobagent bot, or always-on
via scripts/install_mac.sh). It only answers YOUR chat (the one saved by notify-setup --telegram).

Commands: /jobs /all /cv /tailored /changes /letter <company> /apply <company> /interview <company> /prep <company>
          /calendar /run /page /reminders /stats /help
Interview prep: jobs marked Interviewing (here or on the job page) are queued in data/prep_queue.json; the bot
runs Claude's /prep for each one and sends you the pack.
Buttons: ✓ ★ ✕ under each job (Applied / Interested / Not for me), Accept / Reject under CV changes.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date
from pathlib import Path

from . import calendar_ics, cvtools, notify, pipeline, prep, report, tracker
from .store import SeenStore

HELP = """<b>Job agent</b>, your commands:
/jobs: today's top picks, with ✓ ★ ✕ buttons
/all: best unmarked roles from All matches (fit 4+)
/cv: your CV (PDF) · /tailored: tailored CVs
/changes: suggested CV changes (PDF) with Accept / Reject
/letter &lt;company&gt;: cover letter + answers you drafted
/apply &lt;company&gt;: Claude drafts the application, then sends you the cover letter
/interview &lt;company&gt;: mark it Interviewing + get an interview prep pack
/prep &lt;company&gt;: interview prep pack only
/calendar: closing dates in your phone's calendar
/run: start a full job search now (about 20 min), summary when done
/page: private link to the job page (home Wi-Fi)
/reminders · /stats"""

STATUS = {"a": ("applied", "✓ Applied"), "i": ("interested", "★ Interested"), "n": ("not_interested", "✕ Not for me")}


class Bot:
    def __init__(self, root: Path):
        self.root = root
        tg = notify.get_telegram(root)
        if not tg:
            raise SystemExit("Telegram isn't set up: run `python3 -m jobagent notify-setup --telegram` first.")
        self.token, self.chat = tg["token"], int(tg["chat_id"])
        self.map_file = root / "data" / "bot_map.json"
        self.busy: set[str] = set()

    # ----------------------------------------------------------------- Telegram API
    def api(self, method: str, params: dict, timeout: int = 30) -> dict:
        p = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
        data = urllib.parse.urlencode(p).encode()
        with urllib.request.urlopen(f"https://api.telegram.org/bot{self.token}/{method}", data=data,
                                    timeout=timeout) as r:
            return json.loads(r.read().decode())

    def text(self, html_text: str, buttons: list | None = None) -> None:
        params = {"chat_id": self.chat, "text": html_text[:4000], "parse_mode": "HTML",
                  "disable_web_page_preview": "true"}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        self.api("sendMessage", params)

    def document(self, path: Path, caption: str = "", buttons: list | None = None) -> None:
        boundary = uuid.uuid4().hex
        fields = {"chat_id": str(self.chat), "caption": caption[:1000], "parse_mode": "HTML"}
        if buttons:
            fields["reply_markup"] = json.dumps({"inline_keyboard": buttons})
        body = b""
        for k, v in fields.items():
            body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{path.name}\"\r\n"
                 f"Content-Type: application/octet-stream\r\n\r\n").encode() + path.read_bytes() + \
                f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/sendDocument", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()

    # ----------------------------------------------------------------- job buttons
    def _load_map(self) -> dict:
        try:
            return json.loads(self.map_file.read_text())
        except (OSError, ValueError):
            return {"n": 0, "jobs": {}}

    def _register(self, job: dict) -> str:
        m = self._load_map()
        m["n"] += 1
        key = str(m["n"])
        m["jobs"][key] = {k: job.get(k, "") for k in ("id", "company", "title", "url", "deadline", "location", "fit")}
        if len(m["jobs"]) > 2000:                       # keep the file small
            for old in sorted(m["jobs"], key=int)[:500]:
                del m["jobs"][old]
        self.map_file.parent.mkdir(exist_ok=True)
        self.map_file.write_text(json.dumps(m))
        return key

    def job_buttons(self, jobs: list[dict]) -> list:
        rows = []
        for i, j in enumerate(jobs, 1):
            k = self._register(j)
            rows.append([{"text": f"{i} ✓", "callback_data": f"s|{k}|a"},
                         {"text": f"{i} ★", "callback_data": f"s|{k}|i"},
                         {"text": f"{i} ✕", "callback_data": f"s|{k}|n"}])
        return rows

    def jobs_message(self, jobs: list[dict], title: str) -> tuple[str, list]:
        import html as h
        lines = [f"<b>{h.escape(title)}</b>", "Tap ✓ Applied · ★ Interested · ✕ Not for me", ""]
        for i, j in enumerate(jobs, 1):
            fit = f" · <b>{j['fit']}/5</b>" if j.get("fit") else ""
            lines.append(f"{i}. <a href=\"{h.escape(j['url'], quote=True)}\"><b>{h.escape(j['title'])}</b></a>\n"
                         f"   {h.escape(j['company'])} · {h.escape(j['location'][:40])}{fit}"
                         + (f"\n   <i>{h.escape(j['reason'][:120])}</i>" if j.get("reason") else ""))
        return "\n".join(lines), self.job_buttons(jobs)

    def top_picks(self, n: int = 8) -> list[dict]:
        fs = sorted((self.root / "shortlist").glob("*.md"), key=report.shortlist_key)
        if not fs:
            return []
        store = SeenStore(self.root / "seen_jobs.json")
        st = store.statuses()
        out = []
        for r in report.parse_shortlist(fs[-1]):
            j = report._job(r, {})
            if st.get(j["id"]) in (None, "reported"):
                out.append(j)
        return out[:n]

    def best_unmarked(self, n: int = 8, min_fit: int = 4) -> list[dict]:
        rd = pipeline.latest_run(self.root / "data")
        if rd is None or not (rd / "matches.json").exists():
            return []
        st = SeenStore(self.root / "seen_jobs.json").statuses()
        ms = json.loads((rd / "matches.json").read_text()).get("matches", [])
        out = [report._job(m, {}) for m in ms if m.get("fit", 0) >= min_fit and st.get(m["source_id"]) in (None, "reported")]
        return out[:n]

    # ----------------------------------------------------------------- commands
    def handle(self, update: dict) -> None:
        if "callback_query" in update:
            return self.on_button(update["callback_query"])
        msg = update.get("message") or {}
        if msg.get("chat", {}).get("id") != self.chat:
            return                                          # not you: ignore silently
        text = (msg.get("text") or "").strip()
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        try:
            self.command(cmd, arg.strip())
        except Exception as e:  # noqa: BLE001 - tell me instead of dying
            self.text(f"Something went wrong: <code>{type(e).__name__}: {str(e)[:200]}</code>")

    def command(self, cmd: str, arg: str) -> None:
        if cmd in ("/start", "/help", "help"):
            return self.text(HELP)
        if cmd == "/jobs":
            jobs = self.top_picks()
            if not jobs:
                return self.text("No unmarked top picks right now. /all shows the best of All matches, /run starts a search.")
            t, b = self.jobs_message(jobs, "Top picks")
            return self.text(t, b)
        if cmd == "/all":
            jobs = self.best_unmarked()
            if not jobs:
                return self.text("No unmarked fit-4+ roles in the latest run.")
            t, b = self.jobs_message(jobs, "Best unmarked roles (All matches, fit 4+)")
            return self.text(t, b)
        if cmd == "/cv":
            pdf = self.root / "cv" / "build" / "cv.pdf"
            if not pdf.exists():
                cvtools.build_pdfs(self.root)
            return self.document(pdf, "Your CV") if pdf.exists() else self.text("Couldn't build the CV PDF (LaTeX?).")
        if cmd == "/tailored":
            pdfs = {k: v for k, v in cvtools.pdfs(self.root).items() if k != "cv"}
            if not arg:
                if not pdfs:
                    return self.text("No tailored CVs yet.")
                return self.text("Tailored CVs (send <code>/tailored name</code>):\n" +
                                 "\n".join(f"• {n}" for n in pdfs))
            hit = next((p for n, p in pdfs.items() if arg.lower().replace(" ", "-") in n), None)
            return self.document(hit, hit.stem) if hit else self.text("No tailored CV matches that.")
        if cmd == "/changes":
            n = cvtools.pending_changes(self.root)
            if not n:
                return self.text("No suggested CV changes waiting.")
            pdf = cvtools.changes_pdf(self.root)
            buttons = [[{"text": "✓ Accept", "callback_data": "cv|a"}, {"text": "✕ Reject", "callback_data": "cv|r"}]]
            if pdf:
                return self.document(pdf, f"Suggested CV changes ({n} lines). Red = removed, blue = added.", buttons)
            return self.text(f"<pre>{cvtools.changes_text(self.root)[:3500]}</pre>", buttons)
        if cmd == "/letter":
            a = cvtools.find_application(self.root, arg) if arg else (cvtools.applications(self.root) or [None])[0]
            if not a:
                return self.text("No application draft matches that. Try /apply <company>.")
            return self.send_application(a)
        if cmd == "/apply":
            if not arg:
                return self.text("Which role? e.g. <code>/apply resonance</code>")
            return self.start_bg("apply", lambda: self.run_apply(arg), f"Drafting the application for <b>{arg}</b>… "
                                 "I'll send the cover letter in a few minutes.")
        if cmd in ("/prep", "/interview"):
            if not arg:
                return self.text(f"Which role? e.g. <code>{cmd} resonance</code>")
            job = self.find_tracked(arg)
            if not job:
                return self.text("I can't find that role among your jobs or the latest run. Try the company name.")
            if cmd == "/interview":
                st = SeenStore(self.root / "seen_jobs.json")
                st.set_status(job["id"], "interviewing", job["company"], job["title"], job["url"])
                st.save()
                self._schedule_save()
            have = prep.find(self.root, job["id"], job["company"])
            if have:
                return self.document(have, f"🎤 Interview prep: <b>{_html(job['company'])}</b> (already written)")
            prep.enqueue(self.root, job["id"], job["company"], job["title"], job["url"])
            if "interview prep" in self.busy:
                self.text("Queued: I'll start it when the current prep is done.")
            if cmd == "/interview":
                self.text(f"💬 Marked <b>{_html(job['company'])}</b> as Interviewing. Good luck!")
            return None                                     # the queue check right after sends "Writing…"
        if cmd == "/calendar":
            from .server import calendar_link
            f = calendar_ics.write(self.root)
            n = len(calendar_ics.events(self.root))
            self.text(f"📅 <b>{n} closing dates</b> (Interested jobs + unmarked fit 4+), alerts 3 days and 1 day before.\n"
                      f"<b>Best:</b> subscribe once, it updates by itself (on home Wi-Fi):\n{calendar_link(self.root)}\n"
                      "iPhone: Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar, "
                      "paste that link.\nOr open the file below to add them once.")
            return self.document(f, "Job deadlines")
        if cmd == "/run":
            return self.start_bg("run", self.run_search, "Starting a full job search (about 20 min). "
                                 "You'll get the summary here when it's done.")
        if cmd == "/page":
            from .server import phone_link
            return self.text(f"Job page (on your home Wi-Fi, keep it private):\n{phone_link(self.root)}")
        if cmd == "/reminders":
            r = tracker.reminders(SeenStore(self.root / "seen_jobs.json"))
            return self.text("\n".join(f"⏰ {x}" for x in r) or "No reminders: nothing closing soon, no follow-ups due.")
        if cmd == "/stats":
            return self.text(f"<pre>{tracker.stats_text(tracker.stats(SeenStore(self.root / 'seen_jobs.json')))}</pre>")
        return self.text("I didn't get that. /help lists what I can do.")

    def find_tracked(self, query: str) -> dict | None:
        """A job you've marked (interviewing/applied first), else the best match in the latest run."""
        q = query.lower()
        jobs = SeenStore(self.root / "seen_jobs.json").data["jobs"]
        rank = {"interviewing": 0, "applied": 1, "offer": 2, "interested": 3}
        hits = sorted(((rank.get(j.get("status"), 9), jid, j) for jid, j in jobs.items()
                       if q in f"{j.get('company', '')} {j.get('title', '')}".lower() or q == jid.lower()),
                      key=lambda x: x[0])
        if hits and hits[0][0] < 9:
            _, jid, j = hits[0]
            return {"id": jid, "company": j.get("company", ""), "title": j.get("title", ""), "url": j.get("url", "")}
        rd = pipeline.latest_run(self.root / "data")
        if rd and (rd / "matches.json").exists():
            for m in json.loads((rd / "matches.json").read_text()).get("matches", []):
                if q in f"{m.get('company', '')} {m.get('title', '')}".lower():
                    return {"id": m["source_id"], "company": m.get("company", ""), "title": m.get("title", ""),
                            "url": m.get("url", "")}
        if hits:
            _, jid, j = hits[0]
            return {"id": jid, "company": j.get("company", ""), "title": j.get("title", ""), "url": j.get("url", "")}
        return None

    def on_button(self, q: dict) -> None:
        if q.get("message", {}).get("chat", {}).get("id") != self.chat:
            return
        data = q.get("data", "")
        note = ""
        try:
            if data.startswith("s|"):
                _, key, code = data.split("|")
                job = self._load_map()["jobs"].get(key)
                if job and code in STATUS:
                    st = SeenStore(self.root / "seen_jobs.json")
                    extra = {k: job[k] for k in ("deadline", "location") if job.get(k)}
                    if isinstance(job.get("fit"), int) and job["fit"]:
                        extra["fit"] = job["fit"]
                    st.set_status(job["id"], STATUS[code][0], job["company"], job["title"], job["url"], extra=extra)
                    st.save()
                    note = f"{STATUS[code][1]}: {job['company']}"
                    self._schedule_save()
            elif data in ("cv|a", "cv|r"):
                note = (cvtools.accept if data == "cv|a" else cvtools.reject)(self.root)
        except Exception as e:  # noqa: BLE001
            note = f"Error: {e}"
        try:
            self.api("answerCallbackQuery", {"callback_query_id": q["id"], "text": note[:180]})
        except Exception:  # noqa: BLE001
            pass
        if data.startswith("cv|") and note:
            self.text(note)

    def _schedule_save(self):
        from .server import _Saver
        if not hasattr(self, "_saver"):
            self._saver = _Saver(self.root, delay=60)
        self._saver.touch()

    # ----------------------------------------------------------------- long jobs
    def start_bg(self, name: str, fn, started: str) -> None:
        if name in self.busy:
            return self.text(f"Already working on a {name}; I'll message you when it's done.")
        self.busy.add(name)
        self.text(started)

        def wrap():
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                self.text(f"The {name} failed: <code>{str(e)[:300]}</code>")
            finally:
                self.busy.discard(name)
        threading.Thread(target=wrap, daemon=True).start()

    def _claude(self, prompt: str, tools: list[str], timeout: int) -> str:
        env = {**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:/Library/TeX/texbin:" + os.environ.get("PATH", "")}
        r = subprocess.run(["claude", "-p", prompt, "--allowedTools", *tools, "--permission-mode", "acceptEdits"],
                           cwd=self.root, capture_output=True, text=True, timeout=timeout, env=env)
        return (r.stdout or r.stderr or "").strip()

    def run_apply(self, company: str) -> None:
        body = (self.root / ".claude" / "commands" / "apply.md").read_text()
        parts = body.split("---", 2)
        prompt = (parts[2] if len(parts) == 3 else body).replace("$ARGUMENTS", company)
        prompt += ("\n\nYou're running unattended from my phone: if several roles match, pick the best-scored one "
                   "and say which. Put every question for me in the final reply.")
        start = time.time()
        out = self._claude(prompt, ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "Bash(python3 -m jobagent:*)",
                                    "Bash(scripts/build_letter.sh:*)", "Bash(mkdir:*)", "Bash(cp:*)", "Bash(ls:*)",
                                    "Bash(cat:*)", "Edit(applications/**)"], timeout=1800)
        new = [a for a in cvtools.applications(self.root) if a["dir"].stat().st_mtime >= start - 5]
        if new:
            self.send_application(new[0])
            from .gitsave import save
            save(self.root, f"Application draft: {new[0]['name']}")
        self.text("<b>Claude:</b>\n" + _html(out[-3500:] or "(no reply)"))

    def send_application(self, a: dict) -> None:
        if a["letter"]:
            self.document(a["letter"], f"Cover letter: <b>{a['name']}</b>")
        for fname in ("answers.md", "checklist.md"):
            f = a["dir"] / fname
            if f.exists():
                self.document(f, fname)

    def run_prep(self, job: dict) -> None:
        out = self._claude(prep.prompt(self.root, job),
                           ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "Bash(mkdir:*)", "Bash(ls:*)",
                            "Bash(cat:*)", "Edit(applications/**)", "Write(applications/**)"], timeout=1800)
        f = prep.find(self.root, job["id"], job["company"])
        if f:
            self.document(f, f"🎤 Interview prep: <b>{_html(job['company'])}</b>. Also on the job page "
                             "(My applications).")
            from .gitsave import save
            save(self.root, f"Interview prep: {f.parent.name}")
        self.text("<b>Claude:</b>\n" + _html(out[-3000:] or "(no reply)"))

    def check_prep_queue(self) -> None:
        if "interview prep" in self.busy or not prep.queued(self.root):
            return
        job = prep.pop(self.root)
        if job:
            self.start_bg("interview prep", lambda: self.run_prep(job),
                          f"🎤 Writing the interview prep for <b>{_html(job['company'])}: {_html(job['title'])}</b> "
                          "(about 10 min).")

    def run_search(self) -> None:
        env = {**os.environ, "JOBAGENT_MODE": "claude", "JOBAGENT_TRIGGER": "Telegram /run"}
        subprocess.run(["bash", "scripts/run_scheduled.sh"], cwd=self.root, env=env, timeout=7200)
        # run_scheduled.sh sends the summary itself when it's done

    # ----------------------------------------------------------------- loop
    def loop(self) -> None:
        offset_file = self.root / "data" / "bot_offset"
        offset = int(offset_file.read_text()) if offset_file.exists() else 0
        print("Telegram bot running. Send /help to your bot. Ctrl+C to stop.")
        while True:
            try:
                ups = self.api("getUpdates", {"offset": offset, "timeout": 50}, timeout=65).get("result", [])
                for u in ups:
                    offset = u["update_id"] + 1
                    offset_file.parent.mkdir(exist_ok=True)
                    offset_file.write_text(str(offset))
                    self.handle(u)
                self.check_prep_queue()
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001 - network blips: wait and retry
                print(f"bot: {type(e).__name__}: {e}")
                time.sleep(5)


def _html(s: str) -> str:
    import html as h
    return h.escape(s)


def send_summary(root: Path, title: str, html_text: str, rows: list[dict]) -> str:
    """After a run: the rich summary with ✓ ★ ✕ buttons for the top jobs (needs Telegram)."""
    b = Bot(root)
    jobs = [report._job(r, {}) for r in rows[:5]]
    try:
        b.text(html_text, b.job_buttons(jobs) if jobs else None)
        return "sent (Telegram, with buttons)"
    except Exception as e:  # noqa: BLE001
        return f"couldn't send (Telegram): {e}"
