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
    boards = list(companies.get("board", []))
    have = {(b["ats"], b["token"].lower()) for b in boards}
    boards += [dict(company=d["company"], ats=d["ats"], token=d["token"], discovered=True)
               for d in pipeline.load_discovered(ROOT).values() if (d["ats"], d["token"].lower()) not in have]
    status = {}

    def one(b):
        fn = sources.FETCHERS[b["ats"]]
        kw = {k: v for k, v in b.items() if k not in ("company", "ats", "verified", "discovered")}
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
            key = f"{b['ats']}:{b['token'].lower()}" if b.get("discovered") else f"{b['ats']}:{b['token']}"
            status[key] = {"company": b["company"], "ok": err is None, "jobs": len(js), "error": err}
            if b.get("discovered"):
                status[key]["discovered"] = True
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

    n_disc = len(pipeline.load_discovered(ROOT))
    print(f"Fetching {len(companies.get('board', []))} boards + {n_disc} found automatically...")
    jobs, status = fetch_all(companies, cfg)
    for d in pipeline.update_discovered(ROOT, status):
        print(f"  dropped auto-found board after 3 failed runs: {d}")
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
    new_boards = pipeline.discover_boards(ROOT, kept, companies, run_date)
    if new_boards:
        print(f"  {len(new_boards)} new company boards found; the next run fetches all their roles: "
              + ", ".join(b["company"] for b in new_boards[:12]) + (" ..." if len(new_boards) > 12 else ""))

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
    if notify.get_telegram(ROOT):
        from . import bot
        html_msg += "\n\nButtons: 1–5 = the jobs above. Send /help for everything else."
        print(bot.send_summary(ROOT, title, html_msg, rows))
    else:
        print(notify.send(ROOT, title, msg, priority=prio, html_text=html_msg))
    return 0


def cmd_bot(_args) -> int:
    from . import bot
    try:
        bot.Bot(ROOT).loop()
    except KeyboardInterrupt:
        print("\nBot stopped.")
    return 0


def cmd_reset(args) -> int:
    """Start fresh without losing anything: archive shortlists, seen jobs, scores and run files; keep the jobs
    you've actually marked (applied / interviewing / offer / rejected / interested)."""
    import shutil
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    arch = ROOT / "archive" / stamp
    store = SeenStore(ROOT / "seen_jobs.json")
    keep_st = set(SeenStore.APPLIED) | {"interested"}
    keep = {} if args.all else {k: v for k, v in store.data["jobs"].items() if v.get("status") in keep_st}
    shortlists = sorted((ROOT / "shortlist").glob("*.md"))
    runs = sorted((ROOT / "data" / "runs").glob("*")) if (ROOT / "data" / "runs").exists() else []
    cache = ROOT / "data" / "score_cache.json"
    print(f"This will archive to {arch.relative_to(ROOT)}/:\n"
          f"  {len(shortlists)} shortlist files, {len(store.data['jobs'])} seen jobs, {len(runs)} run folders"
          + ("" if args.keep_scores else ", the score cache") + "\n"
          + ("and FORGET your marks too (--all; they stay in the archive).\n" if args.all else
             f"and keep {len(keep)} jobs you've marked (applied/interviewing/offer/rejected/interested).\n") +
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
    """The job page: Top picks, All matches, My applications, CV (accept/reject changes), Stats."""
    from . import server
    shortlist_dir = ROOT / "shortlist"
    files = sorted(shortlist_dir.glob("*.md"), key=report.shortlist_key)
    for f in files:                              # static copies (no buttons) for double-clicking
        report.write_html(f, ROOT / "data", f.with_suffix(".html"), files)
    if files:
        report.write_html(files[-1], ROOT / "data", shortlist_dir / "LATEST.html", files)
    if args.static:
        print(f"Wrote {shortlist_dir.relative_to(ROOT)}/LATEST.html" if files else "No shortlist yet.")
        return 0
    server.serve(ROOT, args.port, lan=args.lan, autosave=args.autosave, open_browser=not args.no_open)
    if not args.no_git and not args.autosave:
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


def cmd_calendar(_args) -> int:
    from . import calendar_ics
    from .server import calendar_link
    f = calendar_ics.write(ROOT)
    ev = calendar_ics.events(ROOT)
    print(f"{len(ev)} closing dates written to {f.relative_to(ROOT)}:")
    for e in ev[:20]:
        print(f"  {e['date']:%a %d %b}  {e['company']}: {e['title']}  ({e['why']})")
    print(f"Subscribe on your phone (updates by itself on home Wi-Fi; needs the always-on job page):\n  {calendar_link(ROOT)}\n"
          "On the Mac: open the file (double-click) to add them to Calendar once.")
    return 0


def cmd_boards(_args) -> int:
    found = pipeline.load_discovered(ROOT)
    st = {}
    if (ROOT / "data/source_status.json").exists():
        st = json.loads((ROOT / "data/source_status.json").read_text())["sources"]
    print(f"{len(found)} company boards found automatically (config/discovered_boards.json), fetched every run:")
    for k, b in sorted(found.items(), key=lambda x: x[1]["company"].lower()):
        s = st.get(k, {})
        print(f"  {b['company'][:34]:34} {k[:44]:44} {str(s.get('jobs', '-')):>5} jobs  since {b['added']}"
              + (f"  (failed {b['fails']}x)" if b.get("fails") else ""))
    print("To stop fetching one: add its slug to [discovery] skip in config/companies.toml.")
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
    rs.add_argument("--all", action="store_true", help="also forget the jobs you've marked (they stay in the archive)")
    ns = sub.add_parser("notify-setup", help="phone notifications: --telegram (recommended) or ntfy")
    ns.add_argument("--telegram", action="store_true")
    ns.add_argument("--token", help="Telegram bot token (otherwise you're asked for it)")
    nt = sub.add_parser("notify", help="send today's summary to your phone (or a custom message)")
    nt.add_argument("message", nargs="*")
    sub.add_parser("bot", help="run the Telegram bot (your phone remote)")
    sub.add_parser("calendar", help="closing dates as a calendar file + phone subscription link")
    sub.add_parser("boards", help="company boards found automatically from roles that passed your filters")
    sv = sub.add_parser("save", help="commit and push your results to GitHub")
    sv.add_argument("-m", "--message", default="Job agent results")
    vw = sub.add_parser("view")
    vw.add_argument("--no-open", action="store_true")
    vw.add_argument("--static", action="store_true", help="only write shortlist/*.html, no server")
    vw.add_argument("--port", type=int, default=8765)
    vw.add_argument("--no-git", action="store_true", help="don't commit and push your marks when you close it")
    vw.add_argument("--lan", action="store_true", help="also open it on your phone (same Wi-Fi) via a private link")
    vw.add_argument("--autosave", action="store_true", help="save to GitHub a minute after each change")
    args = ap.parse_args(argv)
    if args.cmd is None:
        args = ap.parse_args(["run"] + (argv or sys.argv[1:]))
    return {"run": cmd_run, "mark": cmd_mark, "status": cmd_status, "view": cmd_view, "import": cmd_import,
            "batches": cmd_batches, "merge-scores": cmd_merge, "recall": cmd_recall, "audit": cmd_audit, "reminders": cmd_reminders,
            "stats": cmd_stats, "save": cmd_save, "notify-setup": cmd_notify_setup, "notify": cmd_notify,
            "reset": cmd_reset, "bot": cmd_bot, "calendar": cmd_calendar, "boards": cmd_boards}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
