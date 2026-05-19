#!/usr/bin/env python3
"""
Fetch truly new jobs from zapplyjobs README using job-ID set comparison.

How it works:
  - README time strings ("26m", "1h", "1d") represent scraper-internal processing
    time, NOT how long ago the job was posted on the company ATS. They are NOT
    reliable for freshness filtering.
  - The only reliable method: compare the full set of job IDs in the current README
    against the set from the previous run (stored in id_cache.json).
  - New jobs = IDs in current README that were NOT in the previous run's cache.
  - After each run the cache is updated to the full current ID set.

Usage:
  python3 fetch_readme_jobs.py --sections ai_ml,embedded,sre,backend --visa-only
  python3 fetch_readme_jobs.py --since 2026-05-18T21:00:00+00:00   # manual override
  python3 fetch_readme_jobs.py --schema

Output: JSON {"ok": true, "data": {"jobs": [...], "total": N, "mode": "new|all", ...}}
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

README_URLS = [
    "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Software-Engineering-Jobs-2026/main/README.md",
    "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Jobs-2026/main/README.md",
]

SECTION_MAP = {
    "AI / ML Engineering":            "ai_ml",
    "Infrastructure & Security":      "sre",
    "Systems & Embedded":             "embedded",
    "Software Engineering":           "swe_generic",
    "Solutions & Program Management": "other",
    "Data, AI & Research":            "ai_ml",
    "Hardware & Systems Engineering": "embedded",
    "Security Engineering":           "sre",
    "Business & Operations":          "other",
    "Other Jobs":                     "other",
    "Embedded & Systems":             "embedded",
    "Systems & Network Engineering":  "embedded",
    "DevOps & Infrastructure":        "sre",
    "Full Stack":                     "backend",
    "Mobile Development":             "mobile",
    "Frontend":                       "frontend",
    "QA Engineering":                 "qa",
    "Solutions & Pre-Sales":          "other",
    "Technical Program Management":   "other",
}

DEFAULT_DOMAINS = {"ai_ml", "embedded", "sre", "backend"}

# Stores: {"job_ids": [...], "cached_at": "ISO", "count": N}
# All IDs from the previous run (ALL sections, pre-filter) — used for new-job detection.
CACHE_FILE = os.path.join(os.path.dirname(__file__), "references", "id_cache.json")

SCHEMA = {
    "description": "Fetch new jobs from zapplyjobs README using job-ID set comparison",
    "params": {
        "--sections":  "comma-separated domains: ai_ml,embedded,sre,backend",
        "--visa-only": "only rows with ✅ Sponsor or 🏛 H-1B Co. (default: true)",
        "--since":     "ISO datetime override — show all jobs added to README since this time "
                       "(uses cached_at as reference; omit to use cache-based new-only detection)",
    },
    "output": {"ok": "bool", "data": {"jobs": "list", "total": "int", "mode": "str"}},
    "exit_codes": {"0": "ok", "1": "runtime", "4": "no_data"},
}

OVEREXP_KW = [
    "senior", "sr.", " lead ", "principal", "staff engineer",
    "director", "head of", "manager", " vp ", "vice president",
]


# ── helpers ───────────────────────────────────────────────────────────────────

def ok(data):
    print(json.dumps({"ok": True, "data": data,
                      "meta": {"fetched_at": datetime.now(timezone.utc).isoformat()}}))

def err(code, message, retryable=False):
    print(json.dumps({"ok": False,
                      "error": {"code": code, "message": message, "retryable": retryable}}),
          file=sys.stderr)
    sys.exit(1 if code == "runtime" else 4)

def load_cache():
    """Return (set_of_ids, cached_at_str). Both empty/None if no cache."""
    if not os.path.exists(CACHE_FILE):
        return set(), None
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
        return set(data.get("job_ids", [])), data.get("cached_at")
    except Exception:
        return set(), None

def save_cache(all_ids: set):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({
            "job_ids":   sorted(all_ids),
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "count":     len(all_ids),
        }, f)

def fetch_readme(url):
    req = urllib.request.Request(url, headers={"User-Agent": "job-hunter-skill/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")

def clean_company(raw):
    s = re.sub(r"[🏢🏛🏗]\s*", "", raw)
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s).strip()

def extract_link(raw):
    m = re.search(r'\]\(([^)]+)\)\s*$', raw.strip())
    if m:
        return m.group(1).strip()
    m = re.search(r'https?://[^\s\)\"]+', raw)
    return m.group(0) if m else ""

def make_job_id(company, title, link):
    return "readme-" + hashlib.md5(f"{company}|{title}|{link}".encode()).hexdigest()[:12]

def is_overexp(title):
    return any(kw in title.lower() for kw in OVEREXP_KW)


# ── parser ────────────────────────────────────────────────────────────────────

def parse_readme(readme, target_domains, visa_only, new_ids_only):
    """
    Parse all <details> sections in the README.

    Args:
        new_ids_only: if provided (a set), only return jobs whose job_id is in this set.
                      Pass None to return all jobs matching domain/visa filters.

    Returns:
        (filtered_jobs, all_ids_in_readme)
        all_ids_in_readme includes ALL sections (pre-filter), used to update the cache.
    """
    blocks = re.split(r'<details>', readme)
    filtered_jobs = []
    all_ids = set()
    seen_filtered = set()

    for block in blocks[1:]:
        m = re.search(r'<summary><h3>[^<]*<strong>([^<]+)</strong>', block)
        if not m:
            continue
        section_name = m.group(1).strip()
        domain = SECTION_MAP.get(section_name)

        rows = re.findall(r'^\|(.+)\|$', block, re.MULTILINE)
        for row in rows[2:]:  # skip header + separator
            cells = [c.strip() for c in row.split("|")]
            if len(cells) < 5:
                continue

            company    = clean_company(cells[0])
            title      = re.sub(r'\*\*(.+?)\*\*', r'\1', cells[1]).strip()
            location   = cells[2].strip()
            apply_raw  = cells[5] if len(cells) > 5 else ""
            apply_link = extract_link(apply_raw)

            if not company or not title or not apply_link:
                continue

            job_id = make_job_id(company, title, apply_link)
            all_ids.add(job_id)  # always collect for cache

            # Domain / visa / experience filters
            if domain not in target_domains:
                continue
            if is_overexp(title):
                continue
            visa_ok = ("✅" in cells[4] or "Sponsor" in cells[4]
                       or "🏛" in cells[4] or "H-1B" in cells[4])
            if visa_only and not visa_ok:
                continue

            # New-only gate
            if new_ids_only is not None and job_id not in new_ids_only:
                continue

            if job_id in seen_filtered:
                continue
            seen_filtered.add(job_id)

            filtered_jobs.append({
                "job_id":         job_id,
                "title":          title,
                "company":        company,
                "location":       location,
                "remote":         "remote" in location.lower(),
                "apply_link":     apply_link,
                "domain_type":    domain,
                "section":        section_name,
                "visa_confirmed": visa_ok,
                "visa_possible":  visa_ok,
                "source":         "readme",
            })

    return filtered_jobs, all_ids


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", action="store_true")
    parser.add_argument("--sections", default=None)
    parser.add_argument("--visa-only", action="store_true", default=True)
    parser.add_argument("--since", default=None,
                        help="ISO datetime: treat all jobs in README as candidates, "
                             "but skip those whose job_id was already cached before this time. "
                             "Useful for manual range overrides.")
    args = parser.parse_args()

    if args.schema:
        print(json.dumps(SCHEMA, indent=2))
        return

    target_domains = (
        set(s.strip() for s in args.sections.split(","))
        if args.sections else DEFAULT_DOMAINS
    )

    cached_ids, cached_at = load_cache()
    cache_is_empty = len(cached_ids) == 0

    # Determine which IDs are "new" (not in cache)
    # We'll compute this after fetching both READMEs.

    all_current_ids: set = set()
    all_jobs_raw: list = []   # all jobs from both repos, pre-new-filter
    seen_raw: set = set()

    for url in README_URLS:
        try:
            readme = fetch_readme(url)
        except Exception as e:
            sys.stderr.write(f"Warning: failed to fetch {url}: {e}\n")
            continue

        # Pass new_ids_only=None first to collect ALL IDs, then filter below
        jobs_chunk, ids_chunk = parse_readme(readme, target_domains, args.visa_only,
                                             new_ids_only=None)
        all_current_ids |= ids_chunk
        for j in jobs_chunk:
            if j["job_id"] not in seen_raw:
                seen_raw.add(j["job_id"])
                all_jobs_raw.append(j)

    # Save updated cache (full current ID set, all sections)
    save_cache(all_current_ids)

    # Compute new IDs = in current README but NOT in previous cache
    if cache_is_empty:
        # First run: show nothing (cache just initialized)
        new_ids = set()
        mode = "initialized"
    elif args.since:
        # Manual override: treat everything as new (caller wants a specific window)
        new_ids = {j["job_id"] for j in all_jobs_raw}
        mode = f"all-since-{args.since[:10]}"
    else:
        new_ids = {j["job_id"] for j in all_jobs_raw if j["job_id"] not in cached_ids}
        mode = "new"

    result = [j for j in all_jobs_raw if j["job_id"] in new_ids]

    if cache_is_empty:
        err("no_data",
            f"Cache initialized with {len(all_current_ids)} job IDs. "
            f"Run again to see new jobs since this snapshot.",
            retryable=False)

    if not result:
        err("no_data",
            f"No new jobs since last run (cache: {len(cached_ids)} IDs from {cached_at}). "
            f"README has {len(all_current_ids)} total jobs.",
            retryable=False)

    ok({
        "jobs":        result,
        "total":       len(result),
        "mode":        mode,
        "cached_at":   cached_at,
        "cache_size":  len(cached_ids),
        "total_in_readme": len(all_current_ids),
        "domains":     list(target_domains),
    })


if __name__ == "__main__":
    main()
