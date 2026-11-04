"""The run pipeline shared by the fetcher and /job-run.

data/runs/<date>/
  candidates.json   every role that passed the filters (not just the top N), with descriptions
  all.jsonl         every fetched role, kept or not, with the reason (used by the recall check)
  imported/*.json   roles Claude found by web search or LinkedIn, added with `jobagent import`
  batches/*.md      roles waiting for Claude to score (only ones not already in the score cache)
  scores/*.jsonl    Claude's scores, one JSON object per line
  matches.json      every scored role, best first (the "All matches" tab)
  recall.json       benchmark postings for the recall check; recall_report.md is the result
data/score_cache.json  Claude's score per role id, so a role is only ever scored once
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

from . import filters
from .sources import Job
from .store import SeenStore, fuzzy_key


def run_dir(data: Path, run_date: str | None = None) -> Path:
    d = data / "runs" / (run_date or date.today().isoformat())
    d.mkdir(parents=True, exist_ok=True)
    return d


def latest_run(data: Path) -> Path | None:
    runs = sorted(p for p in (data / "runs").glob("*") if (p / "candidates.json").exists()) \
        if (data / "runs").exists() else []
    return runs[-1] if runs else None


def known_companies(companies: dict) -> set[str]:
    return {b["company"].lower() for b in companies.get("board", [])} | \
           {w["company"].lower() for w in companies.get("watch", [])}


def is_new_company(company: str, known: set[str]) -> bool:
    c = company.lower()
    return not any(k in c or c in k for k in known)


def candidate(v: filters.Verdict, j: Job, cfg: dict, store: SeenStore, known: set[str]) -> dict:
    if j.extra.get("recruiter"):
        v.flags.append("recruiter/job-board ad: real employer may not be named")
        v.score -= 2
    return {**j.to_dict(), "description": j.description[:4000], "score": v.score, "region": v.region,
            "sponsorship": v.sponsorship, "why": v.why, "flags": v.flags, "internship": v.internship,
            "families": v.families,
            "applied": filters.is_applied(j.company, cfg) or j.company in store.applied_companies(),
            "new_company": is_new_company(j.company, known)}


def evaluate_all(jobs: list[Job], cfg: dict, store: SeenStore, known: set[str], allow_unknown_location=False):
    """Returns (kept candidate dicts, all-rows for all.jsonl, excluded reason counts)."""
    kept, rows, excluded = [], [], {}
    for j in jobs:
        v = filters.evaluate(j, cfg)
        if allow_unknown_location and not j.location.strip() and v.reasons == ["location outside UK/EU"]:
            v.keep, v.reasons = True, []
            v.flags.append("location not stated: check")
            v.region = "unknown"
        reason = v.reasons[0] if v.reasons else ""
        if v.keep and store.seen(j.source_id, j.company, j.title):
            reason = "already shown in an earlier shortlist"
        rows.append({"id": j.source_id, "company": j.company, "title": j.title, "location": j.location,
                     "url": j.url, "source": j.source, "kept": v.keep and not reason, "reason": reason,
                     "all_reasons": v.reasons,
                     "score": v.score,
                     # a short role excerpt for the filter audit, only for removed roles in a target family
                     "snippet": role_text(j.description, 500) if (reason and v.families) else ""})
        if reason:
            key = ("location outside UK/EU" if reason.startswith("location outside")
                   else "too much experience asked" if "years' experience" in reason
                   else "senior/excluded title word" if reason.startswith("title contains") else reason)
            excluded[key] = excluded.get(key, 0) + 1
            continue
        kept.append(candidate(v, j, cfg, store, known))
    kept.sort(key=lambda c: -c["score"])
    return kept, rows, excluded


def save_run(rd: Path, kept: list[dict], rows: list[dict], excluded: dict, failed: list[str], append=False):
    cpath = rd / "candidates.json"
    if append and cpath.exists():
        old = json.loads(cpath.read_text())
        ids = {c["source_id"] for c in old["candidates"]}
        keys = {fuzzy_key(c["company"], c["title"]) for c in old["candidates"]}
        new = [c for c in kept if c["source_id"] not in ids and fuzzy_key(c["company"], c["title"]) not in keys]
        old["candidates"] += new
        for k, n in excluded.items():
            old["excluded_counts"][k] = old["excluded_counts"].get(k, 0) + n
        cpath.write_text(json.dumps(old, indent=2, ensure_ascii=False) + "\n")
        mode = "a"
        kept = new
    else:
        cpath.write_text(json.dumps({"run": rd.name, "excluded_counts": excluded, "failed_sources": failed,
                                     "candidates": kept}, indent=2, ensure_ascii=False) + "\n")
        mode = "w"
    with (rd / "all.jsonl").open(mode) as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return kept


def load_candidates(rd: Path) -> list[dict]:
    return json.loads((rd / "candidates.json").read_text())["candidates"]


# --------------------------------------------------------------------------- import (web / LinkedIn)
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def import_jobs(items: list[dict], cfg: dict, store: SeenStore, known: set[str], rd: Path,
                companies: dict | None = None) -> dict:
    """items: [{company, title, location, url, description?, deadline?, source?}] found by Claude.
    They go through the same filters, dedupe and scoring as fetched roles."""
    jobs = []
    for it in items:
        if not (it.get("company") and it.get("title")):
            continue
        src = (it.get("source") or "web").lower()
        url = it.get("url", "")
        jid = it.get("id") or f"{src}:{hashlib.sha1((url or it['company'] + it['title']).encode()).hexdigest()[:10]}" \
                                 f":{_slug(it['company'])}"
        jobs.append(Job(source=src, source_id=jid, company=it["company"].strip(), title=it["title"].strip(),
                        location=(it.get("location") or "").strip(), url=url,
                        description=it.get("description") or "", deadline=it.get("deadline") or ""))
    for j in jobs:
        normalize_company(j, companies or {})
    existing = {c["source_id"] for c in load_candidates(rd)} if (rd / "candidates.json").exists() else set()
    jobs = [j for j in jobs if j.source_id not in existing]
    kept, rows, excluded = evaluate_all(jobs, cfg, store, known, allow_unknown_location=True)
    for c in kept:
        c["deadline"] = c.get("deadline") or ""
    added = save_run(rd, kept, rows, excluded, [], append=True)
    return {"received": len(items), "added": len(added), "excluded": excluded}


# --------------------------------------------------------------------------- scoring batches
SCORE_CACHE = "score_cache.json"


def load_cache(data: Path) -> dict:
    p = data / SCORE_CACHE
    return json.loads(p.read_text()) if p.exists() else {}


def save_cache(data: Path, cache: dict) -> None:
    (data / SCORE_CACHE).write_text(json.dumps(cache, indent=1, ensure_ascii=False) + "\n")


BATCH_HEADER = """# Scoring batch {n} of {total} ({count} roles)

Score EVERY role below against the CV (cv/cv.tex) and profile (config/profile.toml).
Write one JSON object per line to `{out}` (no other text), using each role's exact id:
{{"id": "<id>", "fit": 1-5, "reason": "<one line: why it fits or not, concrete>", "deadline": "<date or ''>",
 "start": "<start date if stated or ''>", "concerns": "<visa/experience/language/timing issues or ''>"}}

Fit scale (be strict; across a batch most roles should be 2 or 3):
5 = rare: the role, level, location and timing all fit my CV and goals, I should apply this week.
4 = strong: core work matches my CV (ML/AI/LLM, data science, quant, SWE) and level is graduate/junior,
    with at most one minor doubt.
3 = worth a look: relevant but with a real doubt (adjacent field such as SRE/infra/data platform,
    unclear level, smaller company or city, recruiter ad with the employer not named).
2 = weak: wrong level, mostly unrelated work, internship timing clash, language I don't speak.
1 = not suitable (wrong country, senior, unrelated).
Judge from the description, not just the title. If the description is boilerplate only, say so in
`concerns` and don't go above 3. Use only facts from the posting and the CV. Never invent a deadline.

"""


def role_text(text: str, n: int = 2000) -> str:
    """The part of a description about the role: skips the opening company boilerplate when a
    'The role' / 'What you'll do' / 'Responsibilities' heading appears later on."""
    from .report import ROLE_START
    t = re.sub(r"\s+", " ", text or "").strip()
    m = ROLE_START.search(t[:5000])
    if m and m.start() > 150:
        t = t[m.start():]
    return t[:n]


def normalize_company(job: Job, companies: dict) -> None:
    """Fixes aggregator company names (e.g. a board slug like 'wehrtyou') and flags recruiter ads."""
    aliases = {k.lower(): v for k, v in companies.get("aliases", {}).items()}
    name = job.company.strip()
    if name.lower() in aliases:
        job.company = aliases[name.lower()]
    recruiters = [r.lower() for r in companies.get("recruiters", {}).get("names", [])]
    if any(r in name.lower() for r in recruiters):
        job.extra["recruiter"] = True


def make_batches(rd: Path, cache: dict, size: int = 25) -> list[Path]:
    todo = [c for c in load_candidates(rd) if c["source_id"] not in cache]
    bdir, sdir = rd / "batches", rd / "scores"
    bdir.mkdir(exist_ok=True)
    sdir.mkdir(exist_ok=True)
    for old in bdir.glob("*.md"):
        old.unlink()
    chunks = [todo[i:i + size] for i in range(0, len(todo), size)]
    files = []
    for n, chunk in enumerate(chunks, 1):
        out = sdir / f"batch-{n:03d}.jsonl"
        lines = [BATCH_HEADER.format(n=n, total=len(chunks), count=len(chunk), out=out)]
        for c in chunk:
            desc = role_text(c.get("description") or "", 2000) or "(no description: judge from title)"
            lines.append(f"## id: {c['source_id']}\n**{c['title']}** · {c['company']} · {c['location']} "
                         f"· source {c['source']}\nSponsorship: {c['sponsorship']} · Flags: "
                         f"{'; '.join(c.get('flags') or []) or 'none'}\n{desc}\n")
        p = bdir / f"batch-{n:03d}.md"
        p.write_text("\n".join(lines))
        files.append(p)
    return files


def read_scores(rd: Path) -> tuple[dict, list[str]]:
    """Parses scores/*.jsonl. Returns ({id: score}, [problems])."""
    out, problems = {}, []
    for f in sorted((rd / "scores").glob("*.jsonl")) if (rd / "scores").exists() else []:
        for i, line in enumerate(f.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            try:
                s = json.loads(line)
                fit = int(s["fit"])
                if not 1 <= fit <= 5:
                    raise ValueError("fit out of range")
                out[str(s["id"])] = {"fit": fit, "reason": str(s.get("reason", ""))[:400],
                                     "deadline": str(s.get("deadline", ""))[:80], "start": str(s.get("start", ""))[:80],
                                     "concerns": str(s.get("concerns", ""))[:300], "scored": rd.name}
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
                problems.append(f"{f.name}:{i}: {e}")
    return out, problems


def merge_scores(rd: Path, data: Path, cfg: dict, store: SeenStore, shortlist_dir: Path,
                 statuses: dict | None = None) -> dict:
    """Combines Claude's scores with the candidates: writes matches.json (all, best first) and the
    shortlist (top N with fit >= min). Returns a summary."""
    cache = load_cache(data)
    new, problems = read_scores(rd)
    cands = {c["source_id"]: c for c in load_candidates(rd)}
    new = {k: v for k, v in new.items() if k in cands}
    cache.update(new)
    save_cache(data, cache)
    statuses = statuses or store.statuses()
    matches, unscored = [], []
    for sid, c in cands.items():
        sc = cache.get(sid)
        if not sc:
            unscored.append(sid)
            continue
        if statuses.get(sid) == "not_interested":
            continue
        matches.append({**c, "fit": sc["fit"], "llm_reason": sc["reason"],
                        "deadline": sc.get("deadline") or c.get("deadline") or "",
                        "concerns": sc.get("concerns", ""), "start": sc.get("start", "")})
    matches.sort(key=lambda m: (-m["fit"], -m["score"]))
    (rd / "matches.json").write_text(json.dumps({"run": rd.name, "matches": matches, "unscored": unscored},
                                                indent=1, ensure_ascii=False) + "\n")
    min_fit = cfg.get("scoring", {}).get("min_fit_shortlist", 3)
    size = cfg["output"]["shortlist_size"]
    top = [m for m in matches if m["fit"] >= min_fit][:size]
    rows = []
    for m in top:
        why = f"{m['fit']}/5: {m['llm_reason']}" + (" (new)" if m.get("new_company") else "")
        flags = list(m.get("flags") or []) + ([m["concerns"]] if m.get("concerns") else [])
        rows.append({"source_id": m["source_id"], "title": m["title"], "company": m["company"],
                     "location": m["location"], "url": m["url"], "deadline": m["deadline"] or "Not stated",
                     "sponsorship": m["sponsorship"], "why": why, "flags": flags, "applied": m.get("applied")})
    from . import report
    name = rd.name
    out = report.next_shortlist_path(shortlist_dir, name)
    notes = [f"{len(matches)} roles scored by Claude (all are in the job page's All matches tab); "
             f"shortlist = top {len(rows)} with fit {min_fit}+/5."]
    if unscored:
        notes.append(f"{len(unscored)} roles not scored yet (run `python3 -m jobagent batches` again).")
    report.write_shortlist(out, f"{name} (scored)", rows, notes)
    for m in top:
        store.add(m["source_id"], m["company"], m["title"], m["url"], run=name,
                  extra={"deadline": m["deadline"], "location": m["location"], "region": m["region"],
                         "families": m.get("families", []), "source": m["source"], "fit": m["fit"]})
    store.save()
    return {"scored_now": len(new), "matches": len(matches), "unscored": unscored, "problems": problems,
            "shortlist": out, "shortlisted": len(rows)}


# --------------------------------------------------------------------------- recall check
def _title_tokens(t: str) -> set[str]:
    stop = {"and", "the", "of", "for", "in", "a", "to", "2026", "2027", "2028", "london", "uk", "-", "&"}
    return {w for w in re.findall(r"[a-z0-9+#]+", t.lower()) if w not in stop and len(w) > 1}


def _company_match(a: str, b: str) -> bool:
    na, nb = fuzzy_key(a, "x").split("::")[0], fuzzy_key(b, "x").split("::")[0]
    return bool(na and nb) and (na in nb or nb in na)


def recall(rd: Path, benchmark: list[dict]) -> dict:
    """Compares real postings found elsewhere (job boards) with everything this run fetched.
    found+kept = we have it; excluded = we had it but a filter removed it (check the reason);
    missing = no source of ours returned it (coverage gap)."""
    rows = [json.loads(line) for line in (rd / "all.jsonl").read_text().splitlines() if line.strip()] \
        if (rd / "all.jsonl").exists() else []
    matches = json.loads((rd / "matches.json").read_text())["matches"] if (rd / "matches.json").exists() else []
    fit_by_id = {m["source_id"]: m["fit"] for m in matches}
    res = {"found": [], "excluded": [], "missing": []}
    for b in benchmark:
        bt = _title_tokens(b.get("title", ""))
        best = None
        for r in rows:
            if not _company_match(b.get("company", ""), r["company"]):
                continue
            rt = _title_tokens(r["title"])
            overlap = len(bt & rt) / max(1, min(len(bt), len(rt)))
            if overlap >= 0.6 and (best is None or overlap > best[0] or (r["kept"] and not best[1]["kept"])):
                best = (overlap, r)
        item = {**b}
        if best is None:
            res["missing"].append(item)
        elif best[1]["kept"] or best[1]["reason"].startswith("already shown"):
            item["fit"] = fit_by_id.get(best[1]["id"])
            item["note"] = "already shown earlier" if best[1]["reason"] else ""
            res["found"].append(item)
        else:
            item["reason"] = best[1]["reason"]
            res["excluded"].append(item)
    total = len(benchmark) or 1
    res["recall"] = round((len(res["found"]) + len(res["excluded"])) / total, 2)
    res["kept_rate"] = round(len(res["found"]) / total, 2)
    lines = [f"# Recall check: {rd.name}", "",
             f"{len(benchmark)} real postings from other job boards. Fetched by us: "
             f"{len(res['found']) + len(res['excluded'])} ({int(res['recall'] * 100)}%). "
             f"Kept after filters: {len(res['found'])}.", ""]
    for key, label in (("found", "Found and kept"), ("excluded", "Fetched but filtered out (check the reason)"),
                       ("missing", "Missing: no source returned it (coverage gap)")):
        lines.append(f"## {label} ({len(res[key])})")
        for it in res[key]:
            extra = f" · fit {it['fit']}/5" if it.get("fit") else ""
            extra += f" · {it['reason']}" if it.get("reason") else ""
            extra += f" · {it['note']}" if it.get("note") else ""
            lines.append(f"- {it.get('company', '')}: {it.get('title', '')}{extra} · {it.get('url', '')}")
        lines.append("")
    (rd / "recall_report.md").write_text("\n".join(lines))
    return res


# --------------------------------------------------------------------------- filter audit
AUDIT_SKIP = ("location outside", "already shown", "not a target role family")
ENTRY = re.compile(r"graduate|new grad|grads?\b|junior|entry|campus|early career|2027|intern", re.I)

AUDIT_HEADER = """# Filter audit: {date}

These roles were REMOVED by the filters but look relevant (target role family{entry}). Check each
removal against its reason and excerpt. For every wrong removal, write a line in
`{out}`: the title, the reason it was removed, why that's wrong, and which setting or pattern to fix
(e.g. `[filters].exclude_title_words`, `max_years_experience`, the sponsorship wording, the PhD rule).
If all removals are right, write "No wrong removals." Don't change any config without asking.

"""


def audit(rd: Path, n: int = 40) -> Path:
    """Samples removed-but-relevant roles so Claude can spot filter bugs (wrong removals)."""
    rows = [json.loads(line) for line in (rd / "all.jsonl").read_text().splitlines() if line.strip()]
    # only roles removed by a single, possibly wrong, rule (not also wrong country / family / already shown)
    pool = [r for r in rows if not r["kept"] and r.get("snippet")
            and not any(x.startswith(AUDIT_SKIP) for x in (r.get("all_reasons") or [r["reason"]]))
            and not r["reason"].startswith(AUDIT_SKIP)]
    entry = [r for r in pool if ENTRY.search(r["title"])]
    rest = [r for r in pool if r not in entry]
    pick = (entry + rest)[:n]
    out = rd / "audit_findings.md"
    lines = [AUDIT_HEADER.format(date=rd.name, entry=", entry-level titles first", out=out)]
    for r in pick:
        lines.append(f"## {r['title']} · {r['company']} · {r['location']}\nRemoved because: **{r['reason']}** · "
                     f"{r['url']}\n{r['snippet']}\n")
    path = rd / "audit.md"
    path.write_text("\n".join(lines))
    return path


def record_recall(history: Path, rd: Path, res: dict, n: int) -> None:
    """Appends one line per recall check to history/recall.csv (tracked in git), so the benchmark grows."""
    history.parent.mkdir(parents=True, exist_ok=True)
    new = not history.exists()
    missing = "; ".join(sorted({m.get("company", "") for m in res["missing"]}))
    with history.open("a") as fh:
        if new:
            fh.write("date,postings,fetched_pct,kept_pct,filtered_out,missing,missing_companies\n")
        fh.write(f"{rd.name},{n},{int(res['recall'] * 100)},{int(res['kept_rate'] * 100)},{len(res['excluded'])},"
                 f"{len(res['missing'])},\"{missing}\"\n")
