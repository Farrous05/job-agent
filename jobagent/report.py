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


def write_html(md_path: Path, data_dir: Path, out: Path, others: list[Path]) -> int:
    rows = parse_shortlist(md_path)
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
        cards.append(f"""
<article class="card">
  <div class="top"><span class="rank">{r['rank']}</span><div class="head">
    <h2>{esc(r['title'])}</h2>
    <div class="meta">{md_inline(r['company'].replace('(already applied)', ''))} · {esc(r['location'])}</div>
  </div><a class="apply" href="{esc(r['url'])}" target="_blank" rel="noopener">Apply ↗</a></div>
  <div class="badges">{badges}</div>
  <dl><dt>Deadline</dt><dd>{esc(r['deadline'])}</dd><dt>Sponsorship</dt><dd>{esc(r['sponsorship'])}</dd></dl>
  <p class="why"><b>Why it fits:</b> {md_inline(why)}</p>
  {body}
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
@media (max-width:560px){{.top{{flex-wrap:wrap}} .apply{{margin-left:34px}} .badges,dl,.why,.desc{{margin-left:0}}}}
</style></head><body><main>
<h1>Your job shortlist</h1>
<p class="sub">{esc(md_path.stem)} · {len(rows)} roles · ranked best first. Click <b>Apply</b> to open the posting.</p>
{''.join(cards) or '<p>No roles in this shortlist.</p>'}
{f'<h3>Earlier shortlists</h3><ul>{older}</ul>' if older else ''}
</main></body></html>"""
    out.write_text(page)
    return len(rows)
