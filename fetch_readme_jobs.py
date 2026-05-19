#!/usr/bin/env python3
"""
Fetch jobs by parsing the zapplyjobs README.md section tables.
Covers: AI/ML Engineering, Embedded & Systems, Systems & Network Engineering,
        DevOps & Infrastructure, Full Stack, Software Engineering.

Usage:
  python fetch_readme_jobs.py [--sections ai_ml,embedded,sre,backend,swe] [--visa-only] [--min-days N]
  python fetch_readme_jobs.py --schema

Output: JSON envelope {"ok": true, "data": {"jobs": [...], "total": N}}
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# Both repos are fetched and merged
README_URLS = [
    "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Software-Engineering-Jobs-2026/main/README.md",
    "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Jobs-2026/main/README.md",
]

# Map README section name → internal domain (covers both repos)
SECTION_MAP = {
    # New-Grad-Software-Engineering-Jobs-2026
    "AI / ML Engineering":            "ai_ml",
    "Infrastructure & Security":      "sre",
    "Systems & Embedded":             "embedded",
    "Software Engineering":           "swe_generic",
    "Solutions & Program Management": "other",
    # New-Grad-Jobs-2026
    "Data, AI & Research":            "ai_ml",
    "Hardware & Systems Engineering": "embedded",
    "Security Engineering":           "sre",
    "Business & Operations":          "other",
    "Other Jobs":                     "other",
    # Legacy / fallback names
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

# Which domains to include by default (matching the 4 job-hunter priorities)
DEFAULT_DOMAINS = {"ai_ml", "embedded", "sre", "backend"}

SCHEMA = {
    "description": "Parse zapplyjobs README.md and return jobs by section",
    "params": {
        "--sections": "comma-separated domains: ai_ml,embedded,sre,backend,swe_generic (default: ai_ml,embedded,sre,backend)",
        "--visa-only": "only include rows with ✅ Sponsor (default: true)",
        "--max-days": "only include jobs posted within N days (default: 7)",
    },
    "output": {"ok": "bool", "data": {"jobs": "list[job]", "total": "int", "sections_found": "list[str]"}},
    "exit_codes": {"0": "ok", "1": "runtime", "4": "no_data"},
}

OVEREXP_KW = [
    "senior", "sr.", " lead ", "principal", "staff engineer",
    "director", "head of", "manager", " vp ", "vice president",
]

def ok(data):
    print(json.dumps({"ok": True, "data": data, "meta": {"fetched_at": datetime.now(timezone.utc).isoformat()}}))

def err(code, message, retryable=False):
    print(json.dumps({"ok": False, "error": {"code": code, "message": message, "retryable": retryable}}), file=sys.stderr)
    sys.exit(1 if code == "runtime" else 4)

def fetch_readme(url):
    req = urllib.request.Request(url, headers={"User-Agent": "job-hunter-skill/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")

def parse_posted_days(s):
    """'2d' → 2, '1w' → 7, '3h' → 0, '42m' → 0 (same day)"""
    s = s.strip().lower()
    if s.endswith("d"):
        try:
            return int(s[:-1])
        except ValueError:
            return 999
    if s.endswith("w"):
        try:
            return int(s[:-1]) * 7
        except ValueError:
            return 999
    # hours or minutes → same day
    if s.endswith("h") or s.endswith("min") or s.endswith("m"):
        return 0
    return 999

def posted_ago_str(days):
    if days == 0:
        return "today"
    if days < 7:
        return f"{days}d ago"
    if days < 30:
        return f"{days // 7}w ago"
    return f"{days}d ago"

def posted_iso(days):
    """Approximate ISO timestamp from days ago."""
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.isoformat()

def clean_company(raw):
    """'🏢 **OpenAI**' → 'OpenAI'"""
    s = re.sub(r"[🏢🏛🏗]\s*", "", raw)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    return s.strip()

def extract_apply_link(raw):
    """Extract URL from markdown image-link: [![...](...)](URL)"""
    m = re.search(r'\]\(([^)]+)\)\s*$', raw.strip())
    if m:
        return m.group(1).strip()
    # fallback: any URL
    m = re.search(r'https?://[^\s\)\"]+', raw)
    return m.group(0) if m else ""

def make_job_id(company, title, link):
    key = f"{company}|{title}|{link}"
    return "readme-" + hashlib.md5(key.encode()).hexdigest()[:12]

def is_overexp(title):
    t = title.lower()
    return any(kw in t for kw in OVEREXP_KW)

def parse_sections(readme, target_domains, visa_only, max_days):
    """Split README into <details> blocks and parse each table."""

    # Split on <details> blocks
    blocks = re.split(r'<details>', readme)

    jobs = []
    sections_found = []

    for block in blocks[1:]:  # skip preamble
        # Extract section name
        m = re.search(r'<summary><h3>[^<]*<strong>([^<]+)</strong>', block)
        if not m:
            continue
        section_name = m.group(1).strip()
        domain = SECTION_MAP.get(section_name)

        if domain is None or domain not in target_domains:
            continue

        sections_found.append(section_name)

        # Find the table rows (skip header)
        rows = re.findall(r'^\|(.+)\|$', block, re.MULTILINE)
        if len(rows) < 2:
            continue

        for row in rows[2:]:  # skip header + separator
            cells = [c.strip() for c in row.split("|")]
            if len(cells) < 5:
                continue

            company_raw, title_raw, location_raw, posted_raw, visa_raw = cells[0], cells[1], cells[2], cells[3], cells[4]
            apply_raw = cells[5] if len(cells) > 5 else ""

            company = clean_company(company_raw)
            title = re.sub(r'\*\*(.+?)\*\*', r'\1', title_raw).strip()
            location = location_raw.strip()
            posted_days = parse_posted_days(posted_raw)
            # ✅ Sponsor = explicitly confirmed; 🏛 H-1B Co. = known H-1B employer (also valid)
            visa_confirmed = "✅" in visa_raw or "Sponsor" in visa_raw or "🏛" in visa_raw or "H-1B" in visa_raw
            apply_link = extract_apply_link(apply_raw)

            if not company or not title:
                continue
            if visa_only and not visa_confirmed:
                continue
            if posted_days > max_days:
                continue
            if is_overexp(title):
                continue

            job_id = make_job_id(company, title, apply_link)

            jobs.append({
                "job_id":        job_id,
                "title":         title,
                "company":       company,
                "location":      location,
                "remote":        "remote" in location.lower(),
                "posted_at":     posted_iso(posted_days),
                "posted_ago":    posted_ago_str(posted_days),
                "posted_days":   posted_days,
                "apply_link":    apply_link,
                "domain_type":   domain,
                "section":       section_name,
                "visa_confirmed": visa_confirmed,
                "visa_possible": visa_confirmed,
                "source":        "readme",
            })

    # sort: newest first
    jobs.sort(key=lambda x: x["posted_days"])
    return jobs, sections_found

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", action="store_true")
    parser.add_argument("--sections", default=None,
                        help="comma-separated domains (default: ai_ml,embedded,sre,backend)")
    parser.add_argument("--visa-only", action="store_true", default=True)
    parser.add_argument("--max-days", type=int, default=7)
    args = parser.parse_args()

    if args.schema:
        print(json.dumps(SCHEMA, indent=2))
        return

    if args.sections:
        target_domains = set(s.strip() for s in args.sections.split(","))
    else:
        target_domains = DEFAULT_DOMAINS

    all_jobs = []
    all_sections = []
    seen_ids = set()
    for url in README_URLS:
        try:
            readme = fetch_readme(url)
        except urllib.error.URLError as e:
            sys.stderr.write(f"Warning: failed to fetch {url}: {e}\n")
            continue
        except Exception as e:
            sys.stderr.write(f"Warning: {url}: {e}\n")
            continue
        jobs_chunk, sections_chunk = parse_sections(readme, target_domains, args.visa_only, args.max_days)
        for j in jobs_chunk:
            if j["job_id"] not in seen_ids:
                seen_ids.add(j["job_id"])
                all_jobs.append(j)
        all_sections.extend(s for s in sections_chunk if s not in all_sections)

    jobs = all_jobs
    sections_found = all_sections

    if not jobs:
        err("no_data", f"No jobs found in sections: {target_domains} (max_days={args.max_days}, visa_only={args.visa_only})", retryable=True)

    ok({
        "jobs": jobs,
        "total": len(jobs),
        "sections_found": sections_found,
        "domains_searched": list(target_domains),
        "max_days": args.max_days,
    })

if __name__ == "__main__":
    main()
