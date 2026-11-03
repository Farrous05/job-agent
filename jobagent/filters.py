"""Hard filters, sponsorship detection and heuristic scoring. Everything person-specific comes
from config/profile.toml (see config/profile.example.toml) and config/regions.toml."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .sources import Job

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]
BASE_ENTRY_WORDS = (r"graduate|new grad|grads?\b|entry|junior|campus|early career|university|class of|"
                    r"associate programme|graduate programme")
INTERN_WORDS = (r"\bintern(ship)?\b|placement|industrial year|co-?op\b|working student|werkstudent|praktikant|"
                r"praktikum|stagiaire|\bstage\b|alternan|tirocinio|prácticas|becario")


@dataclass
class Verdict:
    keep: bool
    reasons: list[str] = field(default_factory=list)   # why excluded
    region: str = ""          # a region name from regions.toml, or "other"
    sponsorship: str = ""     # human-readable status
    families: list[str] = field(default_factory=list)
    internship: bool = False
    score: float = 0.0
    why: str = ""
    flags: list[str] = field(default_factory=list)


def _has(pat: str, text: str) -> bool:
    return re.search(pat, text, re.I) is not None


def _word_hits(words, text: str) -> int:
    """Length of the longest whole-word match, 0 if none."""
    best = 0
    for w in words:
        if len(w) > best and re.search(rf"(?<![a-zà-ÿ]){re.escape(w)}(?![a-zà-ÿ])", text):
            best = len(w)
    return best


def _ym(s: str) -> tuple[int, int] | None:
    m = re.match(r"(\d{4})-(\d{1,2})", s or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


# --------------------------------------------------------------------------- location
def region_of(location: str, cfg: dict) -> str:
    """Returns an accepted region name, or 'other'. Each listed location ('London; New York') is matched
    separately; the region with the longest whole-word match wins ('Porto Alegre' beats 'Porto',
    'Cambridge, MA' beats 'Cambridge'). A posting passes if any of its locations is in an accepted region."""
    regions = cfg["_regions"]
    accept = cfg["regions"]["accept"]
    loc_all = location.lower()
    parts = [p.strip() for p in re.split(r"[;/|]| or ", loc_all) if p.strip()] or [""]
    found, non_accepted_seen = [], False
    for part in parts:
        scores = {name: _word_hits(r["words"], part) for name, r in regions.items()}
        best = max(scores, key=scores.get) if scores else None
        if best and scores[best] > 0:
            if best in accept:
                found.append(best)
            else:
                non_accepted_seen = True
        elif "remote" in part:
            found.append("remote")
    real = [r for r in found if r != "remote"]
    if real:
        return real[0]
    if "remote" in found and cfg["regions"].get("accept_remote", True) and not non_accepted_seen:
        return "remote"
    return "other"


# --------------------------------------------------------------------------- experience
def years_required(text: str) -> int | None:
    """Smallest 'N+ years' / 'N-M years' / 'at least N years' experience demand found, else None."""
    mins = []
    for m in re.finditer(r"(\d{1,2})\s*(?:\+|-|–|to)?\s*(\d{1,2})?\s*\+?\s*years?(?:'|’)?\s*(?:of\s+)?"
                         r"(?:[\w/-]+\s+){0,4}?(?:experience|exp\b)", text, re.I):
        mins.append(int(m.group(1)))
    for m in re.finditer(r"(?:at least|minimum of|minimum)\s+(\d{1,2})\s+years", text, re.I):
        mins.append(int(m.group(1)))
    return min(mins) if mins else None


# --------------------------------------------------------------------------- sponsorship
def sponsorship_status(description: str, region: str, cfg: dict) -> tuple[str, str]:
    """Reads the job DESCRIPTION only. Returns (status, verdict); verdict in
    {'free', 'yes', 'no', 'mixed', 'visa_route', 'unknown'}. Only an explicit 'no sponsorship'
    statement gives 'no' (the only verdict that removes a job)."""
    rights = cfg.get("work_rights", {})
    if region == "remote":
        return "Remote: check where you can work from", "unknown"
    if rights.get(region, "needs_sponsorship") == "free":
        label = cfg["_regions"].get(region, {}).get("label", region)
        return f"No sponsorship needed (you can work in {label})", "free"
    t = description.lower()
    no = re.search(r"(unable|not able|cannot|can't|can not|do not|don't|will not|won't|not)\s+"
                   r"(to\s+)?(provide|offer|sponsor|support)\w*\s+(any\s+)?(work\s+)?(visa|sponsorship|work permit|immigration)", t) \
        or re.search(r"without (requiring|needing|the need for|need of) (a |any )?(current or future )?(visa )?sponsorship", t) \
        or re.search(r"(visa )?sponsorship (is )?not (available|provided|offered)", t) \
        or re.search(r"right to work in [a-z ]{2,20} without (the need for )?(visa )?sponsorship", t) \
        or re.search(r"(not|never) (now or in the future )?require (visa |employment visa )?sponsorship", t) \
        or re.search(r"no (visa )?sponsorship(?! (is )?(required|needed))", t)
    yes = re.search(r"(visa )?sponsorship (is )?(available|provided|offered|considered)", t) \
        or re.search(r"\b(we|will|can|able to) (offer |provide )?(visa )?sponsor", t) \
        or re.search(r"skilled worker (visa )?sponsor", t)
    route = re.search(r"graduate (route )?visa|post[- ]study work|opt\b|stem opt|h-?1b", t)
    if yes and no:
        return "Mixed statements: check", "mixed"
    if yes:
        return "Sponsorship offered (stated)", "yes"
    if no:
        return "No sponsorship (stated)", "no"
    if route:
        return "Mentions a visa route: check", "visa_route"
    if re.search(r"right to work|authori[sz]ed to work|work authori[sz]ation", t):
        return "Not stated (asks for right to work: check)", "unknown"
    return "Not stated", "unknown"


# --------------------------------------------------------------------------- main
def _families(cfg: dict):
    return [(f["name"], f["pattern"], f.get("weight", 5)) for f in cfg["roles"]["families"]]


def evaluate(job: Job, cfg: dict) -> Verdict:
    f = cfg["filters"]
    p = cfg["profile"]
    title = job.title
    tl = title.lower()
    text = f"{title}\n{job.description}"
    v = Verdict(keep=True)
    grad = _ym(p.get("graduation", ""))
    graduating = grad is not None and grad >= (date.today().year, date.today().month)
    entry_words = BASE_ENTRY_WORDS + (rf"|{grad[0]}" if graduating else "")

    # --- role family
    fams = _families(cfg)
    v.families = [n for n, pat, _ in fams if _has(pat, title)]
    if not v.families:
        v.keep = False
        v.reasons.append("not a target role family")

    # --- seniority / PhD / experience
    for w in f["exclude_title_words"]:
        if w.strip() and re.search(rf"(?<![a-z]){re.escape(w.strip())}(?![a-z])", tl):
            v.keep = False
            v.reasons.append(f"title contains '{w.strip()}'")
            break
    if f.get("phd", "exclude_phd_only") == "exclude_phd_only":
        masters = r"master|msc|m\.sc|\bms\b|mres|mphil|meng"

        def phd_only(t: str) -> bool:
            for m in re.finditer(r"ph\.?d|doctora|postdoc|post-doc", t, re.I):
                if not re.search(masters, t[max(0, m.start() - 40): m.end() + 40], re.I):
                    return True
            return False
        if re.search(r"ph\.?d|postdoc|post-doc", title, re.I) and phd_only(title):
            v.keep = False
            v.reasons.append("PhD-only role (title)")
        elif re.search(r"(phd|ph\.d|doctoral degree|doctorate)\s+(is\s+)?(required|essential|mandatory)|"
                       r"must (have|hold) a (phd|doctorate)|(currently )?(pursuing|enrolled in) a (phd|doctora)",
                       job.description, re.I) and phd_only(job.description) \
                and not re.search(r"phd (is )?(preferred|a plus|desirable|not required)", job.description, re.I):
            v.keep = False
            v.reasons.append("PhD required")
    yrs = years_required(job.description)
    if yrs is not None and yrs > f["max_years_experience"]:
        v.keep = False
        v.reasons.append(f"{yrs}+ years' experience required")

    # --- internships
    v.internship = _has(INTERN_WORDS, title)
    if _has(r"\b(sc|dv|nv)[- ]?clear(ed|ance)\b|security clearance", text):
        v.flags.append("needs security clearance")
    if v.internship:
        if not f.get("allow_internships", True):
            v.keep = False
            v.reasons.append("internship (not wanted)")
        elif f.get("exclude_summer_internships") and _has(r"summer|jun(e)?\s*[-–]|10[- ]week|12[- ]week", text) \
                and not _has(r"off[- ]cycle|part[- ]time", text):
            v.keep = False
            v.reasons.append("summer internship (excluded in profile)")
        else:
            v.flags.append("internship: check timing" + (f" ({f['internship_note']})" if f.get("internship_note") else ""))

    # --- roles for later graduating classes
    if graduating:
        for y in range(grad[0] + 1, grad[0] + 3):
            if re.search(rf"(graduat\w*|class of|grads?)\D{{0,25}}{y}|{y}\s*(grads?|graduates)", text, re.I) \
                    and not re.search(str(grad[0]), title):
                v.keep = False
                v.reasons.append(f"aimed at {y} graduates")
                break

    # --- location / work rights
    v.region = region_of(job.location, cfg)
    if v.region == "other":
        v.keep = False
        v.reasons.append("location outside accepted regions")
    status, sv = sponsorship_status(job.description, v.region, cfg)
    v.sponsorship = status
    if sv == "no":
        v.keep = False
        v.reasons.append("explicitly no sponsorship (you need it there)")

    if not v.keep:
        return v

    # --- scoring
    score = max(w for n, _, w in fams if n in v.families)
    if p.get("level", "graduate") in ("graduate", "junior"):
        if _has(entry_words, title):
            score += 6
        elif _has(entry_words + r"|recent graduate|no experience required|0-2 years|fellows|residen",
                  job.description[:3000] + title):
            score += 3
        else:
            score -= 6
            v.flags.append("not labelled entry-level: check experience bar")
    # start date fit (only while still studying)
    if graduating:
        y = grad[0]
        if _has(rf"(september|autumn|fall|summer|august|{y})\s*(start|intake)?.{{0,20}}{y}|{y} start|start(ing)? in {y}", text):
            score += 4
        if _has(r"immediate start|asap|start date:? (now|immediately)", text):
            score -= 3
        early = "|".join(MONTHS[: max(grad[1] - 1, 0)])
        if early and _has(rf"start\w*[^.]{{0,40}}\b({early})\s+{y}|\b({early})\s+{y}\s+(start|cohort|intake)", text):
            score -= 8
            v.flags.append(f"starts before you graduate ({MONTHS[grad[1] - 1].title()} {y})")
    # CV fit
    desc = job.description.lower()
    hits = [k for k in cfg["roles"].get("cv_keywords", []) if k in desc or k in tl]
    score += min(len(hits), 12) * 0.75
    # sponsorship: only an explicit statement counts; "not stated" changes nothing
    score += {"yes": 3}.get(sv, 0)
    # location preference
    pref = [c.lower() for c in cfg["regions"].get("preferred_cities", [])]
    if pref and not any(c in job.location.lower() for c in pref):
        score -= 2
    # company quality
    comp = job.company.lower()
    if any(t.lower() in comp for t in p.get("dream_companies", [])):
        score += 4
    elif any(t.lower() in comp for t in cfg["ranking"].get("tier1", [])):
        score += 3
    elif any(t.lower() in comp for t in cfg["ranking"].get("tier2", [])):
        score += 1.5
    if v.internship:
        score -= 4

    v.score = round(score, 2)
    v.why = f"{'/'.join(v.families[:2])} role; matches CV on {', '.join(hits[:5]) or 'title only'}"
    return v


def is_applied(company: str, cfg: dict) -> bool:
    c = company.lower()
    return any(a.lower() in c for a in cfg["profile"].get("already_applied", []))


def title_prefilter(cfg: dict):
    """Cheap filter used before fetching Workday descriptions."""
    fams = _families(cfg)

    def ok(title: str) -> bool:
        return any(_has(pat, title) for _, pat, _ in fams) and not any(
            re.search(rf"(?<![a-z]){re.escape(w.strip())}(?![a-z])", title.lower())
            for w in cfg["filters"]["exclude_title_words"] if w.strip())
    return ok
