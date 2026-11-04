"""Fetchers for public ATS job feeds. Standard library only.

Each fetcher returns a list of Job. Network errors raise SourceError; the caller
records them in data/source_status.json and carries on with the other boards.
"""
from __future__ import annotations

import html
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from dataclasses import dataclass, field, asdict

UA = "job-agent/1.0 (personal job search script)"
TIMEOUT = 25


class SourceError(Exception):
    pass


@dataclass
class Job:
    source: str            # greenhouse / lever / ashby / workday / smartrecruiters / reed / manual
    source_id: str
    company: str
    title: str
    location: str
    url: str
    description: str = ""  # plain text
    posted: str = ""
    deadline: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _request(url: str, data: dict | None = None, headers: dict | None = None, retries: int = 2, raw: bool = False):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    hdrs.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        hdrs["Content-Type"] = "application/json"
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=hdrs)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                text = r.read().decode("utf-8", "replace")
                return text if raw else json.loads(text)
        except urllib.error.HTTPError as e:
            if e.code in (404, 401, 403, 400):
                raise SourceError(f"HTTP {e.code} for {url}") from e
            last = e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, http.client.HTTPException, OSError) as e:
            last = e
        time.sleep(2 * (attempt + 1))
    raise SourceError(f"{type(last).__name__}: {last} for {url}")


_TAG = re.compile(r"<[^>]+>")


def html_to_text(s: str) -> str:
    s = html.unescape(s or "")       # greenhouse content is HTML-escaped HTML
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>", "\n", s)
    s = _TAG.sub(" ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]+", " ", s).strip()


# --------------------------------------------------------------------------- greenhouse
def greenhouse(company: str, token: str, **_) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    data = _request(url)
    out = []
    for j in data.get("jobs", []):
        out.append(Job(
            source="greenhouse", source_id=f"gh:{token}:{j.get('id')}", company=company,
            title=j.get("title", "").strip(),
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
            description=html_to_text(j.get("content", "")),
            posted=j.get("updated_at", "") or "",
        ))
    return out


# --------------------------------------------------------------------------- lever
def lever(company: str, token: str, region: str = "", **_) -> list[Job]:
    host = "api.eu.lever.co" if region == "eu" else "api.lever.co"
    data = _request(f"https://{host}/v0/postings/{token}?mode=json")
    out = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories") or {}
        parts = [j.get("descriptionPlain", ""), j.get("additionalPlain", "")]
        for lst in j.get("lists", []) or []:
            parts.append(lst.get("text", "") + "\n" + html_to_text(lst.get("content", "")))
        locs = cats.get("allLocations") or [cats.get("location", "")]
        out.append(Job(
            source="lever", source_id=f"lv:{token}:{j.get('id')}", company=company,
            title=j.get("text", "").strip(), location=" / ".join(filter(None, locs)),
            url=j.get("hostedUrl", ""), description="\n".join(parts),
            posted=str(j.get("createdAt", "")),
            extra={"commitment": cats.get("commitment", "")},
        ))
    return out


# --------------------------------------------------------------------------- ashby
def ashby(company: str, token: str, **_) -> list[Job]:
    data = _request(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location", "")] + [l.get("location", "") for l in j.get("secondaryLocations", []) or []]
        out.append(Job(
            source="ashby", source_id=f"ab:{token}:{j.get('id')}", company=company,
            title=j.get("title", "").strip(), location=" / ".join(filter(None, locs)),
            url=j.get("jobUrl", ""),
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")),
            posted=j.get("publishedAt", "") or "",
            extra={"employmentType": j.get("employmentType", ""), "remote": j.get("isRemote")},
        ))
    return out


# --------------------------------------------------------------------------- workday
def workday(company: str, token: str, host: str, site: str, search: str = "", max_pages: int = 10,
            title_prefilter=None, **_) -> list[Job]:
    """Workday's undocumented careers JSON API (POST, 20 rows per page)."""
    base = f"https://{host}/wday/cxs/{token}/{site}"
    out, offset = [], 0
    for _page in range(max_pages):
        data = _request(f"{base}/jobs", data={"appliedFacets": {}, "limit": 20, "offset": offset,
                                              "searchText": search})
        posts = data.get("jobPostings", [])
        for p in posts:
            title = p.get("title", "")
            path = p.get("externalPath", "")
            job = Job(source="workday", source_id=f"wd:{token}:{path}", company=company, title=title,
                      location=p.get("locationsText", ""),
                      url=f"https://{host}/en-US/{site}{path}", posted=p.get("postedOn", ""))
            # Fetch the full description only for titles that survive the cheap title filter.
            if title_prefilter is None or title_prefilter(title):
                try:
                    d = _request(f"{base}{path}")
                    info = d.get("jobPostingInfo", {})
                    job.description = html_to_text(info.get("jobDescription", ""))
                    job.location = info.get("location", job.location)
                except SourceError:
                    pass
            out.append(job)
        offset += 20
        if len(posts) < 20 or offset >= data.get("total", 0):
            break
    return out


# --------------------------------------------------------------------------- smartrecruiters
def smartrecruiters(company: str, token: str, **_) -> list[Job]:
    posts, offset = [], 0
    while offset < 1000:                       # the API returns 100 at a time
        data = _request(f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100&offset={offset}")
        page = data.get("content", [])
        posts += page
        offset += 100
        if len(page) < 100 or offset >= data.get("totalFound", 0):
            break
    out = []
    for j in posts:
        loc = j.get("location") or {}
        out.append(Job(
            source="smartrecruiters", source_id=f"sr:{token}:{j.get('id')}", company=company,
            title=j.get("name", ""), location=", ".join(filter(None, [loc.get("city"), loc.get("country")])),
            url=f"https://jobs.smartrecruiters.com/{token}/{j.get('id')}", posted=j.get("releasedDate", ""),
        ))
    return out


# --------------------------------------------------------------------------- reed (optional, needs key)
def reed(queries: list[str], location: str = "London") -> list[Job]:
    """Reed.co.uk Jobseeker API. Free key: https://www.reed.co.uk/developers/jobseeker"""
    key = os.environ.get("REED_API_KEY")
    if not key:
        return []
    auth = "Basic " + b64encode(f"{key}:".encode()).decode()
    out, seen = [], set()
    for q in queries:
        qs = urllib.parse.urlencode({"keywords": q, "locationName": location, "graduate": "true",
                                     "resultsToTake": 100})
        data = _request(f"https://www.reed.co.uk/api/1.0/search?{qs}", headers={"Authorization": auth})
        for j in data.get("results", []):
            if j["jobId"] in seen:
                continue
            seen.add(j["jobId"])
            out.append(Job(
                source="reed", source_id=f"reed:{j['jobId']}", company=j.get("employerName", ""),
                title=j.get("jobTitle", ""), location=j.get("locationName", ""), url=j.get("jobUrl", ""),
                description=j.get("jobDescription", ""), posted=j.get("date", ""),
                deadline=j.get("expirationDate", ""),
            ))
    return out


# --------------------------------------------------------------------------- freehire (aggregator, no key)
def freehire(cfg: dict) -> list[Job]:
    """freehire.me open API: ~7M live postings from ~185k companies' own ATS boards.
    Finds startups and companies that aren't in companies.toml. Free tier: 120 req/min, 2,000/day.
    Docs: https://freehire.me/docs/api"""
    fh = cfg.get("freehire", {})
    if not fh.get("enabled", True):
        return []
    out, seen = [], set()
    for q in fh["queries"]:
        params = [("q", q["q"]), ("description_format", "text"), ("limit", "50"),
                  ("open_within_days", str(fh.get("open_within_days", 30)))]
        params += [("countries", c) for c in fh["countries"]]
        params += [("seniority", s) for s in q.get("seniority", [])]
        for page in range(fh.get("pages", 2)):
            qs = urllib.parse.urlencode(params + [("offset", str(page * 50))])
            try:
                rows = _request(f"https://freehire.me/api/v1/agent/jobs/search?{qs}").get("data", [])
            except SourceError:
                break        # keep what we have; one failed query mustn't lose the rest
            for j in rows:
                slug = j.get("public_slug")
                if not slug or slug in seen or not (j.get("company") or "").strip():
                    continue
                seen.add(slug)
                url = re.sub(r"[?&]utm_source=freehire\.me$", "", j.get("url", ""))
                out.append(Job(source="freehire", source_id=f"fh:{slug}", company=j["company"].strip(),
                               title=(j.get("title") or "").strip(), location=j.get("location") or "",
                               url=url, description=j.get("description") or "",
                               posted=j.get("posted_at") or "", extra={"via": j.get("source", "")}))
            if len(rows) < 50:
                break
    # every role at named companies (watch-list firms with no public board); our filters decide fit
    slugs = fh.get("company_slugs", [])
    countries = fh.get("countries") or []
    for i in range(0, len(slugs), 6):
        # no date limit: freehire only lists postings that are still open, and graduate roles stay open for months
        base = [("description_format", "text"), ("limit", "50")]
        base += [("company_slug", c) for c in slugs[i:i + 6]] + [("countries", c) for c in countries]
        for page in range(fh.get("company_pages", 6)):
            qs = urllib.parse.urlencode(base + [("offset", str(page * 50))])
            try:
                rows = _request(f"https://freehire.me/api/v1/agent/jobs/search?{qs}").get("data", [])
            except SourceError:
                break
            for j in rows:
                slug = j.get("public_slug")
                if not slug or slug in seen or not (j.get("company") or "").strip():
                    continue
                seen.add(slug)
                url = re.sub(r"[?&]utm_source=freehire\.me$", "", j.get("url", ""))
                out.append(Job(source="freehire", source_id=f"fh:{slug}", company=j["company"].strip(),
                               title=(j.get("title") or "").strip(), location=j.get("location") or "",
                               url=url, description=j.get("description") or "",
                               posted=j.get("posted_at") or "", extra={"via": j.get("source", "")}))
            if len(rows) < 50:
                break
    return out


# --------------------------------------------------------------------------- Jane Street (own JSON feed)
JS_CITIES = {"LDN": "London, United Kingdom", "NYC": "New York, NY, United States", "HKG": "Hong Kong",
             "SGP": "Singapore", "ATX": "Austin, TX, United States", "CHI": "Chicago, IL, United States",
             "AMS": "Amsterdam, Netherlands"}


def janestreet(company: str = "Jane Street", token: str = "janestreet", **_) -> list[Job]:
    """janestreet.com/jobs/main.json: every open role with its availability (New Grad / Internship / Experienced)."""
    data = _request("https://www.janestreet.com/jobs/main.json")
    out = []
    for j in data if isinstance(data, list) else []:
        avail = (j.get("availability") or "").strip()
        title = (j.get("position") or "").strip()
        if "intern" in avail.lower() and "intern" not in title.lower():
            title += " (Summer Internship)" if "summer" in avail.lower() else " (Internship)"
        elif "new grad" in avail.lower():
            title += " (New Grad)"
        desc = f"{avail}. Team: {j.get('team') or ''}. " + html_to_text(j.get("overview") or "")
        if "experienced" in avail.lower():
            desc = "Experienced hire (not a graduate role). " + desc
        out.append(Job(source="janestreet", source_id=f"js:{j.get('id')}", company=company, title=title,
                       location=JS_CITIES.get(j.get("city", ""), j.get("city", "")),
                       url=f"https://www.janestreet.com/join-jane-street/position/{j.get('id')}/",
                       description=desc, extra={"availability": avail}))
    return out


# --------------------------------------------------------------------------- EU ATSes
def _xml(url: str):
    import xml.etree.ElementTree as ET
    try:
        return ET.fromstring(_request(url, headers={"Accept": "application/xml, text/xml, */*"}, raw=True))
    except ET.ParseError as e:
        raise SourceError(f"bad XML from {url}: {e}") from e


def personio(company: str, token: str, **_) -> list[Job]:
    """<token>.jobs.personio.com/xml: German/Austrian startups and Mittelstand."""
    root = _xml(f"https://{token}.jobs.personio.com/xml?language=en")
    out = []
    for p in root.iter("position"):
        g = lambda k: (p.findtext(k) or "").strip()  # noqa: E731
        offices = [g("office")] + [(o.text or "").strip() for o in p.findall("additionalOffices/office")]
        desc = "\n".join(f"{(d.findtext('name') or '').strip()}\n{html_to_text(d.findtext('value') or '')}"
                         for d in p.iter("jobDescription"))
        desc = f"Seniority: {g('seniority')}. Type: {g('employmentType')}. " + desc
        out.append(Job(source="personio", source_id=f"pe:{token}:{g('id')}", company=company, title=g("name"),
                       location="; ".join(o for o in offices if o), description=desc,
                       url=f"https://{token}.jobs.personio.com/job/{g('id')}", posted=g("createdAt")))
    return out


def recruitee(company: str, token: str, **_) -> list[Job]:
    """<token>.recruitee.com/api/offers/: Dutch/Benelux and Central-European companies."""
    data = _request(f"https://{token}.recruitee.com/api/offers/")
    out = []
    for o in data.get("offers", []):
        desc = html_to_text((o.get("description") or "") + "\n" + (o.get("requirements") or ""))
        lvl = o.get("experience_code") or ""
        out.append(Job(source="recruitee", source_id=f"rc:{token}:{o.get('id')}",
                       company=o.get("company_name") or company, title=o.get("title", ""),
                       location=o.get("location") or ", ".join(filter(None, [o.get("city"), o.get("country")])),
                       url=o.get("careers_url", ""), description=(f"Level: {lvl}. " if lvl else "") + desc,
                       posted=o.get("published_at") or "", deadline=(o.get("close_at") or "")[:10]))
    return out


def teamtailor(company: str, token: str, **_) -> list[Job]:
    """<token>.teamtailor.com/jobs.rss: Nordic and French companies."""
    root = _xml(f"https://{token}.teamtailor.com/jobs.rss")
    ns = "{https://teamtailor.com/locations}"
    out = []
    for it in root.iter("item"):
        locs = []
        for loc in it.iter(f"{ns}location"):
            c = ", ".join(filter(None, [(loc.findtext(f"{ns}city") or "").strip(),
                                        (loc.findtext(f"{ns}country") or "").strip()]))
            if c:
                locs.append(c)
        remote = (it.findtext("remoteStatus") or "").strip()
        if remote in ("fully", "remote"):
            locs.append("Remote")
        link = (it.findtext("link") or "").strip()
        out.append(Job(source="teamtailor", source_id=f"tt:{token}:{(it.findtext('guid') or link).strip()}",
                       company=company, title=(it.findtext("title") or "").strip(), location="; ".join(locs),
                       url=link, description=html_to_text(it.findtext("description") or ""),
                       posted=(it.findtext("pubDate") or "").strip()))
    return out


def workable(company: str, token: str, **_) -> list[Job]:
    """apply.workable.com/<token>: many EU scale-ups (Greece, Spain, UK, Netherlands...)."""
    data = _request(f"https://apply.workable.com/api/v1/widget/accounts/{token}?details=true")
    out = []
    for j in data.get("jobs", []):
        loc = ", ".join(filter(None, [j.get("city"), j.get("country")]))
        if j.get("telecommuting"):
            loc = (loc + "; " if loc else "") + "Remote"
        out.append(Job(source="workable", source_id=f"wk:{token}:{j.get('shortcode')}", company=company,
                       title=j.get("title", ""), location=loc,
                       url=j.get("url") or f"https://apply.workable.com/{token}/j/{j.get('shortcode')}/",
                       description=html_to_text(j.get("description") or ""), posted=j.get("published_on") or ""))
    return out


FETCHERS = {"janestreet": janestreet, "greenhouse": greenhouse, "lever": lever, "ashby": ashby, "workday": workday,
            "smartrecruiters": smartrecruiters, "personio": personio, "recruitee": recruitee,
            "teamtailor": teamtailor, "workable": workable}

# job URL -> (ats, token): used to find new company boards in roles that passed your filters
BOARD_URL = [("greenhouse", r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)"), ("lever", r"jobs\.lever\.co/([\w-]+)"),
             ("ashby", r"jobs\.ashbyhq\.com/([\w%.-]+)"), ("personio", r"([\w-]+)\.jobs\.personio\.(?:de|com)"),
             ("recruitee", r"([\w-]+)\.recruitee\.com"), ("teamtailor", r"([\w-]+)\.teamtailor\.com"),
             ("workable", r"apply\.workable\.com/(?!j/|api/)([\w-]+)"),
             ("smartrecruiters", r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)")]


def board_from_url(url: str) -> tuple[str, str] | None:
    for ats, rx in BOARD_URL:
        m = re.search(rx, url or "")
        if m and m.group(1).lower() not in ("embed", "jobs", "o", "j", "p"):
            return ats, m.group(1)
    return None
