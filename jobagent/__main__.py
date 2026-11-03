"""Job agent CLI.

  python3 -m jobagent run              fetch boards, filter, rank, write shortlist, mark seen
  python3 -m jobagent run --dry-run    same, but writes data/candidates/<date>.json only (no shortlist, no marking)
  python3 -m jobagent mark FILE.md     mark every job listed in a shortlist file as seen
  python3 -m jobagent status           show seen-job counts and last source errors
  python3 -m jobagent view             build shortlist/*.html pages and open the newest in your browser
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from . import filters, report, sources
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

    # same role from two sources (company board + aggregator): keep the first, boards come first
    uniq, keys = [], set()
    for j in jobs:
        k = fuzzy_key(j.company, j.title) + "|" + j.location.lower()[:20]
        if k not in keys:
            keys.add(k)
            uniq.append(j)
    jobs = uniq
    known = {b["company"].lower() for b in companies.get("board", [])} | \
            {w["company"].lower() for w in companies.get("watch", [])}
    kept, excluded = [], {}
    for j in jobs:
        v = filters.evaluate(j, cfg)
        if not v.keep:
            for r in v.reasons[:1]:
                excluded[r] = excluded.get(r, 0) + 1
            continue
        if store.seen(j.source_id, j.company, j.title):
            excluded["already reported"] = excluded.get("already reported", 0) + 1
            continue
        kept.append((v, j))
    kept.sort(key=lambda x: -x[0].score)

    pool = kept[: cfg["output"]["candidates_size"]]
    cand = [{**j.to_dict(), "description": j.description[:4000], "score": v.score, "region": v.region,
             "sponsorship": v.sponsorship, "why": v.why, "flags": v.flags, "internship": v.internship,
             "applied": filters.is_applied(j.company, cfg),
             "new_company": not any(k in j.company.lower() or j.company.lower() in k for k in known)}
            for v, j in pool]
    cdir = data / "candidates"
    cdir.mkdir(exist_ok=True)
    (cdir / f"{run_date}.json").write_text(json.dumps(
        {"run": run_date, "excluded_counts": excluded, "failed_sources": bad, "candidates": cand},
        indent=2, ensure_ascii=False) + "\n")
    print(f"  {len(kept)} new matching roles; top {len(cand)} written to data/candidates/{run_date}.json")
    print(f"  excluded: {excluded}")

    if args.dry_run:
        return 0
    rows = cand[: cfg["output"]["shortlist_size"]]
    notes = [f"Auto-ranked by keyword heuristic (no LLM). Run `/job-run` in Claude Code for a judged ranking."]
    if bad:
        notes.append(f"Failed sources: {', '.join(bad)}")
    out = ROOT / "shortlist" / f"{run_date}.md"
    report.write_shortlist(out, run_date, rows, notes)
    for r in rows:
        store.add(r["source_id"], r["company"], r["title"], r["url"], run=run_date)
    store.save()
    print(f"Shortlist: {out.relative_to(ROOT)} ({len(rows)} roles)")
    report.write_html(out, ROOT / "data", ROOT / "shortlist" / "LATEST.html", [])
    return 0


def cmd_mark(args) -> int:
    store = SeenStore(ROOT / "seen_jobs.json")
    n = 0
    for f in args.files:
        run = Path(f).stem
        for r in report.read_ids(Path(f)):
            if r["id"] not in store.data["jobs"]:
                store.add(r["id"], r["company"].replace(" **(already applied)**", ""), r["title"], r["url"], run=run)
                n += 1
    store.save()
    print(f"Marked {n} new jobs as seen ({len(store.data['jobs'])} total).")
    return 0


def cmd_view(args) -> int:
    files = sorted((ROOT / "shortlist").glob("*.md"), key=lambda f: f.stat().st_mtime)
    if not files:
        print("No shortlist yet. Run /job-run in Claude Code (or python3 -m jobagent run).")
        return 1
    for f in files:
        report.write_html(f, ROOT / "data", f.with_suffix(".html"), files)
    newest = files[-1].with_suffix(".html")
    latest = ROOT / "shortlist" / "LATEST.html"
    report.write_html(files[-1], ROOT / "data", latest, files)
    print(f"Open: {latest.relative_to(ROOT)}  (same as {newest.name})")
    if not args.no_open and sys.platform == "darwin":
        import subprocess
        subprocess.run(["open", str(latest)], check=False)
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
    vw = sub.add_parser("view")
    vw.add_argument("--no-open", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd is None:
        args = ap.parse_args(["run"] + (argv or sys.argv[1:]))
    return {"run": cmd_run, "mark": cmd_mark, "status": cmd_status, "view": cmd_view}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
