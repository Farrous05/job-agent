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


def write_html(md_path: Path, data_dir: Path, out: Path | None, others: list[Path],
               statuses: dict | None = None, interactive: bool = False) -> int | str:
    """Builds the shortlist page. With interactive=True (served by `jobagent view`) each card gets
    Applied / Interested / Not for me buttons; returns the HTML instead of writing it when out is None."""
    rows = parse_shortlist(md_path)
    statuses = statuses or {}
    desc = _descriptions(data_dir)
    esc = html.escape

    def md_inline(s: str) -> str:
        s = esc(s.replace("**", ""))
        return s.replace("⚠", "<br>⚠")

    cards = []
    for r in rows:
        sid = r.get("id", "")
        d = desc.get(sid) or next((v for k, v in desc.items() if sid and (sid.endswith(k) or k.endswith(sid))), "")
        fit = re.match(r"\s*(\d)/5", r["why"])
        applied = "already applied" in r["company"].lower()
        new = "(new)" in r["why"]
        badges = "".join([
            f'<span class="b fit{fit.group(1)}">{fit.group(1)}/5 fit</span>' if fit else "",
            '<span class="b new">new company</span>' if new else "",
            '<span class="b applied">already applied</span>' if applied else ""])
        why = re.sub(r"^\s*\d/5:\s*", "", r["why"]).replace("(new)", "").strip()
        body = f'<p class="desc">{esc(_summary(d))}</p>' if d else ""
        st = statuses.get(sid, "reported")
        buttons = "".join(
            f'<button class="st {k}{" on" if st == k else ""}" data-s="{k}">{label}</button>'
            for k, label in (("applied", "✓ Applied"), ("interested", "★ Interested"), ("not_interested", "✕ Not for me")))
        cards.append(f"""
<article class="card s-{st}" data-id="{esc(sid)}" data-company="{esc(r['company'].replace('**', '').replace('(already applied)', '').strip())}"
 data-title="{esc(r['title'])}" data-url="{esc(r['url'])}">
  <div class="top"><span class="rank">{r['rank']}</span><div class="head">
    <h2>{esc(r['title'])}</h2>
    <div class="meta">{md_inline(r['company'].replace('(already applied)', ''))} · {esc(r['location'])}</div>
  </div><a class="apply" href="{esc(r['url'])}" target="_blank" rel="noopener">Apply ↗</a></div>
  <div class="badges">{badges}</div>
  <dl><dt>Deadline</dt><dd>{esc(r['deadline'])}</dd><dt>Sponsorship</dt><dd>{esc(r['sponsorship'])}</dd></dl>
  <p class="why"><b>Why it fits:</b> {md_inline(why)}</p>
  {body}
  {f'<div class="actions">{buttons}</div>' if interactive else ''}
</article>""")
    older = "".join(f'<li><a href="{esc(o.stem)}.html">{esc(o.stem)}</a></li>' for o in others if o != md_path)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Job shortlist {esc(md_path.stem)}</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--mute:#5d6676;--line:#e3e6eb;--accent:#2457d6;--good:#1f7a43;--mid:#8a6a00;--low:#9a3b3b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151b;--card:#1b2029;--ink:#e8ebf0;--mute:#9aa3b2;--line:#2c3340;--accent:#7aa2ff;--good:#5fd08f;--mid:#e3c15a;--low:#f08a8a}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:860px;margin:0 auto;padding:24px 16px 60px}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:var(--mute);margin:0 0 20px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 14px}}
.top{{display:flex;gap:12px;align-items:flex-start}} .head{{flex:1;min-width:0}}
.rank{{font-weight:700;color:var(--mute);min-width:22px;padding-top:2px}}
h2{{font-size:17px;margin:0}} .meta{{color:var(--mute);margin-top:2px}}
.apply{{background:var(--accent);color:#fff;text-decoration:none;padding:7px 14px;border-radius:8px;font-weight:600;white-space:nowrap}}
.badges{{margin:10px 0 4px 34px}} .b{{display:inline-block;font-size:12px;font-weight:600;padding:2px 8px;border-radius:99px;margin-right:6px;border:1px solid currentColor}}
.fit5,.fit4{{color:var(--good)}} .fit3{{color:var(--mid)}} .fit2,.fit1{{color:var(--low)}} .new{{color:var(--accent)}} .applied{{color:var(--mute)}}
dl{{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px;margin:8px 0 0 34px}} dt{{color:var(--mute)}} dd{{margin:0}}
.why,.desc{{margin:8px 0 0 34px}} .desc{{color:var(--mute);font-size:14px}}
ul{{color:var(--mute)}} a{{color:var(--accent)}}
.actions{{margin:12px 0 0 34px;display:flex;gap:8px;flex-wrap:wrap}}
.st{{font:inherit;font-size:13px;padding:5px 12px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--ink);cursor:pointer}}
.st.applied.on{{background:var(--good);border-color:var(--good);color:#fff}} .st.interested.on{{background:var(--mid);border-color:var(--mid);color:#fff}}
.st.not_interested.on{{background:var(--low);border-color:var(--low);color:#fff}}
.card.s-not_interested{{opacity:.5}} .card.s-applied{{border-color:var(--good)}}
nav{{margin:0 0 18px}} nav a{{margin-right:14px}} .hint{{background:var(--card);border:1px dashed var(--line);border-radius:8px;padding:8px 12px;color:var(--mute)}}
label.hide{{color:var(--mute);font-size:14px;margin-left:8px}}
@media (max-width:560px){{.top{{flex-wrap:wrap}} .apply{{margin-left:34px}} .badges,dl,.why,.desc{{margin-left:0}}}}
</style></head><body><main>
<h1>Your job shortlist</h1>
<p class="sub">{esc(md_path.stem)} · {len(rows)} roles · ranked best first. Click <b>Apply</b> to open the posting.</p>
{NAV if interactive else HINT}
{''.join(cards) or '<p>No roles in this shortlist.</p>'}
{f'<h3>Earlier shortlists</h3><ul>{older}</ul>' if older else ''}
</main>{SCRIPT if interactive else ''}</body></html>"""
    if interactive:
        page = page.replace('href="' , 'href="').replace('.html">', '">').replace('<li><a href="', '<li><a href="/s/')
    if out is None:
        return page
    out.write_text(page)
    return len(rows)


NAV = """<nav><a href="/">Latest shortlist</a><a href="/applied">My applications</a>
<label class="hide"><input type="checkbox" id="hide"> hide "not for me"</label></nav>"""
HINT = """<p class="hint">To mark jobs as Applied / Interested / Not for me, open this page with
<code>python3 -m jobagent view</code> instead of double-clicking the file.</p>"""
SCRIPT = """<script>
document.querySelectorAll('.card').forEach(card => card.querySelectorAll('.st').forEach(btn => {
  btn.addEventListener('click', async () => {
    const s = btn.classList.contains('on') ? 'reported' : btn.dataset.s;
    const r = await fetch('/api/status', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: card.dataset.id, status: s, company: card.dataset.company,
                            title: card.dataset.title, url: card.dataset.url})});
    if (!r.ok) { alert('Could not save (is the jobagent view server still running?)'); return; }
    card.querySelectorAll('.st').forEach(b => b.classList.toggle('on', b.dataset.s === s));
    card.className = 'card s-' + s; hide();
  });
}));
const box = document.getElementById('hide');
function hide() { if (!box) return; document.querySelectorAll('.card.s-not_interested')
  .forEach(c => c.style.display = box.checked ? 'none' : ''); }
if (box) { box.checked = localStorage.getItem('hideNI') === '1'; box.onchange = () => {
  try { localStorage.setItem('hideNI', box.checked ? '1' : '0'); } catch (e) {} hide(); }; hide(); }
</script>"""


def applications_html(jobs: dict) -> str:
    """'My applications' page: everything you marked Applied or Interested, newest first."""
    esc = html.escape
    groups = {"applied": [], "interested": []}
    for jid, j in jobs.items():
        if j.get("status") in groups:
            groups[j["status"]].append(j)
    parts = []
    for key, label in (("applied", "Applied"), ("interested", "Interested (not applied yet)")):
        items = sorted(groups[key], key=lambda j: j.get("status_date", ""), reverse=True)
        li = "".join(f'<li><b>{esc(j.get("company", ""))}</b>: {esc(j.get("title", ""))} '
                     f'<span class="mute">· {esc(j.get("status_date", ""))}</span> · '
                     f'<a href="{esc(j.get("url", ""))}" target="_blank" rel="noopener">posting ↗</a></li>' for j in items)
        parts.append(f"<h2>{label} ({len(items)})</h2><ul>{li or '<li class=mute>None yet.</li>'}</ul>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>My applications</title>
<style>:root{{--bg:#f6f7f9;--ink:#1d2330;--mute:#5d6676;--accent:#2457d6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151b;--ink:#e8ebf0;--mute:#9aa3b2;--accent:#7aa2ff}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:860px;margin:0 auto;padding:24px 16px}} a{{color:var(--accent)}} .mute{{color:var(--mute)}} nav a{{margin-right:14px}}
h2{{font-size:18px;margin-top:24px}}</style></head><body><main>
<nav><a href="/">Latest shortlist</a><a href="/applied">My applications</a></nav>
<h1>My applications</h1>{''.join(parts)}</main></body></html>"""
