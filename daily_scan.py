#!/usr/bin/env python3
"""
Daily job scan — Plan B
  Source A: fetch_jobs.py  (JSON, scored ≥65, last 24h)
  Source B: fetch_readme_jobs.py (README, today only, no score — too fresh for JSON)

Usage:
    python3 daily_scan.py              # JSON output to stdout
    python3 daily_scan.py --pretty     # human-readable table
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta

DOMAIN_MAP = {
    "ai_ml":       "AI/ML",
    "embedded":    "Embedded",
    "sre":         "Systems",
    "backend":     "Backend",
    "swe_generic": "Backend",
}

from profile import SKIP_TITLE_KW, SKIP_COMPANY, REQUIRE_TITLE_KW


def is_relevant(title, company):
    t = title.lower()
    c = company.lower()
    return not any(k in t for k in SKIP_TITLE_KW) and not any(k in c for k in SKIP_COMPANY)


def has_tech_keyword(title):
    t = title.lower()
    return any(k in t for k in REQUIRE_TITLE_KW)


def run(args):
    r = subprocess.run(["python3"] + args, capture_output=True, text=True)
    if r.returncode not in (0, 4):
        print(f"[warn] {args[0]}: {r.stderr.strip()[:200]}", file=sys.stderr)
        return None
    try:
        return json.loads(r.stdout)
    except Exception as e:
        print(f"[warn] JSON parse error ({args[0]}): {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    since = (datetime.now(timezone.utc) - timedelta(hours=26)).strftime("%Y-%m-%dT%H:%M:%S")
    all_jobs = []
    seen_links = set()

    # ── Source A: scored jobs from JSON (≥65) ──────────────────────────────
    print("Fetching scored jobs...", file=sys.stderr)
    result = run([
        "fetch_jobs.py",
        "--domain", "software",
        "--since", since,
        "--min-score", "65",
        "--visa-only",
        "--limit", "100",
    ])
    scored_count = 0
    if result and result.get("ok"):
        for j in result["data"]["jobs"]:
            link = j.get("apply_link", "")
            if not link or link in seen_links: continue
            if not is_relevant(j["title"], j["company"]): continue
            seen_links.add(link)
            scored_count += 1
            all_jobs.append({
                "id":             j["job_id"],
                "title":          j["title"],
                "company":        j["company"],
                "domain":         DOMAIN_MAP.get(j.get("domain_type", ""), "Backend"),
                "location":       j.get("location", ""),
                "posted":         j.get("posted_ago", ""),
                "visa":           "✅ Confirmed" if j.get("visa_confirmed") else "🏛 H-1B Co",
                "visa_confirmed": j.get("visa_confirmed", False),
                "link":           link,
                "score":          j.get("score"),
                "matched_skills": j.get("matched_skills", [])[:6],
                "source":         "scored",
                "scan_date":      datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "fetched_at":     datetime.now(timezone.utc).isoformat(),
            })
    print(f"  → {scored_count} scored jobs (≥65)", file=sys.stderr)

    # ── Source B: today's README jobs (no score, brand new) ────────────────
    print("Fetching today's fresh jobs...", file=sys.stderr)
    result = run([
        "fetch_readme_jobs.py",
        "--sections", "ai_ml,embedded,sre,backend",
        "--visa-only",
        "--max-days", "0",
    ])
    fresh_count = 0
    if result and result.get("ok"):
        for j in result["data"]["jobs"]:
            link = j.get("apply_link", "")
            if not link or link in seen_links: continue
            if not is_relevant(j["title"], j["company"]): continue
            if not has_tech_keyword(j["title"]): continue   # positive filter
            seen_links.add(link)
            fresh_count += 1
            all_jobs.append({
                "id":             j["job_id"],
                "title":          j["title"],
                "company":        j["company"],
                "domain":         DOMAIN_MAP.get(j.get("domain_type", ""), "Backend"),
                "location":       j.get("location", ""),
                "posted":         "today",
                "visa":           "✅ Confirmed" if j.get("visa_confirmed") else "🏛 H-1B Co",
                "visa_confirmed": j.get("visa_confirmed", False),
                "link":           link,
                "score":          None,
                "matched_skills": [],
                "source":         "fresh",
                "scan_date":      datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "fetched_at":     datetime.now(timezone.utc).isoformat(),
            })
    print(f"  → {fresh_count} fresh jobs (today, unscored)", file=sys.stderr)
    print(f"Total: {len(all_jobs)} ({scored_count} scored + {fresh_count} fresh)", file=sys.stderr)

    if args.pretty:
        # Sort: scored first (by score desc), then fresh
        scored = sorted([j for j in all_jobs if j["source"] == "scored"], key=lambda x: -(x["score"] or 0))
        fresh = [j for j in all_jobs if j["source"] == "fresh"]
        print(f"\n{'='*70}")
        print(f"SCORED (≥65) — {len(scored)} jobs")
        print(f"{'='*70}")
        for j in scored:
            v = "✅" if j["visa_confirmed"] else "🏛"
            skills = ", ".join(j["matched_skills"][:4])
            print(f"  [{j['score']:2}] {v} {j['company']:<22} {j['title'][:42]}")
            print(f"       Skills: {skills}")
            print(f"       {j['link']}")
        print(f"\n{'='*70}")
        print(f"FRESH TODAY (unscored) — {len(fresh)} jobs")
        print(f"{'='*70}")
        for j in fresh:
            v = "✅" if j["visa_confirmed"] else "🏛"
            print(f"  {v} {j['company']:<25} {j['title'][:45]}")
            print(f"     {j['link']}")
    else:
        print(json.dumps(all_jobs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
