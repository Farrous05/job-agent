"""Markdown output for shortlist/YYYY-MM-DD.md."""
from __future__ import annotations

import html
import urllib.parse
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


def deadline_date(text: str):
    """A deadline like '22 Nov 2026', 'November 22, 2026', '2026-11-22' or '22/11/2026' (UK order) as a date."""
    from datetime import date
    t = (text or "").lower()
    try:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", t)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*\.?,?\s+(\d{4})", t)
        if m and m.group(2) in MONTHS:
            return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
        m = re.search(r"\b([a-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", t)
        if m and m.group(1) in MONTHS:
            return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    except ValueError:
        return None
    return None


def _deadline_days(text: str) -> int | None:
    """Days until a deadline; None if there's no date."""
    from datetime import date
    d = deadline_date(text)
    return None if d is None else (d - date.today()).days


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
.fpanel{width:100%;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-top:4px;
max-height:46vh;overflow:auto} .fsec{display:grid;grid-template-columns:70px 1fr;gap:6px 10px;align-items:start;
padding:6px 0;border-bottom:1px solid var(--line)} .fsec:last-child{border-bottom:0}
.fsec>b{grid-column:1;grid-row:1/span 3;font-size:13px;color:var(--mute);padding-top:4px}
.fsec>.fchips{grid-column:2;display:flex;flex-wrap:wrap;gap:6px;min-width:0} .fc{font:inherit;font-size:12.5px;padding:4px 10px;border-radius:99px;
border:1px solid var(--line);background:transparent;color:var(--ink);cursor:pointer}
.fc .n{color:var(--mute);font-size:11.5px} .fc.on{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.fc.on .n{color:inherit;opacity:.8} .fc.zero{opacity:.4} .resline{width:100%;font-size:13px;color:var(--mute)}
button.link{font:inherit;font-size:13px;background:none;border:0;color:var(--accent);cursor:pointer;padding:0 4px}
.more-wrap{text-align:center;margin:10px 0} .tag.fam{background:var(--soft);color:var(--ink);font-weight:600}
#list.compact .card{padding:11px 14px;margin-bottom:8px} #list.compact .logo{width:34px;height:34px;font-size:13px}
#list.compact h2{font-size:15.5px} #list.compact .meta{font-size:13px}
#list.compact .tags,#list.compact .why,#list.compact .flags,#list.compact .actions{margin-left:48px}
#list.compact .tags{margin-top:7px} #list.compact .why{margin-top:6px;font-size:14px;display:-webkit-box;
-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden} #list.compact details,#list.compact .lead{display:none}
#list.compact .actions{margin-top:8px} #list.compact .st{padding:4px 10px;font-size:12.5px}
#list.compact .apply{padding:6px 12px;font-size:13px}
@media (max-width:600px){header.top{position:static}.top-line{flex-wrap:wrap}.head{flex-basis:calc(100% - 60px)}
.apply{margin-left:56px}nav{margin-left:0;width:100%}nav a{margin:0 14px 0 0}.stats .stat{padding:4px 10px}
.tags,.why,.flags,details,.lead,.actions{margin-left:0}
#list.compact .tags,#list.compact .why,#list.compact .flags,#list.compact .actions{margin-left:0}
#list.compact .apply{margin-left:48px} .fsec{grid-template-columns:1fr} .fsec>b{grid-row:auto;padding:0}
.fsec>.fchips{grid-column:1} .fpanel{max-height:none} .tools input[type=search]{min-width:100%}
#list.compact .top-line{flex-wrap:nowrap;gap:10px} #list.compact .head{flex-basis:auto}
#list.compact .apply{margin-left:0;padding:5px 10px} #list.compact .logo{display:none}
#list.compact .tags{gap:4px} #list.compact .tag{font-size:12px;padding:2px 7px}
.stats{flex-wrap:nowrap;overflow-x:auto} .stats .stat{white-space:nowrap}}
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


def _short_loc(loc: str) -> str:
    parts = [x.strip() for x in re.split(r";|\s\|\s", loc or "") if x.strip()]
    return loc if len(parts) <= 2 else f"{'; '.join(parts[:2])} +{len(parts) - 2} more"


def _short_sponsor(t: str) -> str:
    low = (t or "").lower()
    if low.startswith("eu role: no sponsorship needed"):
        return "EU: no visa needed"
    if low == "not stated":
        return "Visa: not stated"
    return t


def _card(j: dict, st: str, interactive: bool, compact: bool = False) -> str:
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
        sp = _short_sponsor(j["sponsorship"]) if compact else j["sponsorship"]
        tags.append(f'<span class="tag {_sponsor_class(j["sponsorship"])}" title="{esc(j["sponsorship"])}">{esc(sp)}</span>')
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
    <div class="head"><h2>{rank}{esc(j['title'])}</h2><div class="meta" title="{esc(j['location'])}">{esc(j['company'])} · {esc(_short_loc(j['location']) if compact else j['location'])}</div></div>
    <a class="apply" href="{esc(j['url'])}" target="_blank" rel="noopener">Apply ↗</a>
  </div>
  <div class="tags">{''.join(tags)}</div>
  {f'<p class="why">{esc(j["reason"].rstrip("."))}.</p>' if j['reason'] else ''}
  {f'<div class="flags">⚠ {esc(j["flags"])}</div>' if j['flags'] else ''}
  {body}
  {f'<div class="actions">{buttons}</div>' if interactive else ''}
</article>"""


TABS = (("/", "Top picks"), ("/all", "All matches"), ("/applied", "My applications"), ("/cv", "CV"),
        ("/stats", "Stats"))


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


COUNTRIES = {
    "United Kingdom": ["united kingdom", "uk", "england", "scotland", "wales", "london", "cambridge", "oxford",
                       "edinburgh", "manchester", "bristol", "belfast", "glasgow", "leeds", "birmingham", "reading"],
    "France": ["france", "fr", "paris", "île-de-france", "ile-de-france", "lyon", "toulouse", "grenoble", "nice",
               "sophia antipolis", "lille", "bordeaux", "nantes", "montpellier", "marseille", "rennes"],
    "Germany": ["germany", "deutschland", "de", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne",
                "köln", "stuttgart", "düsseldorf", "leipzig", "heidelberg", "karlsruhe", "tübingen", "darmstadt"],
    "Netherlands": ["netherlands", "nederland", "nl", "amsterdam", "rotterdam", "eindhoven", "utrecht", "the hague",
                    "delft", "veldhoven"],
    "Switzerland": ["switzerland", "ch", "zurich", "zürich", "geneva", "lausanne", "basel", "zug", "bern"],
    "Ireland": ["ireland", "ie", "dublin", "cork", "galway"],
    "Spain": ["spain", "españa", "es", "madrid", "barcelona", "valencia", "seville", "malaga", "málaga"],
    "Italy": ["italy", "italia", "it", "milan", "milano", "rome", "roma", "turin", "torino", "bologna"],
    "Portugal": ["portugal", "pt", "lisbon", "lisboa", "porto"],
    "Belgium": ["belgium", "be", "brussels", "antwerp", "ghent", "leuven"],
    "Sweden": ["sweden", "se", "stockholm", "gothenburg", "malmö"],
    "Denmark": ["denmark", "dk", "copenhagen", "aarhus"],
    "Norway": ["norway", "no", "oslo", "bergen", "trondheim"],
    "Finland": ["finland", "fi", "helsinki", "espoo"],
    "Poland": ["poland", "pl", "warsaw", "krakow", "kraków", "wroclaw", "wrocław", "gdansk", "gdańsk"],
    "Austria": ["austria", "at", "vienna", "wien"],
    "Czechia": ["czechia", "czech republic", "cz", "prague", "brno"],
    "Other EU": ["luxembourg", "romania", "bucharest", "cluj", "hungary", "budapest", "bulgaria", "sofia", "greece",
                 "athens", "croatia", "zagreb", "slovenia", "ljubljana", "slovakia", "bratislava", "estonia", "tallinn",
                 "latvia", "riga", "lithuania", "vilnius", "cyprus", "limassol", "malta", "iceland"],
}
_COUNTRY_RX = [(c, re.compile(r"(?<![a-zà-ÿ])(" + "|".join(re.escape(w) for w in sorted(ws, key=len, reverse=True)
                                                          if len(w) > 2) + r")(?![a-zà-ÿ])"),
                {w for w in ws if len(w) <= 2}) for c, ws in COUNTRIES.items()]
FAMILY_LABELS = (("mlai", "ML / AI"), ("data_science", "Data science"), ("quant", "Quant"), ("software", "Software"))
HUBS = ("london", "paris", "amsterdam", "berlin", "munich", "münchen", "zurich", "zürich", "dublin")


def countries_of(location: str) -> list[str]:
    t = (location or "").lower()
    segs = {x.strip() for x in re.split(r"[;,|/]", t)}          # 2-letter codes ("fr", "de") only as a whole part
    out = [c for c, rx, codes in _COUNTRY_RX if rx.search(t) or segs & codes]
    if not out and "remote" in t:
        out = ["Remote"]
    return out or ["Other"]


def _age_days(posted: str) -> int:
    from datetime import date
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", posted or "")
    if not m:
        return 9999
    try:
        return (date.today() - date(int(m.group(1)), int(m.group(2)), int(m.group(3)))).days
    except ValueError:
        return 9999


def all_matches_html(run: Path | None, statuses: dict, interactive: bool = True,
                     reminders: list[str] | None = None, applied_companies: set | None = None) -> str:
    """Every role Claude scored in the latest run, with a filter panel (fit, role type, country, status,
    deadline, posted date, extras), live counts, a compact/detailed view and 'show more' paging."""
    esc = html.escape
    matches = []
    if run is not None and (run / "matches.json").exists():
        matches = json.loads((run / "matches.json").read_text()).get("matches", [])
    applied_co = {c.lower() for c in (applied_companies or set())}
    cards, sts, country_n = [], [], {}
    for i, m in enumerate(matches, 1):
        j = _job(m, {})
        j["rank"] = i
        st = statuses.get(j["id"], "reported")
        fams = set(m.get("families") or [])
        fam = " ".join(sorted({"mlai" if f in ("ml", "ai") else f for f in fams})) or "software"
        cs = countries_of(j["location"])
        for c in cs:
            country_n[c] = country_n.get(c, 0) + 1
        days = _deadline_days(j["deadline"])
        extra = {"fam": fam, "countries": "|".join(cs), "region": m.get("region", ""),
                 "age": _age_days(m.get("posted", "")), "new": "1" if j["new"] else "",
                 "appco": "1" if (j["applied_prev"] or j["company"].lower() in applied_co) else "",
                 "hub": "1" if any(h in j["location"].lower() for h in HUBS) else "",
                 "seen": "1" if j.get("seen") else "", "dl": "" if days is None else str(days)}
        attrs = " ".join(f'data-{k}="{esc(str(v))}"' for k, v in extra.items())
        card = _card(j, st, interactive, compact=True).replace("<article ", f"<article {attrs} ", 1)
        fam_tags = "".join(f'<span class="tag fam">{lab}</span>' for k, lab in FAMILY_LABELS if k in fam.split())
        age = extra["age"]
        if age < 9999:
            fam_tags += f'<span class="tag">{"today" if age <= 0 else f"posted {age}d ago"}</span>'
        cards.append(card.replace('<div class="tags">', f'<div class="tags">{fam_tags}', 1))
        sts.append(st)
    empty = ("<p class=empty>No scored roles yet. Run a job search first (findjobs, or /run in Telegram): Claude "
             "scores every role that passes your filters.</p>")
    top_c = sorted(country_n.items(), key=lambda x: -x[1])

    def chips(group: str, opts, multi: bool = True) -> str:
        return f'<div class="fchips" data-group="{group}" data-multi="{1 if multi else 0}">' + "".join(
            f'<button class="fc" data-v="{esc(v)}">{esc(lab)}<span class="n"></span></button>' for v, lab in opts) + "</div>"
    panel = f"""
<div id="fpanel" class="fpanel">
  <div class="fsec"><b>Fit</b>{chips("fit", (("5", "5/5"), ("4", "4+"), ("3", "3+"), ("0", "Any")), False)}</div>
  <div class="fsec"><b>Role</b>{chips("fam", FAMILY_LABELS)}</div>
  <div class="fsec"><b>Where</b>{chips("region", (("uk", "UK"), ("eu", "EU")))}
    {chips("country", [(c, c) for c, _ in top_c])}
    {chips("hub", (("1", "Big hubs only: London, Paris, Amsterdam, Berlin, Munich, Zurich, Dublin"),))}</div>
  <div class="fsec"><b>Status</b>{chips("status", (("reported", "Not marked"), ("interested", "★ Interested"),
                                                    ("applied", "✓ Applied"), ("not_interested", "✕ Not for me")))}</div>
  <div class="fsec"><b>Deadline</b>{chips("dl", (("14", "Closes within 14 days"), ("any", "Has a deadline"),
                                                  ("open", "Not closed")), False)}</div>
  <div class="fsec"><b>Posted</b>{chips("age", (("7", "Last 7 days"), ("30", "Last 30 days")), False)}</div>
  <div class="fsec"><b>More</b>{chips("more", (("new", "New companies only"), ("noappco", "Hide companies I applied to"),
                                              ("noseen", "Hide shown before")))}</div>
</div>"""
    tools = f"""<input type="search" id="q" placeholder="Search title, company, city, reason…">
<button class="chip" id="ftoggle">Filters <span id="fcount"></span></button>
<select id="sort"><option value="rank">Best match</option><option value="fit">Fit score</option>
<option value="days">Deadline soonest</option><option value="age">Newest posted</option>
<option value="company">Company A–Z</option></select>
<button class="chip" id="view">Detailed view</button>{panel}
<div class="resline"><span id="shown"></span> <button class="link" id="clear">Clear filters</button></div>"""
    inner = (f'<div id="list" class="compact">{"".join(cards) or empty}</div>'
             f'<p class="empty" id="none" hidden>No jobs match these filters. <button class="link" id="clear2">'
             f'Clear filters</button></p><div class="more-wrap"><button class="chip" id="more" hidden>Show more</button></div>')
    return _page("All matches", f"{run.name if run else ''} · {len(cards)} scored roles", "/all", inner, interactive,
                 tools, _stat_boxes(len(cards), cards, sts), reminders,
                 ALL_SCRIPT + (STATUS_SCRIPT if interactive else ""))


ALL_SCRIPT = """
const list = document.getElementById('list'), q = document.getElementById('q'), sortSel = document.getElementById('sort');
const PAGE = 40; let limit = PAGE;
const DEF = {fit: ['4'], status: ['reported', 'interested', 'applied']};
let F = {};
try { F = JSON.parse(localStorage.getItem('allFilters') || 'null') || {}; } catch (e) {}
if (!Object.keys(F).length) F = JSON.parse(JSON.stringify(DEF));
const cards = list ? [...list.querySelectorAll('.card')] : [];
cards.forEach(c => { c.dataset.text = (c.dataset.text + ' ' + (c.querySelector('.why') || {textContent: ''}).textContent).toLowerCase(); });
const stOf = c => (c.className.match(/s-(\\w+)/) || [, 'reported'])[1];
const TESTS = {
  fit: (c, v) => v.some(x => +c.dataset.fit >= +x),
  fam: (c, v) => v.some(x => c.dataset.fam.split(' ').includes(x)),
  region: (c, v) => v.includes(c.dataset.region),
  country: (c, v) => v.some(x => c.dataset.countries.split('|').includes(x)),
  hub: (c, v) => c.dataset.hub === '1',
  status: (c, v) => v.includes(stOf(c)),
  dl: (c, v) => v[0] === '14' ? (c.dataset.dl !== '' && +c.dataset.dl >= 0 && +c.dataset.dl <= 14)
              : v[0] === 'any' ? c.dataset.dl !== '' : (c.dataset.dl === '' || +c.dataset.dl >= 0),
  age: (c, v) => +c.dataset.age <= +v[0],
  more: (c, v) => (!v.includes('new') || c.dataset.new === '1') && (!v.includes('noappco') || c.dataset.appco !== '1')
                  && (!v.includes('noseen') || c.dataset.seen !== '1'),
};
function passes(c, skip) {
  const term = q ? q.value.trim().toLowerCase() : '';
  if (term && !term.split(/\\s+/).every(t => c.dataset.text.includes(t))) return false;
  for (const g in F) { if (g === skip || !F[g] || !F[g].length) continue; if (!TESTS[g](c, F[g])) return false; }
  return true;
}
function saveFilters() { try { localStorage.setItem('allFilters', JSON.stringify(F)); } catch (e) {} }
function apply(resetLimit) {
  if (!list) return; if (resetLimit) limit = PAGE;
  const key = sortSel ? sortSel.value : 'rank';
  const by = {rank: (a, b) => a.dataset.rank - b.dataset.rank,
    fit: (a, b) => (b.dataset.fit - a.dataset.fit) || (a.dataset.rank - b.dataset.rank),
    days: (a, b) => ((a.dataset.dl === '' ? 9999 : +a.dataset.dl) - (b.dataset.dl === '' ? 9999 : +b.dataset.dl)) || (a.dataset.rank - b.dataset.rank),
    age: (a, b) => (a.dataset.age - b.dataset.age) || (a.dataset.rank - b.dataset.rank),
    company: (a, b) => a.dataset.company.localeCompare(b.dataset.company) || (a.dataset.rank - b.dataset.rank)}[key];
  cards.sort(by).forEach(c => list.appendChild(c));
  let match = 0;
  cards.forEach(c => { const ok = passes(c); if (ok) match++; c.style.display = ok && match <= limit ? '' : 'none'; });
  document.querySelectorAll('.fchips').forEach(box => {
    const g = box.dataset.group;
    box.querySelectorAll('.fc').forEach(b => {
      const v = b.dataset.v, on = (F[g] || []).includes(v); b.classList.toggle('on', on);
      const n = cards.filter(c => passes(c, g) && TESTS[g](c, [v])).length;
      b.querySelector('.n').textContent = g === 'more' ? '' : ' ' + n; b.classList.toggle('zero', !n && !on);
    });
  });
  const active = Object.values(F).filter(v => v && v.length).length;
  document.getElementById('fcount').textContent = active ? '(' + active + ')' : '';
  document.getElementById('shown').textContent = 'Showing ' + Math.min(match, limit) + ' of ' + match + ' matching · ' + cards.length + ' scored';
  const more = document.getElementById('more'); more.hidden = match <= limit; more.textContent = 'Show more (' + (match - limit) + ' left)';
  const none = document.getElementById('none'); if (none) none.hidden = match > 0 || !cards.length;
  saveFilters();
}
document.querySelectorAll('.fchips').forEach(box => box.addEventListener('click', e => {
  const b = e.target.closest('.fc'); if (!b) return;
  const g = box.dataset.group, v = b.dataset.v, cur = F[g] || [];
  if (box.dataset.multi === '1') F[g] = cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v];
  else F[g] = cur.includes(v) ? [] : [v];
  if (g === 'fit' && F.fit[0] === '0') F.fit = [];
  apply(true);
}));
function clearAll() { F = {}; if (q) q.value = ''; apply(true); }
document.getElementById('clear').onclick = clearAll;
const c2 = document.getElementById('clear2'); if (c2) c2.onclick = clearAll;
document.getElementById('more').onclick = () => { limit += PAGE * 2; apply(false); };
const panel = document.getElementById('fpanel'), tog = document.getElementById('ftoggle');
let open = window.innerWidth > 700; try { const o = localStorage.getItem('fpanel'); if (o !== null) open = o === '1'; } catch (e) {}
function showPanel() { panel.hidden = !open; tog.classList.toggle('on', open); }
tog.onclick = () => { open = !open; try { localStorage.setItem('fpanel', open ? '1' : '0'); } catch (e) {} showPanel(); };
showPanel();
const view = document.getElementById('view');
let detailed = false; try { detailed = localStorage.getItem('detailed') === '1'; } catch (e) {}
function showView() { list && list.classList.toggle('compact', !detailed); view.textContent = detailed ? 'Compact view' : 'Detailed view'; }
view.onclick = () => { detailed = !detailed; try { localStorage.setItem('detailed', detailed ? '1' : '0'); } catch (e) {} showView(); };
showView();
let t; if (q) q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => apply(true), 120); });
if (sortSel) { try { sortSel.value = localStorage.getItem('allSort') || 'rank'; } catch (e) {}
  sortSel.addEventListener('change', () => { try { localStorage.setItem('allSort', sortSel.value); } catch (e) {} apply(true); }); }
apply(true);
"""


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
  if (await save(card, sel.value)) { card.className = 'card s-' + sel.value; flash(card);
    if (sel.value === 'interviewing') setTimeout(() => location.reload(), 600); }
}));
document.querySelectorAll('.card button.prep').forEach(b => b.addEventListener('click', async () => {
  const card = b.closest('.card');
  let r; try { r = await fetch('/api/prep', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id: card.dataset.id, company: card.dataset.company, title: card.dataset.title,
                          url: card.dataset.url})}); } catch (e) { r = null; }
  if (r && r.ok) { b.textContent = 'Prep queued: it arrives on Telegram in ~10 min'; b.disabled = true; }
  else alert('Could not queue it. Is the job page still running?');
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


def applications_html(jobs: dict, reminders: list[str] | None = None, preps: dict | None = None,
                      calendar_url: str = "") -> str:
    """'My applications': every job you've marked, grouped by stage, with a stage picker and notes.
    preps: job id -> "ready" or "queued" (interview prep packs)."""
    esc = html.escape
    preps = preps or {}
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
  <div class="actions"><select class="stage">{opts}</select>{_prep_bit(jid, key, preps)}</div>
  <div class="actions" style="display:block"><textarea class="note" placeholder="Notes: who you spoke to, next step, dates…">{esc(j.get('note', ''))}</textarea>
  <button class="st savenote">Save note</button><span class="saved" hidden>Saved ✓</span></div>
</article>""")
        parts.append(f"<h3>{labels[key]} ({len(items)})</h3>" + ("".join(cards) or '<p class="empty">None yet.</p>'))
    if calendar_url:
        parts.insert(0, f'<p class="sub">📅 Closing dates in your phone’s calendar: <a href="{esc(calendar_url)}">'
                        f'subscribe to the deadlines calendar</a> (or send /calendar to the bot).</p>')
    return _page("My applications", "change the stage as things happen", "/applied", "".join(parts), True,
                 reminders=reminders, script=STATUS_SCRIPT)


def _prep_bit(jid: str, stage: str, preps: dict) -> str:
    esc = html.escape
    st = preps.get(jid)
    if st == "ready":
        return f' <a class="st" href="/prep?id={urllib.parse.quote(jid)}">🎤 Interview prep</a>'
    if st == "queued":
        return ' <span class="sub">🎤 prep being written…</span>'
    if stage in ("interviewing", "applied"):
        return ' <button class="st prep">🎤 Write interview prep</button>'
    return ""


def md_html(md: str, title: str) -> str:
    """Tiny Markdown → HTML for prep packs (headings, bullets, bold, links, paragraphs)."""
    esc = html.escape
    out, in_list = [], False

    def inline(t: str) -> str:
        t = esc(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
        return re.sub(r'(?<!href=")(https?://[^\s<]+)', r'<a href="\1" target="_blank" rel="noopener">\1</a>', t)
    for line in md.splitlines():
        if line.strip().startswith("<!--"):
            continue
        m = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.*)", line)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(m.group(1))}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        h = re.match(r"^(#{1,4})\s+(.*)", line)
        if h:
            n = min(len(h.group(1)) + 1, 4)
            out.append(f"<h{n}>{inline(h.group(2))}</h{n}>")
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    return _page(title, "interview prep", "/applied", '<div class="card prepdoc">' + "".join(out) + "</div>", True)


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


def cv_html(pending: int, has_changes_pdf: bool, pdf_names: list[str], apps: list[dict], msg: str = "",
            images: list[str] | None = None) -> str:
    """CV tab: suggested changes with Accept / Reject, your CV and tailored CVs, application drafts."""
    esc = html.escape
    parts = []
    if msg:
        parts.append(f'<p class="remind">{esc(msg)}</p>')
    if pending:
        imgs = "".join(f'<img src="/file?p={esc(i)}" alt="CV changes" style="width:100%;border:1px solid var(--line);'
                       f'border-radius:12px;background:#fff;margin-bottom:10px">' for i in (images or []))
        viewer = ((imgs or "") + '<p class="sub"><a href="/file?p=cv/build/cv-changes.pdf" target="_blank">Open the PDF ↗</a></p>') \
            if has_changes_pdf else \
                 '<p class="sub">The changes PDF couldn\'t be built (LaTeX missing?). Text diff: <a href="/cv/diff">open</a>.</p>'
        parts.append(f"""<h3>Suggested changes to your CV ({pending} lines)</h3>
<p class="sub">Red = removed, blue = added. Nothing changes until you press Accept.</p>
<div class="actions" style="margin-left:0">
 <button class="apply" style="border:0;cursor:pointer" onclick="cvAct('accept')">✓ Accept changes</button>
 <button class="st" onclick="cvAct('reject')">✕ Reject</button></div>
<div style="margin-top:12px">{viewer}</div>""")
    else:
        parts.append('<h3>Suggested changes</h3><p class="empty">No suggested CV changes waiting.</p>')
    main = [n for n in pdf_names if n == "cv"]
    tailored = [n for n in pdf_names if n != "cv"]
    links = "".join(f'<li><a href="/file?p=cv/build/{esc(n)}.pdf" target="_blank">{esc(n)}.pdf</a></li>' for n in main + tailored)
    parts.append(f"<h3>Your CVs ({len(pdf_names)})</h3>" + (f'<ul class="older">{links}</ul>' if links else
                 '<p class="empty">No PDFs yet. <button class="st" onclick="cvAct(\'build\')">Build them</button></p>'))
    app_cards = []
    for a in apps:
        letter = (f'<a class="apply" href="/file?p=applications/{esc(a["name"])}/cover_letter.pdf" target="_blank">'
                  f'Cover letter PDF ↗</a>') if a["letter"] else '<span class="tag warn">no cover letter PDF</span>'
        app_cards.append(f"""<article class="card"><div class="top-line"><div class="head"><h2>{esc(a['name'])}</h2>
<div class="meta">applications/{esc(a['name'])}/</div></div>{letter}</div>
{f'<details><summary>Answers to the form</summary><pre style="white-space:pre-wrap">{esc(a["answers"])}</pre></details>' if a['answers'] else ''}
{f'<details><summary>Checklist</summary><pre style="white-space:pre-wrap">{esc(a["checklist"])}</pre></details>' if a['checklist'] else ''}
</article>""")
    parts.append(f"<h3>Application drafts ({len(apps)})</h3>" + ("".join(app_cards) or
                 '<p class="empty">None yet. In Claude (or Telegram) use /apply &lt;company&gt;.</p>'))
    script = """
async function cvAct(what) {
  if (what === 'reject' && !confirm('Throw the suggested CV changes away?')) return;
  if (what === 'accept' && !confirm('Apply the suggested changes to your CV?')) return;
  document.body.style.cursor = 'wait';
  const r = await fetch('/api/cv/' + what, {method: 'POST'});
  const t = await r.text(); location.href = '/cv?msg=' + encodeURIComponent(t);
}"""
    return _page("CV", "your CV, tailored CVs, cover letters", "/cv", "".join(parts), True, script=script)
