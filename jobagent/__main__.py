"""Job agent CLI.

  python3 -m jobagent run              fetch boards, filter, rank, write shortlist, mark seen
  python3 -m jobagent run --dry-run    same, but writes data/candidates/<date>.json only (no shortlist, no marking)
  python3 -m jobagent mark FILE.md     mark every job listed in a shortlist file as seen
  python3 -m jobagent status           show seen-job counts and last source errors
  python3 -m jobagent view             open the job page (Top picks, All matches, My applications, Stats)
  python3 -m jobagent import F.json    add roles found by web search / LinkedIn to today's run
  python3 -m jobagent batches          write scoring batches (roles Claude hasn't scored yet)
  python3 -m jobagent merge-scores     read Claude's scores -> All matches + shortlist
  python3 -m jobagent recall F.json    compare real postings from other boards with this run
  python3 -m jobagent audit            removed-but-relevant roles, for Claude to check the filters
  python3 -m jobagent reminders        deadlines closing soon, follow-ups due
  python3 -m jobagent stats            applications by stage, reply rate by role type/region/source
  python3 -m jobagent save             commit + push your results to GitHub
  python3 -m jobagent notify-setup     phone notifications (ntfy app), then: jobagent notify
"""
from __future__ import annotations

import argparse
import json
import sys
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 (e.g. macOS's built-in 3.9)
    sys.exit(f"job-agent needs Python 3.11 or newer; this is {sys.version.split()[0]}.\n"
             "On macOS: run `brew install python`, open a new Terminal window, check `python3 --version`.")
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from . import filters, pipeline, report, sources, tracker
from .store import SeenStore, fuzzy_key

ROOT = Path(__file__).resolve().parent.parent


def load_cfg(root: Path = ROOT) -> tuple[dict, dict]:
    with open(root / "config/profile.toml", "rb") as fh:
        profile = tomllib.load(fh)
    with open(root / "config/companies.toml", "rb") as fh:
        companies = tomllib.load(fh)
    return profile, companies


def fetch_all(companies: dict, cfg: dict) -> tuple[list[sources.Job], dict]:
    boards = companies.get("board", [])
    status = {}

    def one(b):
        fn = sources.FETCHERS[b["ats"]]
        kw = {k: v for k, v in b.items() if k not in ("company", "ats", "verified")}
        if b["ats"] == "workday":
            kw["title_prefilter"] = filters.title_prefilter(cfg)
        try:
            jobs = fn(b["company"], **kw)
            return b, jobs, None
        except sources.SourceError as e:
            return b, [], str(e)

    jobs: list[sources.Job] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for b, js, err in ex.map(one, boards):
            key = f"{b['ats']}:{b['token']}"
            status[key] = {"company": b["company"], "ok": err is None, "jobs": len(js), "error": err}
            jobs.extend(js)
    try:
        fh = sources.freehire(cfg)
        status["freehire"] = {"ok": True, "jobs": len(fh), "error": None}
        jobs.extend(fh)
    except sources.SourceError as e:
        status["freehire"] = {"ok": False, "jobs": 0, "error": str(e)}
    try:
        r = sources.reed(["graduate machine learning", "graduate software engineer", "graduate data scientist",
                          "graduate quantitative"])
        status["reed"] = {"ok": True, "jobs": len(r), "error": None if r else "REED_API_KEY not set"}
        jobs.extend(r)
    except sources.SourceError as e:
        status["reed"] = {"ok": False, "jobs": 0, "error": str(e)}
    return jobs, status


def cmd_run(args) -> int:
    cfg, companies = load_cfg()
    run_date = args.date or date.today().isoformat()
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    store = SeenStore(ROOT / "seen_jobs.json")

    print(f"Fetching {len(companies.get('board', []))} boards...")
    jobs, status = fetch_all(companies, cfg)
    (data / "source_status.json").write_text(json.dumps(
        {"run": datetime.now().isoformat(timespec="seconds"), "sources": status}, indent=2) + "\n")
    bad = [k for k, s in status.items() if not s["ok"]]
    print(f"  {len(jobs)} jobs fetched; {len(bad)} sources failed (see data/source_status.json)")

    for j in jobs:
        pipeline.normalize_company(j, companies)
    # same role from two sources (company board + aggregator): keep the first, boards come first
    uniq, keys = [], set()
    for j in jobs:
        k = fuzzy_key(j.company, j.title) + "|" + j.location.lower()[:20]
        if k not in keys:
            keys.add(k)
            uniq.append(j)
    jobs = uniq
    known = pipeline.known_companies(companies)
    kept, rows_all, excluded = pipeline.evaluate_all(jobs, cfg, store, known)
    rd = pipeline.run_dir(data, run_date)
    pipeline.save_run(rd, kept, rows_all, excluded, bad)
    cand = kept
    seen_n = sum(1 for c in kept if c.get("seen"))
    print(f"  {len(kept) - seen_n} new matching roles + {seen_n} shown before (all written to "
          f"{rd.relative_to(ROOT)}/candidates.json; only new ones can be shortlisted)")
    print("  excluded: " + ", ".join(f"{k}: {v}" for k, v in sorted(excluded.items(), key=lambda x: -x[1])))

    if args.dry_run:
        return 0
    rows = [c for c in cand if not c.get("seen")][: cfg["output"]["shortlist_size"]]
    notes = [f"Auto-ranked by keyword heuristic (no LLM). Run `/job-run` in Claude Code for a judged ranking."]
    if bad:
        notes.append(f"Failed sources: {', '.join(bad)}")
    out = report.next_shortlist_path(ROOT / "shortlist", run_date)
    report.write_shortlist(out, run_date, rows, notes)
    for r in rows:
        store.add(r["source_id"], r["company"], r["title"], r["url"], run=run_date)
    store.save()
    print(f"Shortlist: {out.relative_to(ROOT)} ({len(rows)} roles)")
    report.write_html(out, ROOT / "data", ROOT / "shortlist" / "LATEST.html", [])
    for line in tracker.reminders(store):
        print("  reminder: " + line)
    return 0


def _rd(args) -> Path:
    data = ROOT / "data"
    rd = pipeline.run_dir(data, args.date) if args.date else pipeline.latest_run(data)
    if rd is None or not (rd / "candidates.json").exists():
        sys.exit("No run yet today. Run `python3 -m jobagent run --dry-run` first.")
    return rd


def cmd_import(args) -> int:
    cfg, companies = load_cfg()
    rd = _rd(args)
    items = json.loads(Path(args.file).read_text())
    if isinstance(items, dict):
        items = items.get("jobs", [])
    store = SeenStore(ROOT / "seen_jobs.json")
    res = pipeline.import_jobs(items, cfg, store, pipeline.known_companies(companies), rd, companies)
    print(f"Imported {res['added']} of {res['received']} roles into {rd.relative_to(ROOT)}/candidates.json")
    if res["excluded"]:
        print("  excluded: " + ", ".join(f"{k}: {v}" for k, v in res["excluded"].items()))
    return 0


def cmd_batches(args) -> int:
    cfg, _ = load_cfg()
    rd = _rd(args)
    size = args.size or cfg.get("scoring", {}).get("batch_size", 25)
    cache = {} if args.rescore else pipeline.load_cache(ROOT / "data")
    cands = pipeline.load_candidates(rd)
    files = pipeline.make_batches(rd, cache, size)
    todo = sum(1 for c in cands if c["source_id"] not in cache)
    print(f"{len(cands)} roles in this run; {len(cands) - todo} already scored (cache), {todo} to score "
          f"in {len(files)} batch file(s):")
    for f in files:
        print(f"  {f.relative_to(ROOT)}")
    if not files:
        print("  none: run `python3 -m jobagent merge-scores`")
    return 0


def cmd_merge(args) -> int:
    cfg, _ = load_cfg()
    rd = _rd(args)
    store = SeenStore(ROOT / "seen_jobs.json")
    res = pipeline.merge_scores(rd, ROOT / "data", cfg, store, ROOT / "shortlist")
    print(f"Scored now: {res['scored_now']}. Matches: {res['matches']}. Shortlist: "
          f"{res['shortlist'].relative_to(ROOT)} ({res['shortlisted']} roles).")
    if res["problems"]:
        print("  problems in score files:\n    " + "\n    ".join(res["problems"][:20]))
    if res["unscored"]:
        print(f"  {len(res['unscored'])} roles have no score yet (run `batches` again to get them).")
    report.write_html(res["shortlist"], ROOT / "data", ROOT / "shortlist" / "LATEST.html", [])
    return 0


def cmd_recall(args) -> int:
    rd = _rd(args)
    bench = json.loads(Path(args.file).read_text())
    if isinstance(bench, dict):
        bench = bench.get("jobs", [])
    res = pipeline.recall(rd, bench)
    print(f"Recall: fetched {int(res['recall'] * 100)}% of {len(bench)} benchmark postings, kept "
          f"{int(res['kept_rate'] * 100)}%. Missing {len(res['missing'])}, filtered out {len(res['excluded'])}.")
    print(f"  details: {(rd / 'recall_report.md').relative_to(ROOT)}")
    hist = ROOT / "history" / "recall.csv"
    pipeline.record_recall(hist, rd, res, len(bench))
    rows = hist.read_text().splitlines()[1:]
    total = sum(int(r.split(",")[1]) for r in rows)
    avg = round(sum(int(r.split(",")[1]) * int(r.split(",")[2]) for r in rows) / max(total, 1))
    print(f"  all checks so far: {len(rows)} runs, {total} postings, {avg}% fetched (history/recall.csv)")
    return 0


def cmd_audit(args) -> int:
    rd = _rd(args)
    path = pipeline.audit(rd, args.n)
    n = path.read_text().count("\n## ")
    print(f"{n} removed-but-relevant roles to check: {path.relative_to(ROOT)}")
    return 0


def cmd_reminders(_args) -> int:
    store = SeenStore(ROOT / "seen_jobs.json")
    lines = tracker.reminders(store)
    print("\n".join(lines) if lines else "No reminders: nothing closing soon, no follow-ups due.")
    return 0


def cmd_save(args) -> int:
    from . import gitsave
    print("GitHub: " + gitsave.save(ROOT, args.message))
    return 0


def cmd_notify_setup(args) -> int:
    from . import notify
    if args.telegram:
        print("""Telegram setup (2 minutes):
1. In Telegram, open a chat with @BotFather, send /newbot, pick any name and a username ending in 'bot'.
2. BotFather replies with a token like 123456:ABC-def... Copy it.
3. Open the chat with YOUR new bot (BotFather gives a t.me link) and send it any message, e.g. "hi".""")
        token = args.token or input("4. Paste the token here and press Enter: ")
        print(notify.telegram_setup(ROOT, token))
        if notify.get_telegram(ROOT):
            print(notify.send(ROOT, "Job agent", "Notifications are set up. You'll get a summary after each run."))
        return 0
    t = notify.setup(ROOT)
    print(f"""Your private notification channel: {t}
1. Install the free "ntfy" app on your phone (App Store / Google Play).
2. In the app: tap +, Subscribe to topic, enter:  {t}
   (keep the default server ntfy.sh). Anyone who knows this name can read the messages, so don't share it.
3. Test it:  python3 -m jobagent notify "Hello from your job agent"
The name is saved in config/ntfy_topic (never pushed to GitHub).
(On iPhone, Telegram is more reliable: python3 -m jobagent notify-setup --telegram)""")
    return 0


def cmd_notify(args) -> int:
    from . import notify
    store = SeenStore(ROOT / "seen_jobs.json")
    if args.message:
        print(notify.send(ROOT, "Job agent", " ".join(args.message)))
        return 0
    fs = sorted((ROOT / "shortlist").glob("*.md"), key=report.shortlist_key)
    newest = fs[-1] if fs else None
    today = date.today().isoformat()
    rows = report.parse_shortlist(newest) if newest and newest.stem.startswith(today) else []
    counts = {}
    rd = pipeline.latest_run(ROOT / "data")
    if rd is not None and rd.name == today:
        try:
            st = json.loads((ROOT / "data" / "source_status.json").read_text())["sources"]
            counts["fetched"] = sum(v.get("jobs", 0) for v in st.values())
        except (OSError, ValueError, KeyError):
            pass
        if (rd / "matches.json").exists():
            ms = json.loads((rd / "matches.json").read_text()).get("matches", [])
            counts["scored"] = len(ms)
            counts["fits"] = {f: sum(1 for m in ms if m.get("fit") == f) for f in (5, 4, 3)}
    import subprocess
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--numstat", "HEAD", "cv-edits", "--", "cv/cv.tex"],
                          capture_output=True, text=True)
    if diff.returncode == 0 and diff.stdout.strip():
        counts["cv_changes"] = int(diff.stdout.split()[0] or 0)
    counts["tailored"] = sum(1 for f in (ROOT / "cv" / "tailored").glob("*.tex")
                             if date.fromtimestamp(f.stat().st_mtime).isoformat() == today)
    title, msg, html_msg, prio = notify.rich_summary(rows, tracker.reminders(store), counts)
    print(notify.send(ROOT, title, msg, priority=prio, html_text=html_msg))
    return 0


def cmd_reset(args) -> int:
    """Start fresh without losing anything: archive shortlists, seen jobs, scores and run files; keep the jobs
    you've actually marked (applied / interviewing / offer / rejected / interested)."""
    import shutil
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    arch = ROOT / "archive" / stamp
    store = SeenStore(ROOT / "seen_jobs.json")
    keep_st = set(SeenStore.APPLIED) | {"interested"}
    keep = {k: v for k, v in store.data["jobs"].items() if v.get("status") in keep_st}
    shortlists = sorted((ROOT / "shortlist").glob("*.md"))
    runs = sorted((ROOT / "data" / "runs").glob("*")) if (ROOT / "data" / "runs").exists() else []
    cache = ROOT / "data" / "score_cache.json"
    print(f"This will archive to {arch.relative_to(ROOT)}/:\n"
          f"  {len(shortlists)} shortlist files, {len(store.data['jobs'])} seen jobs, {len(runs)} run folders"
          + ("" if args.keep_scores else ", the score cache") + "\n"
          f"and keep {len(keep)} jobs you've marked (applied/interviewing/offer/rejected/interested).\n"
          "Your CV, tailored CVs, applications and settings are not touched.")
    if not args.yes and input("Go ahead? [y/N] ").strip().lower() != "y":
        print("Nothing changed.")
        return 1
    (arch / "shortlist").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "seen_jobs.json", arch / "seen_jobs.json")
    for f in shortlists + sorted((ROOT / "shortlist").glob("*.html")):
        shutil.move(str(f), arch / "shortlist" / f.name)
    local = ROOT / "data" / "archive" / stamp          # bulky run files stay out of git
    if runs:
        local.mkdir(parents=True, exist_ok=True)
        for r in runs:
            shutil.move(str(r), local / r.name)
    if cache.exists():
        shutil.copy(cache, arch / "score_cache.json")
        if not args.keep_scores:
            cache.unlink()
    store.data["jobs"] = keep
    store.save()
    print(f"Done. Archived to {arch.relative_to(ROOT)}/ (run files: {local.relative_to(ROOT)}/).\n"
          "Next: run `jobs` to watch a full run from scratch.")
    return 0


def cmd_stats(_args) -> int:
    store = SeenStore(ROOT / "seen_jobs.json")
    print(tracker.stats_text(tracker.stats(store)))
    return 0


def cmd_mark(args) -> int:
    store = SeenStore(ROOT / "seen_jobs.json")
    n = 0
    for f in args.files:
        run = Path(f).stem
        details = {r.get("id"): r for r in report.parse_shortlist(Path(f))}
        for r in report.read_ids(Path(f)):
            d = details.get(r["id"], {})
            extra = {k: v for k, v in (("deadline", d.get("deadline", "")), ("location", d.get("location", "")))
                     if v and v not in ("—", "Not stated")}
            if r["id"] not in store.data["jobs"]:
                n += 1
            store.add(r["id"], r["company"].replace(" **(already applied)**", ""), r["title"], r["url"], run=run,
                      extra=extra)
    store.save()
    print(f"Marked {n} new jobs as seen ({len(store.data['jobs'])} total).")
    return 0


def cmd_view(args) -> int:
    """Serves the shortlist pages on http://127.0.0.1:<port> (your computer only) so the Applied /
    Interested / Not for me buttons can save to seen_jobs.json. Also writes static shortlist/*.html."""
    import http.server
    import threading
    import webbrowser
    shortlist_dir = ROOT / "shortlist"
    files = sorted(shortlist_dir.glob("*.md"), key=report.shortlist_key)
    if not files:
        print("No shortlist yet. Run /job-run in Claude Code (or python3 -m jobagent run).")
        return 1
    store_path = ROOT / "seen_jobs.json"
    for f in files:                              # static copies (no buttons) for double-clicking
        report.write_html(f, ROOT / "data", f.with_suffix(".html"), files)
    report.write_html(files[-1], ROOT / "data", shortlist_dir / "LATEST.html", files)
    if args.static:
        print(f"Wrote {shortlist_dir.relative_to(ROOT)}/LATEST.html")
        return 0
    lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):               # keep the terminal quiet
            pass

        def _send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8"):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            fs = sorted(shortlist_dir.glob("*.md"), key=report.shortlist_key)
            store = SeenStore(store_path)
            rem = tracker.reminders(store)
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                md = fs[-1]
            elif path.startswith("/s/"):
                md = next((f for f in fs if f.stem == path[3:]), None)
                if md is None:
                    return self._send(404, "Not found")
            elif path == "/all":
                return self._send(200, report.all_matches_html(pipeline.latest_run(ROOT / "data"), store.statuses(),
                                                               reminders=rem))
            elif path == "/applied":
                return self._send(200, report.applications_html(store.data["jobs"], reminders=rem))
            elif path == "/stats":
                return self._send(200, report.stats_html(tracker.stats(store)))
            else:
                return self._send(404, "Not found")
            self._send(200, report.write_html(md, ROOT / "data", None, fs, store.statuses(), interactive=True,
                                              reminders=rem))

        def do_POST(self):
            if self.path != "/api/status":
                return self._send(404, "Not found", "text/plain")
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(min(n, 10_000)) or b"{}")
                with lock:
                    store = SeenStore(store_path)
                    extra = {k: str(body[k])[:200] for k in ("deadline", "location") if body.get(k)}
                    if str(body.get("fit", "")).isdigit() and int(body["fit"]) > 0:
                        extra["fit"] = int(body["fit"])
                    note = body.get("note")
                    store.set_status(str(body["id"]), body["status"], str(body.get("company", ""))[:200],
                                     str(body.get("title", ""))[:300], str(body.get("url", ""))[:1000],
                                     note=str(note) if note is not None else None, extra=extra)
                    store.save()
            except (KeyError, ValueError, json.JSONDecodeError):
                return self._send(400, "Bad request", "text/plain")
            self._send(200, '{"ok": true}', "application/json")

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Job page: {url}  (tabs: Top picks, All matches, My applications, Stats)\n"
          "Leave this window open while you use it. Press Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Your marks are saved in seen_jobs.json.")
    if not args.no_git:
        from . import gitsave
        print("GitHub: " + gitsave.save(ROOT, "Job page marks"))
    return 0


def cmd_status(_args) -> int:
    store = SeenStore(ROOT / "seen_jobs.json")
    print(f"seen jobs: {len(store.data['jobs'])}")
    p = ROOT / "data/source_status.json"
    if p.exists():
        s = json.loads(p.read_text())
        print(f"last fetch: {s['run']}")
        for k, v in s["sources"].items():
            if not v["ok"] or v.get("error"):
                print(f"  {k}: {v.get('error')}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jobagent")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--date")
    m = sub.add_parser("mark")
    m.add_argument("files", nargs="+")
    sub.add_parser("status")
    im = sub.add_parser("import", help="add roles found by web search / LinkedIn (JSON list)")
    im.add_argument("file")
    im.add_argument("--date")
    ba = sub.add_parser("batches", help="write scoring batches for Claude")
    ba.add_argument("--size", type=int)
    ba.add_argument("--rescore", action="store_true", help="ignore cached scores and score every role again")
    ba.add_argument("--date")
    me = sub.add_parser("merge-scores", help="combine Claude's scores: matches + shortlist")
    me.add_argument("--date")
    rc = sub.add_parser("recall", help="compare a benchmark list of real postings with this run")
    rc.add_argument("file")
    rc.add_argument("--date")
    au = sub.add_parser("audit", help="sample roles the filters removed, to check for wrong removals")
    au.add_argument("--n", type=int, default=40)
    au.add_argument("--date")
    sub.add_parser("reminders")
    sub.add_parser("stats")
    rs = sub.add_parser("reset", help="start fresh: archive shortlists, seen jobs and scores (keeps your marked jobs)")
    rs.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    rs.add_argument("--keep-scores", action="store_true", help="keep Claude's cached scores (faster rerun)")
    ns = sub.add_parser("notify-setup", help="phone notifications: --telegram (recommended) or ntfy")
    ns.add_argument("--telegram", action="store_true")
    ns.add_argument("--token", help="Telegram bot token (otherwise you're asked for it)")
    nt = sub.add_parser("notify", help="send today's summary to your phone (or a custom message)")
    nt.add_argument("message", nargs="*")
    sv = sub.add_parser("save", help="commit and push your results to GitHub")
    sv.add_argument("-m", "--message", default="Job agent results")
    vw = sub.add_parser("view")
    vw.add_argument("--no-open", action="store_true")
    vw.add_argument("--static", action="store_true", help="only write shortlist/*.html, no server")
    vw.add_argument("--port", type=int, default=8765)
    vw.add_argument("--no-git", action="store_true", help="don't commit and push your marks when you close it")
    args = ap.parse_args(argv)
    if args.cmd is None:
        args = ap.parse_args(["run"] + (argv or sys.argv[1:]))
    return {"run": cmd_run, "mark": cmd_mark, "status": cmd_status, "view": cmd_view, "import": cmd_import,
            "batches": cmd_batches, "merge-scores": cmd_merge, "recall": cmd_recall, "audit": cmd_audit, "reminders": cmd_reminders,
            "stats": cmd_stats, "save": cmd_save, "notify-setup": cmd_notify_setup, "notify": cmd_notify,
            "reset": cmd_reset}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
