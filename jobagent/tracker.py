"""Application tracking: reminders (deadlines, follow-ups) and stats (what gets replies)."""
from __future__ import annotations

from datetime import date

from .store import SeenStore

FOLLOW_UP_DAYS = 14        # nudge if an application has had no update for this long
CLOSING_DAYS = 10          # warn about deadlines this close


def _days_since(iso: str) -> int | None:
    try:
        return (date.today() - date.fromisoformat(iso[:10])).days
    except (TypeError, ValueError):
        return None


def reminders(store: SeenStore) -> list[str]:
    from .report import _deadline_days
    out = []
    for j in store.data["jobs"].values():
        st = j.get("status", "reported")
        days = _deadline_days(j.get("deadline", "") or "")
        name = f"{j.get('company', '')}: {j.get('title', '')}"
        if st in ("reported", "interested") and days is not None and 0 <= days <= CLOSING_DAYS:
            when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
            out.append(f"Closes {when}: {name}" + (" (you marked it Interested)" if st == "interested" else ""))
        if st == "applied":
            since = _days_since(j.get("status_date", ""))
            if since is not None and since >= FOLLOW_UP_DAYS:
                out.append(f"No reply for {since} days: {name}. Follow up or mark it Rejected.")
        if st == "interviewing":
            since = _days_since(j.get("status_date", ""))
            if since is not None and since >= FOLLOW_UP_DAYS:
                out.append(f"Interview stage for {since} days with no update: {name}.")
    order = {"Closes": 0, "No reply": 1, "Interview": 2}
    return sorted(out, key=lambda s: order.get(s.split(" ")[0], 3))


def stats(store: SeenStore) -> dict:
    """Counts by stage, plus reply rate by role family, region and source."""
    stages = {k: 0 for k in ("interested", "applied", "interviewing", "offer", "rejected", "not_interested")}
    by = {"family": {}, "region": {}, "source": {}}
    for j in store.data["jobs"].values():
        st = j.get("status", "reported")
        if st in stages:
            stages[st] += 1
        if st not in SeenStore.APPLIED:
            continue
        replied = st in ("interviewing", "offer", "rejected")
        positive = st in ("interviewing", "offer")
        keys = {"family": (j.get("families") or ["unknown"])[0], "region": j.get("region") or "unknown",
                "source": j.get("source") or "unknown"}
        for dim, key in keys.items():
            row = by[dim].setdefault(key, {"applied": 0, "replied": 0, "interviews": 0})
            row["applied"] += 1
            row["replied"] += replied
            row["interviews"] += positive
    cal = {"applied": [], "interested": [], "not_interested": []}
    for j in store.data["jobs"].values():
        st = j.get("status", "reported")
        key = "applied" if st in SeenStore.APPLIED else st
        if key in cal and isinstance(j.get("fit"), int):
            cal[key].append(j["fit"])
    calibration = {k: {"n": len(v), "avg": round(sum(v) / len(v), 1) if v else None} for k, v in cal.items()}
    applied_total = sum(stages[s] for s in SeenStore.APPLIED)
    replied_total = stages["interviewing"] + stages["offer"] + stages["rejected"]
    return {"stages": stages, "applied_total": applied_total, "replied_total": replied_total,
            "interview_total": stages["interviewing"] + stages["offer"], "by": by, "calibration": calibration}


def stats_text(s: dict) -> str:
    st = s["stages"]
    lines = [f"Applied: {s['applied_total']} · replies: {s['replied_total']} · interviews/offers: "
             f"{s['interview_total']} · offers: {st['offer']} · rejected: {st['rejected']} · "
             f"interested (not applied): {st['interested']}"]
    cal = s.get("calibration", {})
    if any(v["n"] for v in cal.values()):
        lines.append("\nClaude's average fit for jobs you marked: " + ", ".join(
            f"{k.replace('_', ' ')} {v['avg']} ({v['n']})" for k, v in cal.items() if v["n"]))
    for dim, label in (("family", "role type"), ("region", "region"), ("source", "where found")):
        rows = s["by"][dim]
        if not rows:
            continue
        lines.append(f"\nBy {label}:")
        for k, r in sorted(rows.items(), key=lambda x: -x[1]["applied"]):
            rate = f"{round(100 * r['interviews'] / r['applied'])}% interviews" if r["applied"] else ""
            lines.append(f"  {k:<16} applied {r['applied']:>3} · replies {r['replied']:>3} · {rate}")
    return "\n".join(lines)
