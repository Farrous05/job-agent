"""The job page server (python3 -m jobagent view).

- Local (default): http://127.0.0.1:8765, only this Mac can open it.
- --lan: also reachable from your phone on the same Wi-Fi, through a private link with a secret code
  (config/page_token, git-ignored). Requests without the code get "403".
- --autosave: commits and pushes your marks to GitHub a minute after you change something (for the
  always-on version installed by scripts/install_mac.sh).
"""
from __future__ import annotations

import http.server
import json
import re
import secrets
import socket
import threading
import urllib.parse
from pathlib import Path

from . import calendar_ics, cvtools, gitsave, pipeline, prep, report, tracker
from .store import SeenStore

# files the page may serve: CV PDFs and application drafts, nothing else on the disk
ALLOWED = [re.compile(r"^cv/build/[\w.\-]+\.(pdf|png)$"),
           re.compile(r"^applications/[\w.\-]+/(cover_letter\.pdf|answers\.md|checklist\.md|interview_prep\.md)$")]


def page_token(root: Path) -> str:
    f = root / "config" / "page_token"
    if f.exists() and f.read_text().strip():
        return f.read_text().strip()
    t = secrets.token_urlsafe(16)
    f.write_text(t + "\n")
    return t


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))          # no packet is sent; this just picks the Wi-Fi interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def phone_link(root: Path, port: int = 8765) -> str:
    return f"http://{lan_ip()}:{port}/?k={page_token(root)}"


def calendar_link(root: Path, port: int = 8765) -> str:
    return f"webcal://{lan_ip()}:{port}/calendar.ics?k={page_token(root)}"


class _Saver:
    """Debounced git save: one commit + push a minute after the last change."""
    def __init__(self, root: Path, delay: float = 60.0):
        self.root, self.delay, self.timer, self.lock = root, delay, None, threading.Lock()

    def touch(self):
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(self.delay, lambda: gitsave.save(self.root, "Job page marks"))
            self.timer.daemon = True
            self.timer.start()


def prep_states(root: Path) -> dict:
    st = {q["id"]: "queued" for q in prep.queued(root)}
    st.update({k: "ready" for k in prep.packs(root)})
    return st


def make_handler(root: Path, token: str | None, saver: _Saver | None):
    shortlist_dir = root / "shortlist"
    store_path = root / "seen_jobs.json"
    lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body, ctype: str = "text/html; charset=utf-8", headers: dict | None = None):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self, qs: dict) -> tuple[bool, dict]:
            """Local-only mode needs no code. LAN mode: ?k=<code> once, then a cookie."""
            if token is None or self.client_address[0] in ("127.0.0.1", "::1"):
                return True, {}                     # this Mac itself never needs the code
            if qs.get("k", [""])[0] == token:
                return True, {"Set-Cookie": f"jobagent={token}; Path=/; Max-Age=31536000; SameSite=Strict; HttpOnly"}
            cookie = self.headers.get("Cookie", "")
            return f"jobagent={token}" in cookie, {}

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(u.query)
            ok, extra = self._authorised(qs)
            if not ok:
                return self._send(403, "This page needs your private link (with ?k=…). Ask the bot: /page", "text/plain; charset=utf-8")
            fs = sorted(shortlist_dir.glob("*.md"), key=report.shortlist_key)
            store = SeenStore(store_path)
            rem = tracker.reminders(store)
            path = u.path
            if path == "/file":
                rel = qs.get("p", [""])[0]
                if not any(rx.match(rel) for rx in ALLOWED) or ".." in rel:
                    return self._send(404, "Not found", "text/plain; charset=utf-8")
                f = root / rel
                if not f.exists():
                    return self._send(404, "Not found", "text/plain; charset=utf-8")
                ctype = {".pdf": "application/pdf", ".png": "image/png"}.get(f.suffix, "text/plain; charset=utf-8")
                return self._send(200, f.read_bytes(), ctype, extra)
            if path == "/cv":
                n = cvtools.pending_changes(root)
                pdf = cvtools.changes_pdf(root) if n else None
                imgs = [f"cv/build/{p.name}" for p in cvtools.changes_images(root, pdf)] if pdf else []
                return self._send(200, report.cv_html(n, pdf is not None, list(cvtools.pdfs(root)),
                                                      cvtools.applications(root), qs.get("msg", [""])[0], imgs),
                                  headers=extra)
            if path == "/cv/diff":
                return self._send(200, cvtools.changes_text(root) or "No changes.", "text/plain; charset=utf-8", extra)
            if path == "/all":
                return self._send(200, report.all_matches_html(pipeline.latest_run(root / "data"), store.statuses(),
                                                               reminders=rem,
                                                               applied_companies=store.applied_companies()), headers=extra)
            if path == "/applied":
                cal = f"webcal://{self.headers.get('Host') or '127.0.0.1:8765'}/calendar.ics" + (f"?k={token}" if token else "")
                return self._send(200, report.applications_html(store.data["jobs"], reminders=rem,
                                                                preps=prep_states(root), calendar_url=cal),
                                  headers=extra)
            if path == "/calendar.ics":
                return self._send(200, calendar_ics.ics(root), "text/calendar; charset=utf-8",
                                  {**extra, "Content-Disposition": 'inline; filename="job-deadlines.ics"'})
            if path == "/prep":
                jid = qs.get("id", [""])[0]
                f = prep.find(root, jid)
                if not f:
                    return self._send(404, "No interview prep for that job yet.", "text/plain; charset=utf-8")
                return self._send(200, report.md_html(f.read_text(errors="replace"), "Interview prep"), headers=extra)
            if path == "/stats":
                return self._send(200, report.stats_html(tracker.stats(store)), headers=extra)
            if path in ("/", "/index.html") or path.startswith("/s/"):
                if not fs:
                    return self._send(200, "<p style='font-family:sans-serif;padding:20px'>No shortlist yet. Run a job "
                                           "search first (findjobs, or /run in Telegram).</p>", headers=extra)
                md = fs[-1] if not path.startswith("/s/") else next((f for f in fs if f.stem == path[3:]), None)
                if md is None:
                    return self._send(404, "Not found")
                return self._send(200, report.write_html(md, root / "data", None, fs, store.statuses(),
                                                         interactive=True, reminders=rem), headers=extra)
            return self._send(404, "Not found")

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            ok, _ = self._authorised(urllib.parse.parse_qs(u.query))
            if not ok:
                return self._send(403, "Forbidden", "text/plain; charset=utf-8")
            if u.path in ("/api/cv/accept", "/api/cv/reject", "/api/cv/build"):
                fn = {"/api/cv/accept": cvtools.accept, "/api/cv/reject": cvtools.reject,
                      "/api/cv/build": cvtools.build_pdfs}[u.path]
                with lock:
                    return self._send(200, fn(root), "text/plain; charset=utf-8")
            if u.path == "/api/prep":
                try:
                    body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 10_000)) or b"{}")
                    prep.enqueue(root, str(body["id"]), str(body.get("company", ""))[:200],
                                 str(body.get("title", ""))[:300], str(body.get("url", ""))[:1000])
                except (KeyError, ValueError, json.JSONDecodeError):
                    return self._send(400, "Bad request", "text/plain; charset=utf-8")
                return self._send(200, '{"ok": true}', "application/json")
            if u.path != "/api/status":
                return self._send(404, "Not found", "text/plain; charset=utf-8")
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(min(n, 10_000)) or b"{}")
                with lock:
                    store = SeenStore(store_path)
                    extra = {k: str(body[k])[:200] for k in ("deadline", "location") if body.get(k)}
                    if str(body.get("fit", "")).isdigit() and int(body["fit"]) > 0:
                        extra["fit"] = int(body["fit"])
                    note = body.get("note")
                    before = store.data["jobs"].get(str(body["id"]), {}).get("status")
                    store.set_status(str(body["id"]), body["status"], str(body.get("company", ""))[:200],
                                     str(body.get("title", ""))[:300], str(body.get("url", ""))[:1000],
                                     note=str(note) if note is not None else None, extra=extra)
                    store.save()
                    if body["status"] == "interviewing" and before != "interviewing":
                        prep.enqueue(root, str(body["id"]), str(body.get("company", ""))[:200],
                                     str(body.get("title", ""))[:300], str(body.get("url", ""))[:1000])
            except (KeyError, ValueError, json.JSONDecodeError):
                return self._send(400, "Bad request", "text/plain; charset=utf-8")
            if saver:
                saver.touch()
            self._send(200, '{"ok": true}', "application/json")

    return Handler


def serve(root: Path, port: int = 8765, lan: bool = False, autosave: bool = False, open_browser: bool = True):
    import webbrowser
    token = page_token(root) if lan else None
    saver = _Saver(root) if autosave else None
    host = "0.0.0.0" if lan else "127.0.0.1"
    try:
        srv = http.server.ThreadingHTTPServer((host, port), make_handler(root, token, saver))
    except OSError:
        # already running (e.g. the always-on page from install_mac.sh): just open it
        tf = root / "config" / "page_token"
        url = f"http://127.0.0.1:{port}/" + (f"?k={tf.read_text().strip()}" if tf.exists() else "")
        print(f"The job page is already running: {url}")
        if open_browser:
            webbrowser.open(url)
        return None
    local = f"http://127.0.0.1:{port}/" + (f"?k={token}" if token else "")
    print(f"Job page: {local}  (tabs: Top picks, All matches, My applications, CV, Stats)")
    if lan:
        print(f"On your phone (same Wi-Fi): {phone_link(root, port)}\n"
              "Keep that link private: it opens your job page.")
    print("Press Ctrl+C to stop." + (" Changes are saved to GitHub automatically." if autosave else ""))
    if open_browser:
        webbrowser.open(local)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Your marks are saved in seen_jobs.json.")
    return srv
