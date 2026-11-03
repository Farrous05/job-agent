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
    for f in sorted((data_dir / "candidates").glob("*.json")):
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
@media (max-width:600px){header.top{position:static}.top-line{flex-wrap:wrap}.head{flex-basis:calc(100% - 60px)}
.apply{margin-left:56px}nav{margin-left:0;width:100%}nav a{margin:0 14px 0 0}.stats .stat{padding:4px 10px}
.tags,.why,.flags,details,.lead,.actions{margin-left:0}}
"""


def write_html(md_path: Path, data_dir: Path, out: Path | None, others: list[Path],
               statuses: dict | None = None, interactive: bool = False) -> int | str:
    """Builds the shortlist page. With interactive=True (served by `jobagent view`) each card gets
    Applied / Interested / Not for me buttons; returns the HTML instead of writing it when out is None."""
    rows = parse_shortlist(md_path)
    statuses = statuses or {}
    desc = _descriptions(data_dir)
    esc = html.escape
    cards, counts = [], {"applied": 0, "interested": 0, "not_interested": 0}
    for r in rows:
        sid = r.get("id", "")
        d = desc.get(sid) or next((v for k, v in desc.items() if sid and (sid.endswith(k) or k.endswith(sid))), "")
        fitm = re.match(r"\s*(\d)/5", r["why"])
        fit = int(fitm.group(1)) if fitm else 0
        company_raw = r["company"].replace("**", "")
        applied_prev = "already applied" in company_raw.lower()
        company = re.sub(r"\s*\(already applied\)", "", company_raw).strip()
        new = "(new)" in r["why"]
        why_full = re.sub(r"^\s*\d/5:\s*", "", r["why"]).replace("(new)", "").strip()
        why, _, flags = why_full.partition("⚠")
        st = statuses.get(sid, "reported")
        if st in counts:
            counts[st] += 1
        days = _deadline_days(r["deadline"])
        tags = []
        if fit:
            tags.append(f'<span class="tag fit {"good" if fit >= 4 else "warn" if fit == 3 else "bad"}">{fit}/5 fit</span>')
        if days is not None:
            cls = "bad" if days <= 14 else "warn" if days <= 30 else ""
            when = "closed" if days < 0 else "today" if days == 0 else f"{days} days left"
            tags.append(f'<span class="tag {cls}">Deadline {esc(r["deadline"])} · {when}</span>')
        elif r["deadline"] and r["deadline"] not in ("—", "Not stated"):
            tags.append(f'<span class="tag">Deadline: {esc(r["deadline"])}</span>')
        tags.append(f'<span class="tag {_sponsor_class(r["sponsorship"])}">{esc(r["sponsorship"])}</span>')
        if new:
            tags.append('<span class="tag">New company</span>')
        if applied_prev:
            tags.append('<span class="tag good">Already applied</span>')
        summ = _summary(d)
        more = _summary(d, 2500)
        body = ""
        if summ and len(more) > len(summ) + 40:
            body = f'<details><summary>Show description</summary><p>{esc(more)}</p></details>'
        elif summ:
            body = f'<p class="lead">{esc(summ)}</p>'
        buttons = "".join(
            f'<button class="st {k}{" on" if st == k else ""}" data-s="{k}">{label}</button>'
            for k, label in (("applied", "✓ Applied"), ("interested", "★ Interested"), ("not_interested", "✕ Not for me")))
        hue = _hue(company)
        cards.append(f"""
<article class="card s-{st}" data-id="{esc(sid)}" data-company="{esc(company)}" data-title="{esc(r['title'])}"
 data-url="{esc(r['url'])}" data-rank="{r['rank']}" data-fit="{fit}" data-days="{days if days is not None else 9999}"
 data-text="{esc((r['title'] + ' ' + company + ' ' + r['location']).lower())}">
  <div class="top-line">
    <div class="logo" style="background:hsl({hue} 45% 45%)">{esc(_initials(company))}</div>
    <div class="head"><h2><span class="rank">{r['rank']}.</span>{esc(r['title'])}</h2>
      <div class="meta">{esc(company)} · {esc(r['location'])}</div></div>
    <a class="apply" href="{esc(r['url'])}" target="_blank" rel="noopener">Apply ↗</a>
  </div>
  <div class="tags">{''.join(tags)}</div>
  <p class="why">{esc(why.strip().rstrip('.'))}.</p>
  {f'<div class="flags">⚠ {esc(flags.strip())}</div>' if flags.strip() else ''}
  {body}
  {f'<div class="actions">{buttons}</div>' if interactive else ''}
</article>""")
    href = (lambda o: f"/s/{o.stem}") if interactive else (lambda o: f"{o.stem}.html")
    older = "".join(f'<li><a href="{esc(href(o))}">{esc(o.stem)}</a></li>' for o in reversed(others) if o != md_path)
    stats = (f'<div class="stat"><b>{len(rows)}</b>jobs</div>'
             f'<div class="stat"><b>{counts["applied"]}</b>applied</div>'
             f'<div class="stat"><b>{counts["interested"]}</b>interested</div>'
             f'<div class="stat"><b>{sum(1 for c in cards if "tag fit good" in c)}</b>strong fits (4–5/5)</div>')
    status_chips = ("" if not interactive else
                    '<button class="chip" data-f="reported">Not marked</button>'
                    '<button class="chip" data-f="interested">Interested</button>'
                    '<button class="chip" data-f="applied">Applied</button>'
                    '<label class="chip"><input type="checkbox" id="hide"> hide "not for me"</label>')
    nav = ('<nav><a class="cur" href="/">Shortlist</a><a href="/applied">My applications</a></nav>' if interactive else "")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Job shortlist</title><style>{CSS}</style></head>
<body><main>
<header class="top">
  <div class="row1"><h1>Your job shortlist</h1><span class="date">{esc(md_path.stem)}</span>{nav}</div>
  <div class="stats">{stats}</div>
  <div class="tools"><input type="search" id="q" placeholder="Search jobs…">
    <button class="chip on" data-f="all">All</button>{status_chips}
    <select id="sort"><option value="rank">Sort: best match</option><option value="fit">Sort: fit score</option>
    <option value="days">Sort: deadline soonest</option></select></div>
</header>
{'' if interactive else HINT}
<div id="list">{''.join(cards) or '<p class="empty">No roles in this shortlist.</p>'}</div>
<p class="empty" id="none" hidden>No jobs match these filters.</p>
{f'<h3>Earlier shortlists</h3><ul class="older">{older}</ul>' if older else ''}
</main><script>{SCRIPT}{STATUS_SCRIPT if interactive else ''}</script></body></html>"""
    if out is None:
        return page
    out.write_text(page)
    return len(rows)


HINT = """<p class="hint">To mark jobs as Applied / Interested / Not for me, run <code>python3 -m jobagent view</code>
in Terminal (this file on its own can't save your clicks).</p>"""

SCRIPT = """
const list = document.getElementById('list'), q = document.getElementById('q'), sortSel = document.getElementById('sort');
let filter = 'all';
const hideBox = document.getElementById('hide');
function apply() {
  const term = q.value.trim().toLowerCase(); let shown = 0;
  const cards = [...list.querySelectorAll('.card')];
  const key = sortSel.value;
  cards.sort((a, b) => key === 'rank' ? a.dataset.rank - b.dataset.rank
    : key === 'fit' ? (b.dataset.fit - a.dataset.fit) || (a.dataset.rank - b.dataset.rank)
    : (a.dataset.days - b.dataset.days) || (a.dataset.rank - b.dataset.rank));
  cards.forEach(c => list.appendChild(c));
  cards.forEach(c => {
    const st = (c.className.match(/s-(\\w+)/) || [, 'reported'])[1];
    const ok = (!term || c.dataset.text.includes(term)) && (filter === 'all' || st === filter)
      && !(hideBox && hideBox.checked && st === 'not_interested');
    c.style.display = ok ? '' : 'none'; if (ok) shown++;
  });
  document.getElementById('none').hidden = shown > 0 || !cards.length;
}
document.querySelectorAll('.chip[data-f]').forEach(ch => ch.addEventListener('click', () => {
  filter = ch.dataset.f; document.querySelectorAll('.chip[data-f]').forEach(x => x.classList.toggle('on', x === ch)); apply();
}));
q.addEventListener('input', apply); sortSel.addEventListener('change', apply);
if (hideBox) { try { hideBox.checked = localStorage.getItem('hideNI') === '1'; } catch (e) {}
  hideBox.addEventListener('change', () => { try { localStorage.setItem('hideNI', hideBox.checked ? '1' : '0'); } catch (e) {} apply(); }); }
apply();
"""

STATUS_SCRIPT = """
document.querySelectorAll('.card').forEach(card => card.querySelectorAll('.st').forEach(btn => {
  btn.addEventListener('click', async () => {
    const s = btn.classList.contains('on') ? 'reported' : btn.dataset.s;
    let r;
    try {
      r = await fetch('/api/status', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: card.dataset.id, status: s, company: card.dataset.company,
                              title: card.dataset.title, url: card.dataset.url})});
    } catch (e) { r = null; }
    if (!r || !r.ok) { alert('Could not save. Is "python3 -m jobagent view" still running in Terminal?'); return; }
    card.querySelectorAll('.st').forEach(b => b.classList.toggle('on', b.dataset.s === s));
    card.className = 'card s-' + s;
    const stats = document.querySelectorAll('.stat b');
    stats[1].textContent = document.querySelectorAll('.card.s-applied').length;
    stats[2].textContent = document.querySelectorAll('.card.s-interested').length;
    apply();
  });
}));
"""


def applications_html(jobs: dict) -> str:
    """'My applications' page: everything you marked Applied or Interested, newest first."""
    esc = html.escape
    groups = {"applied": [], "interested": []}
    for j in jobs.values():
        if j.get("status") in groups:
            groups[j["status"]].append(j)
    parts = []
    for key, label in (("applied", "Applied"), ("interested", "Interested, not applied yet")):
        items = sorted(groups[key], key=lambda j: j.get("status_date", ""), reverse=True)
        rows = "".join(f"""<article class="card s-{key}"><div class="top-line">
  <div class="logo" style="background:hsl({_hue(j.get('company', ''))} 45% 45%)">{esc(_initials(j.get('company', '')))}</div>
  <div class="head"><h2>{esc(j.get('title', ''))}</h2><div class="meta">{esc(j.get('company', ''))} · marked {esc(j.get('status_date', ''))}</div></div>
  <a class="apply" href="{esc(j.get('url', ''))}" target="_blank" rel="noopener">Posting ↗</a></div></article>""" for j in items)
        parts.append(f"<h3>{label} ({len(items)})</h3>{rows or '<p class=empty>None yet.</p>'}")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>My applications</title><style>{CSS}</style></head>
<body><main><header class="top"><div class="row1"><h1>My applications</h1>
<nav><a href="/">Shortlist</a><a class="cur" href="/applied">My applications</a></nav></div></header>
{''.join(parts)}</main></body></html>"""
