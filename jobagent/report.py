"""Markdown output for shortlist/YYYY-MM-DD.md."""
from __future__ import annotations

import html
import json
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


def shortlist_key(path: Path):
    """Sort shortlists by date, then run number: 2026-11-03 < -live < -run2 < -run10."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:-(.*))?$", path.stem)
    if not m:
        return (path.stem, 0, "")
    rest = m.group(2) or ""
    n = re.match(r"run(\d+)$", rest)
    return (m.group(1), int(n.group(1)) if n else (1 if rest else 0), rest)


def next_shortlist_path(folder: Path, run_date: str) -> Path:
    existing = [f for f in folder.glob(f"{run_date}*.md")]
    if not existing:
        return folder / f"{run_date}.md"
    top = max(shortlist_key(f)[1] for f in existing)
    return folder / f"{run_date}-run{max(top + 1, 2)}.md"


def read_ids(path: Path) -> list[dict]:
    return [m.groupdict() for m in ID_LINE.finditer(path.read_text())]


# --------------------------------------------------------------------------- HTML view
ROW = re.compile(r"^\|\s*(\d+)\s*\|(.*)\|\s*$")
LINK = re.compile(r"\[[^\]]*\]\((\S+?)\)")


def parse_shortlist(path: Path) -> list[dict]:
    """Reads the table rows of a shortlist file (any of our formats) into dicts."""
    rows, ids = [], read_ids(path)
    for line in path.read_text().splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        if len(cells) < 7:
            continue
        title, company, location, deadline, sponsorship, why, link = cells[:7]
        url = (LINK.search(link) or LINK.search(line))
        rows.append({"rank": int(m.group(1)), "title": title, "company": company, "location": location,
                     "deadline": deadline, "sponsorship": sponsorship, "why": why,
                     "url": url.group(1) if url else ""})
    for r, i in zip(rows, ids):
        r["id"] = i["id"]
    return rows


def _descriptions(data_dir: Path) -> dict:
    """source_id -> (description, location) from every saved candidates file, newest last."""
    out = {}
    files = sorted((data_dir / "candidates").glob("*.json")) + sorted((data_dir / "runs").glob("*/candidates.json"))
    for f in files:
        try:
            for c in json.loads(f.read_text()).get("candidates", []):
                out[c["source_id"]] = c.get("description", "")
        except Exception:  # noqa: BLE001 - a broken data file shouldn't stop the page
            continue
    return out


ROLE_START = re.compile(r"(about the role|the role|about the team|what you'?ll do|what you will do|your role|"
                        r"the opportunity|responsibilities|in this role|the position|your mission|vos missions|"
                        r"ihre aufgaben|deine aufgaben)\b[:\s]*", re.I)


def _summary(text: str, n: int = 650) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    m = ROLE_START.search(t[:4000])
    if m and m.start() > 80:          # skip the company boilerplate, start at the role
        t = t[m.start():]
    if len(t) <= n:
        return t
    cut = t[:n]
    return cut[: cut.rfind(". ") + 1] if ". " in cut[200:] else cut.rsplit(" ", 1)[0] + "…"


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                       "nov", "dec"], 1)}


def _deadline_days(text: str) -> int | None:
    """Days until a deadline like '22 Nov 2026' or '2026-11-22'; None if there's no date."""
    from datetime import date
    t = text.lower()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    try:
        if m:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        else:
            m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*\.?,?\s+(\d{4})", t)
            if not m or m.group(2) not in MONTHS:
                return None
            d = date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
    except ValueError:
        return None
    return (d - date.today()).days


def _sponsor_class(text: str) -> str:
    t = text.lower()
    if re.search(r"none needed|no sponsorship needed|not needed|free movement|offered|can work in", t):
        return "good"
    if re.search(r"check|mixed|remote", t):
        return "warn"
    return "neutral"


def _initials(company: str) -> str:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", company)
    return (words[0][0] + (words[1][0] if len(words) > 1 else "")).upper() if words else "?"


def _hue(s: str) -> int:
    return sum(ord(c) * (i + 1) for i, c in enumerate(s)) % 360


CSS = """
:root{--bg:#f4f5f7;--card:#fff;--ink:#1b2130;--mute:#606a7b;--line:#e2e5ea;--soft:#eef1f5;--accent:#2f5bd3;
--accent-ink:#fff;--good:#1d7a45;--good-bg:#e6f4ec;--warn:#8a5a00;--warn-bg:#fbf1dc;--bad:#a23a3a;--bad-bg:#f9e5e5;
--shadow:0 1px 2px rgba(20,30,50,.06),0 4px 14px rgba(20,30,50,.05)}
@media (prefers-color-scheme:dark){:root{--bg:#101318;--card:#181c24;--ink:#e7eaf0;--mute:#9aa3b3;--line:#2a303b;
--soft:#212733;--accent:#7f9fff;--accent-ink:#0d1220;--good:#62d394;--good-bg:#173126;--warn:#eac46a;--warn-bg:#33291a;
--bad:#f29191;--bad-bg:#3a1f22;--shadow:none}}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent)} main{max-width:920px;margin:0 auto;padding:0 16px 64px}
header.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);
backdrop-filter:blur(8px);border-bottom:1px solid var(--line);margin:0 -16px 18px;padding:14px 16px 12px}
.row1{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap} h1{font-size:20px;margin:0;letter-spacing:-.01em}
.date{color:var(--mute);font-size:14px} nav{margin-left:auto;font-size:14px} nav a{margin-left:14px;text-decoration:none}
nav a.cur{font-weight:650;color:var(--ink)}
.stats{display:flex;gap:8px;margin:10px 0 10px;flex-wrap:wrap}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:6px 12px;font-size:13px;color:var(--mute)}
.stat b{color:var(--ink);font-size:16px;margin-right:4px}
.tools{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.tools input[type=search]{flex:1;min-width:180px;font:inherit;padding:7px 12px;border-radius:9px;border:1px solid var(--line);
background:var(--card);color:var(--ink)}
.chip{font:inherit;font-size:13px;padding:6px 12px;border-radius:99px;border:1px solid var(--line);background:var(--card);
color:var(--ink);cursor:pointer} .chip.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
select{font:inherit;font-size:13px;padding:6px 8px;border-radius:9px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:0 0 12px;box-shadow:var(--shadow)}
.card.s-applied{border-color:var(--good);box-shadow:inset 4px 0 0 var(--good),var(--shadow)}
.card.s-interested{box-shadow:inset 4px 0 0 var(--warn),var(--shadow)} .card.s-not_interested{opacity:.55}
.top-line{display:flex;gap:14px;align-items:flex-start}
.logo{flex:none;width:42px;height:42px;border-radius:10px;display:grid;place-items:center;font-weight:700;font-size:15px;color:#fff}
.head{flex:1;min-width:0} h2{font-size:17px;margin:0;line-height:1.3}
.meta{color:var(--mute);margin-top:3px;font-size:14px} .rank{color:var(--mute);font-weight:600;margin-right:6px}
.apply{flex:none;background:var(--accent);color:var(--accent-ink);text-decoration:none;padding:8px 16px;border-radius:9px;
font-weight:650;font-size:14px;white-space:nowrap} .apply:hover{filter:brightness(1.08)}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 0 56px}
.tag{font-size:12.5px;padding:3px 9px;border-radius:7px;background:var(--soft);color:var(--mute)}
.tag.good{background:var(--good-bg);color:var(--good)} .tag.warn{background:var(--warn-bg);color:var(--warn)}
.tag.bad{background:var(--bad-bg);color:var(--bad)} .tag.fit{font-weight:700}
.why{margin:10px 0 0 56px} .flags{margin:6px 0 0 56px;color:var(--warn);font-size:13.5px}
details{margin:8px 0 0 56px;color:var(--mute);font-size:14px} summary{cursor:pointer;color:var(--accent);font-size:13.5px}
details p{margin:6px 0 0} .lead{margin:8px 0 0 56px;color:var(--mute);font-size:14px}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 0 56px}
.st{font:inherit;font-size:13px;padding:6px 12px;border-radius:9px;border:1px solid var(--line);background:transparent;
color:var(--ink);cursor:pointer} .st:hover{background:var(--soft)}
.st.applied.on{background:var(--good);border-color:var(--good);color:var(--card)}
.st.interested.on{background:var(--warn);border-color:var(--warn);color:var(--card)}
.st.not_interested.on{background:var(--bad);border-color:var(--bad);color:var(--card)}
.hint{background:var(--card);border:1px dashed var(--line);border-radius:10px;padding:9px 12px;color:var(--mute);font-size:14px;margin:0 0 14px}
.empty{color:var(--mute);text-align:center;padding:30px} h3{font-size:15px;color:var(--mute);margin:28px 0 6px}
ul.older{color:var(--mute);padding-left:18px}
nav.tabs{display:flex;gap:4px;margin:10px 0 0;flex-wrap:wrap} nav.tabs a{padding:6px 12px;border-radius:9px;
text-decoration:none;color:var(--mute);font-size:14px;font-weight:600} nav.tabs a.cur{background:var(--ink);color:var(--bg)}
.remind{background:var(--warn-bg);color:var(--warn);border-radius:10px;padding:10px 14px;margin:0 0 14px;font-size:14px}
.remind b{display:block;margin-bottom:4px} .remind ul{margin:0;padding-left:18px}
.stage{font:inherit;font-size:13px;padding:6px 8px;border-radius:9px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
textarea.note{width:100%;min-height:54px;font:inherit;font-size:14px;padding:8px 10px;border-radius:9px;
border:1px solid var(--line);background:var(--bg);color:var(--ink);margin-top:8px}
.saved{color:var(--good);font-size:13px;margin-left:8px} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.big{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px} .big b{font-size:24px;display:block}
.big span{color:var(--mute);font-size:13px} table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
border-radius:12px;overflow:hidden;font-size:14px} th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line)}
th{color:var(--mute);font-weight:600} .card.s-interviewing,.card.s-offer{border-color:var(--accent);box-shadow:inset 4px 0 0 var(--accent),var(--shadow)}
.card.s-rejected{opacity:.6}
@media (max-width:600px){header.top{position:static}.top-line{flex-wrap:wrap}.head{flex-basis:calc(100% - 60px)}
.apply{margin-left:56px}nav{margin-left:0;width:100%}nav a{margin:0 14px 0 0}.stats .stat{padding:4px 10px}
.tags,.why,.flags,details,.lead,.actions{margin-left:0}}
"""



# --------------------------------------------------------------------------- page building blocks
def _job(r: dict, desc: dict) -> dict:
    """Normalises a shortlist row or a match into what a card needs."""
    sid = r.get("id") or r.get("source_id", "")
    d = r.get("description") or desc.get(sid) or next(
        (v for k, v in desc.items() if sid and (sid.endswith(k) or k.endswith(sid))), "")
    why_raw = r.get("why", "")
    if "fit" in r and r.get("llm_reason") is not None:
        fit = int(r["fit"])
        why_raw = r["llm_reason"] + (" ⚠ " + "; ".join(r.get("flags") or []) if r.get("flags") else "") \
            + (f" ⚠ {r['concerns']}" if r.get("concerns") else "")
        new = bool(r.get("new_company"))
    else:
        m = re.match(r"\s*(\d)/5", why_raw)
        fit = int(m.group(1)) if m else 0
        new = "(new)" in why_raw
    company_raw = r.get("company", "").replace("**", "")
    why = re.sub(r"^\s*\d/5:\s*", "", why_raw).replace("(new)", "").strip()
    reason, _, flags = why.partition("⚠")
    return {"id": sid, "rank": r.get("rank", 0), "title": r.get("title", ""),
            "company": re.sub(r"\s*\(already applied\)", "", company_raw).strip(),
            "applied_prev": "already applied" in company_raw.lower() or bool(r.get("applied")),
            "location": r.get("location", ""), "url": r.get("url", ""), "deadline": r.get("deadline") or "",
            "sponsorship": r.get("sponsorship", ""), "fit": fit, "new": new, "reason": reason.strip(),
            "flags": " · ".join(x.strip() for x in flags.split("⚠") if x.strip()), "description": d,
            "seen": bool(r.get("seen"))}


def _card(j: dict, st: str, interactive: bool) -> str:
    esc = html.escape
    days = _deadline_days(j["deadline"])
    tags = []
    if j["fit"]:
        tags.append(f'<span class="tag fit {"good" if j["fit"] >= 4 else "warn" if j["fit"] == 3 else "bad"}">'
                    f'{j["fit"]}/5 fit</span>')
    if days is not None:
        cls = "bad" if days <= 14 else "warn" if days <= 30 else ""
        when = "closed" if days < 0 else "today" if days == 0 else f"{days} days left"
        tags.append(f'<span class="tag {cls}">Deadline {esc(j["deadline"])} · {when}</span>')
    elif j["deadline"] and j["deadline"] not in ("—", "Not stated"):
        tags.append(f'<span class="tag">Deadline: {esc(j["deadline"])}</span>')
    if j["sponsorship"]:
        tags.append(f'<span class="tag {_sponsor_class(j["sponsorship"])}">{esc(j["sponsorship"])}</span>')
    if j["new"]:
        tags.append('<span class="tag">New company</span>')
    if j["applied_prev"]:
        tags.append('<span class="tag good">Already applied</span>')
    if j.get("seen"):
        tags.append('<span class="tag">Shown before</span>')
    summ, more = _summary(j["description"]), _summary(j["description"], 2500)
    body = (f'<details><summary>Show description</summary><p>{esc(more)}</p></details>' if summ and len(more) > len(summ) + 40
            else f'<p class="lead">{esc(summ)}</p>' if summ else "")
    buttons = "".join(
        f'<button class="st {k}{" on" if st == k else ""}" data-s="{k}">{label}</button>'
        for k, label in (("applied", "✓ Applied"), ("interested", "★ Interested"), ("not_interested", "✕ Not for me")))
    rank = f'<span class="rank">{j["rank"]}.</span>' if j["rank"] else ""
    return f"""
<article class="card s-{st}" data-id="{esc(j['id'])}" data-company="{esc(j['company'])}" data-title="{esc(j['title'])}"
 data-url="{esc(j['url'])}" data-deadline="{esc(j['deadline'])}" data-location="{esc(j['location'])}"
 data-rank="{j['rank'] or 999}" data-fit="{j['fit']}" data-days="{days if days is not None else 9999}"
 data-text="{esc((j['title'] + ' ' + j['company'] + ' ' + j['location']).lower())}">
  <div class="top-line">
    <div class="logo" style="background:hsl({_hue(j['company'])} 45% 45%)">{esc(_initials(j['company']))}</div>
    <div class="head"><h2>{rank}{esc(j['title'])}</h2><div class="meta">{esc(j['company'])} · {esc(j['location'])}</div></div>
    <a class="apply" href="{esc(j['url'])}" target="_blank" rel="noopener">Apply ↗</a>
  </div>
  <div class="tags">{''.join(tags)}</div>
  {f'<p class="why">{esc(j["reason"].rstrip("."))}.</p>' if j['reason'] else ''}
  {f'<div class="flags">⚠ {esc(j["flags"])}</div>' if j['flags'] else ''}
  {body}
  {f'<div class="actions">{buttons}</div>' if interactive else ''}
</article>"""


TABS = (("/", "Top picks"), ("/all", "All matches"), ("/applied", "My applications"), ("/stats", "Stats"))


def _page(title: str, sub: str, active: str, inner: str, interactive: bool, tools: str = "", stats: str = "",
          reminders: list[str] | None = None, script: str = "") -> str:
    esc = html.escape
    tabs = "".join(f'<a class="{"cur" if href == active else ""}" href="{href}">{label}</a>' for href, label in TABS) \
        if interactive else ""
    rem = ""
    if reminders:
        rem = '<div class="remind"><b>Reminders</b><ul>' + "".join(f"<li>{esc(r)}</li>" for r in reminders[:8]) + \
              "</ul></div>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style></head>
<body><main>
<header class="top">
  <div class="row1"><h1>{esc(title)}</h1><span class="date">{esc(sub)}</span></div>
  {f'<nav class="tabs">{tabs}</nav>' if tabs else ''}
  {f'<div class="stats">{stats}</div>' if stats else ''}
  {f'<div class="tools">{tools}</div>' if tools else ''}
</header>
{'' if interactive else HINT}{rem}
{inner}
</main><script>{script}</script></body></html>"""


def _tools(interactive: bool, fit_filter: bool = False) -> str:
    fits = ('<select id="minfit"><option value="3">Fit 3+/5</option><option value="4">Fit 4+/5</option>'
            '<option value="5">Fit 5/5</option><option value="0">Any fit</option></select>') if fit_filter else ""
    chips = ('<button class="chip" data-f="reported">Not marked</button><button class="chip" data-f="interested">Interested</button>'
             '<button class="chip" data-f="applied">Applied</button>'
             '<label class="chip"><input type="checkbox" id="hide"> hide "not for me"</label>') if interactive else ""
    return (f'<input type="search" id="q" placeholder="Search jobs…"><button class="chip on" data-f="all">All</button>{chips}'
            f'{fits}<select id="sort"><option value="rank">Sort: best match</option><option value="fit">Sort: fit score</option>'
            f'<option value="days">Sort: deadline soonest</option></select>')


def _stat_boxes(n: int, cards: list[str], statuses: list[str]) -> str:
    return (f'<div class="stat"><b>{n}</b>jobs</div>'
            f'<div class="stat"><b>{statuses.count("applied")}</b>applied</div>'
            f'<div class="stat"><b>{statuses.count("interested")}</b>interested</div>'
            f'<div class="stat"><b>{sum(1 for c in cards if "tag fit good" in c)}</b>strong fits (4–5/5)</div>')


# --------------------------------------------------------------------------- pages
def write_html(md_path: Path, data_dir: Path, out: Path | None, others: list[Path],
               statuses: dict | None = None, interactive: bool = False, reminders: list[str] | None = None) -> int | str:
    """Top picks page for one shortlist file. Returns the HTML when out is None."""
    statuses = statuses or {}
    desc = _descriptions(data_dir)
    jobs = [_job(r, desc) for r in parse_shortlist(md_path)]
    sts = [statuses.get(j["id"], "reported") for j in jobs]
    cards = [_card(j, st, interactive) for j, st in zip(jobs, sts)]
    esc = html.escape
    href = (lambda o: f"/s/{o.stem}") if interactive else (lambda o: f"{o.stem}.html")
    older = "".join(f'<li><a href="{esc(href(o))}">{esc(o.stem)}</a></li>'
                    for o in sorted(others, key=shortlist_key, reverse=True) if o != md_path)
    inner = (f'<div id="list">{"".join(cards) or "<p class=empty>No roles in this shortlist.</p>"}</div>'
             '<p class="empty" id="none" hidden>No jobs match these filters.</p>'
             + (f'<h3>Earlier shortlists</h3><ul class="older">{older}</ul>' if older else ""))
    page = _page("Your job shortlist", md_path.stem, "/", inner, interactive, _tools(interactive),
                 _stat_boxes(len(jobs), cards, sts), reminders, SCRIPT + (STATUS_SCRIPT if interactive else ""))
    if out is None:
        return page
    out.write_text(page)
    return len(jobs)


def all_matches_html(run: Path | None, statuses: dict, interactive: bool = True,
                     reminders: list[str] | None = None) -> str:
    """Every role Claude scored in the latest run (not just the top picks), best first."""
    matches = []
    if run is not None and (run / "matches.json").exists():
        matches = json.loads((run / "matches.json").read_text()).get("matches", [])
    jobs = [_job(m, {}) for m in matches]
    for i, j in enumerate(jobs, 1):
        j["rank"] = i
    sts = [statuses.get(j["id"], "reported") for j in jobs]
    cards = [_card(j, st, interactive) for j, st in zip(jobs, sts)]
    empty = ("<p class=empty>No scored roles yet. Run /job-run in Claude Code (it scores every role that passes "
             "your filters).</p>")
    inner = (f'<div id="list">{"".join(cards) or empty}</div><p class="empty" id="none" hidden>No jobs match these '
             f'filters.</p>')
    return _page("All matches", f"{run.name if run else ''} · {len(jobs)} scored roles", "/all", inner, interactive,
                 _tools(interactive, fit_filter=True), _stat_boxes(len(jobs), cards, sts), reminders,
                 SCRIPT + (STATUS_SCRIPT if interactive else ""))


HINT = """<p class="hint">To mark jobs as Applied / Interested / Not for me, run <code>python3 -m jobagent view</code>
in Terminal (this file on its own can't save your clicks).</p>"""

SCRIPT = """
const list = document.getElementById('list'), q = document.getElementById('q'), sortSel = document.getElementById('sort');
const minFit = document.getElementById('minfit'), hideBox = document.getElementById('hide');
let filter = 'all';
function apply() {
  if (!list) return;
  const term = q ? q.value.trim().toLowerCase() : ''; let shown = 0;
  const cards = [...list.querySelectorAll('.card')];
  const key = sortSel ? sortSel.value : 'rank';
  cards.sort((a, b) => key === 'rank' ? a.dataset.rank - b.dataset.rank
    : key === 'fit' ? (b.dataset.fit - a.dataset.fit) || (a.dataset.rank - b.dataset.rank)
    : (a.dataset.days - b.dataset.days) || (a.dataset.rank - b.dataset.rank));
  cards.forEach(c => list.appendChild(c));
  const mf = minFit ? +minFit.value : 0;
  cards.forEach(c => {
    const st = (c.className.match(/s-(\\w+)/) || [, 'reported'])[1];
    const ok = (!term || c.dataset.text.includes(term)) && (filter === 'all' || st === filter)
      && (+c.dataset.fit >= mf || !mf) && !(hideBox && hideBox.checked && st === 'not_interested');
    c.style.display = ok ? '' : 'none'; if (ok) shown++;
  });
  const none = document.getElementById('none'); if (none) none.hidden = shown > 0 || !cards.length;
}
document.querySelectorAll('.chip[data-f]').forEach(ch => ch.addEventListener('click', () => {
  filter = ch.dataset.f; document.querySelectorAll('.chip[data-f]').forEach(x => x.classList.toggle('on', x === ch)); apply();
}));
if (q) q.addEventListener('input', apply);
if (sortSel) sortSel.addEventListener('change', apply);
if (minFit) minFit.addEventListener('change', apply);
if (hideBox) { try { hideBox.checked = localStorage.getItem('hideNI') === '1'; } catch (e) {}
  hideBox.addEventListener('change', () => { try { localStorage.setItem('hideNI', hideBox.checked ? '1' : '0'); } catch (e) {} apply(); }); }
apply();
"""

STATUS_SCRIPT = """
async function save(card, status, note) {
  const body = {id: card.dataset.id, status, company: card.dataset.company, title: card.dataset.title,
                url: card.dataset.url, deadline: card.dataset.deadline || '', location: card.dataset.location || '',
                fit: card.dataset.fit || ''};
  if (note !== undefined) body.note = note;
  let r;
  try { r = await fetch('/api/status', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                        body: JSON.stringify(body)}); } catch (e) { r = null; }
  if (!r || !r.ok) { alert('Could not save. Is "python3 -m jobagent view" still running in Terminal?'); return false; }
  return true;
}
document.querySelectorAll('.card').forEach(card => card.querySelectorAll('.st[data-s]').forEach(btn => {
  btn.addEventListener('click', async () => {
    const s = btn.classList.contains('on') ? 'reported' : btn.dataset.s;
    if (!await save(card, s)) return;
    card.querySelectorAll('.st[data-s]').forEach(b => b.classList.toggle('on', b.dataset.s === s));
    card.className = 'card s-' + s;
    const stats = document.querySelectorAll('.stat b');
    if (stats.length > 2) { stats[1].textContent = document.querySelectorAll('.card.s-applied').length;
      stats[2].textContent = document.querySelectorAll('.card.s-interested').length; }
    if (typeof apply === 'function') apply();
  });
}));
document.querySelectorAll('.card select.stage').forEach(sel => sel.addEventListener('change', async () => {
  const card = sel.closest('.card');
  if (await save(card, sel.value)) { card.className = 'card s-' + sel.value; flash(card); }
}));
document.querySelectorAll('.card button.savenote').forEach(b => b.addEventListener('click', async () => {
  const card = b.closest('.card');
  if (await save(card, card.querySelector('select.stage').value, card.querySelector('textarea.note').value)) flash(card);
}));
function flash(card) { const s = card.querySelector('.saved'); if (s) { s.hidden = false; setTimeout(() => s.hidden = true, 1500); } }
"""

STAGE_LABELS = (("interested", "★ Interested (not applied)"), ("applied", "✓ Applied"),
                ("interviewing", "💬 Interviewing"), ("offer", "🎉 Offer"), ("rejected", "✕ Rejected"),
                ("reported", "Remove from tracker"))


def applications_html(jobs: dict, reminders: list[str] | None = None) -> str:
    """'My applications': every job you've marked, grouped by stage, with a stage picker and notes."""
    esc = html.escape
    order = ("interviewing", "offer", "applied", "interested", "rejected")
    labels = {"interviewing": "Interviewing", "offer": "Offers", "applied": "Applied, waiting",
              "interested": "Interested, not applied yet", "rejected": "Rejected"}
    groups = {k: [] for k in order}
    for jid, j in jobs.items():
        if j.get("status") in groups:
            groups[j["status"]].append((jid, j))
    parts = []
    for key in order:
        items = sorted(groups[key], key=lambda x: x[1].get("status_date", ""), reverse=True)
        if not items and key in ("offer", "rejected"):
            continue
        cards = []
        for jid, j in items:
            opts = "".join(f'<option value="{k}"{" selected" if k == key else ""}>{lab}</option>' for k, lab in STAGE_LABELS)
            dates = " · ".join(f"{h[1]} {h[0]}" for h in j.get("history", [])[-4:]) or f"marked {j.get('status_date', '')}"
            dl = f" · deadline {esc(j['deadline'])}" if j.get("deadline") else ""
            cards.append(f"""<article class="card s-{key}" data-id="{esc(jid)}" data-company="{esc(j.get('company', ''))}"
 data-title="{esc(j.get('title', ''))}" data-url="{esc(j.get('url', ''))}" data-deadline="{esc(j.get('deadline', ''))}">
  <div class="top-line">
    <div class="logo" style="background:hsl({_hue(j.get('company', ''))} 45% 45%)">{esc(_initials(j.get('company', '')))}</div>
    <div class="head"><h2>{esc(j.get('title', ''))}</h2>
      <div class="meta">{esc(j.get('company', ''))} · {esc(dates)}{dl}</div></div>
    <a class="apply" href="{esc(j.get('url', ''))}" target="_blank" rel="noopener">Posting ↗</a></div>
  <div class="actions"><select class="stage">{opts}</select></div>
  <div class="actions" style="display:block"><textarea class="note" placeholder="Notes: who you spoke to, next step, dates…">{esc(j.get('note', ''))}</textarea>
  <button class="st savenote">Save note</button><span class="saved" hidden>Saved ✓</span></div>
</article>""")
        parts.append(f"<h3>{labels[key]} ({len(items)})</h3>" + ("".join(cards) or '<p class="empty">None yet.</p>'))
    return _page("My applications", "change the stage as things happen", "/applied", "".join(parts), True,
                 reminders=reminders, script=STATUS_SCRIPT)


def stats_html(s: dict) -> str:
    esc = html.escape
    st = s["stages"]
    boxes = "".join(f'<div class="big"><b>{v}</b><span>{lab}</span></div>' for v, lab in (
        (s["applied_total"], "applied"), (s["replied_total"], "replies"), (s["interview_total"], "interviews / offers"),
        (st["offer"], "offers"), (st["rejected"], "rejected"), (st["interested"], "interested, not applied")))
    rate = f'{round(100 * s["interview_total"] / s["applied_total"])}%' if s["applied_total"] else "—"
    tables = []
    for dim, label in (("family", "Role type"), ("region", "Region"), ("source", "Where the job was found")):
        rows = s["by"][dim]
        if not rows:
            continue
        trs = "".join(f"<tr><td>{esc(k)}</td><td>{r['applied']}</td><td>{r['replied']}</td><td>{r['interviews']}</td>"
                      f"<td>{round(100 * r['interviews'] / r['applied']) if r['applied'] else 0}%</td></tr>"
                      for k, r in sorted(rows.items(), key=lambda x: -x[1]["applied"]))
        tables.append(f"<h3>{label}</h3><table><tr><th>{label}</th><th>Applied</th><th>Replies</th><th>Interviews</th>"
                      f"<th>Interview rate</th></tr>{trs}</table>")
    cal = s.get("calibration", {})
    cal_rows = "".join(f"<tr><td>{esc(lab)}</td><td>{cal[k]['n']}</td><td>{cal[k]['avg']}</td></tr>"
                       for k, lab in (("applied", "Applied (any stage)"), ("interested", "Interested"),
                                      ("not_interested", "Not for me")) if cal.get(k, {}).get("n"))
    cal_html = (f"<h3>Do Claude's scores match your choices?</h3><table><tr><th>You marked</th><th>Jobs</th>"
                f"<th>Avg Claude fit (1–5)</th></tr>{cal_rows}</table><p class='sub'>Good scoring: Applied/Interested "
                f"average clearly higher than Not for me. If not, tell Claude what it gets wrong.</p>") if cal_rows else ""
    tables.insert(0, cal_html)
    inner = (f'<div class="grid">{boxes}</div><p class="sub" style="margin-top:14px">Interview rate overall: <b>{rate}</b>. '
             f'Mark replies on the My applications tab to keep this accurate.</p>' + "".join(tables)
             + ("" if tables else '<p class="empty">Mark jobs as Applied to see which kinds of roles reply.</p>'))
    return _page("Stats", "what's working", "/stats", inner, True)
