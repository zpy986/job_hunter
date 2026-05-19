#!/usr/bin/env python3
"""
Daily job scan for Peiyi Zhang.
Fetches new jobs from zapplyjobs repos, filters by profile, outputs JSON.

Usage:
    python3 daily_scan.py              # output JSON to stdout
    python3 daily_scan.py --pretty     # human-readable table
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

from profile import (
    TARGET_SECTIONS, SKIP_TITLE_KW, SKIP_COMPANY,
    VISA_KEYWORDS, MAX_POSTED_DAYS
)

README_URLS = [
    "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Software-Engineering-Jobs-2026/main/README.md",
    "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Jobs-2026/main/README.md",
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "peiyi-job-hunter/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_posted_days(s):
    s = s.strip().lower()
    if s.endswith("d"):
        try: return int(s[:-1])
        except: return 999
    if s.endswith("w"):
        try: return int(s[:-1]) * 7
        except: return 999
    if s.endswith("h") or s.endswith("m") or s.endswith("min"):
        return 0
    return 999


def clean_company(raw):
    s = re.sub(r"[🏢🏛🏗]\s*", "", raw)
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s).strip()


def extract_link(raw):
    m = re.search(r"\]\(([^)]+)\)\s*$", raw.strip())
    return m.group(1).strip() if m else ""


def make_id(company, title, link):
    return "readme-" + hashlib.md5(f"{company}|{title}|{link}".encode()).hexdigest()[:12]


def is_relevant(title, company):
    t = title.lower()
    c = company.lower()
    if any(k in t for k in SKIP_TITLE_KW): return False
    if any(k in c for k in SKIP_COMPANY): return False
    return True


def parse_readme(content):
    jobs = []
    blocks = re.split(r"<details>", content)
    for block in blocks[1:]:
        m = re.search(r"<summary><h3>[^<]*<strong>([^<]+)</strong>", block)
        if not m: continue
        section = m.group(1).strip()
        domain = TARGET_SECTIONS.get(section)
        if not domain: continue
        rows = re.findall(r"^\|(.+)\|$", block, re.MULTILINE)
        if len(rows) < 2: continue
        for row in rows[2:]:
            cells = [c.strip() for c in row.split("|")]
            if len(cells) < 5: continue
            company = clean_company(cells[0])
            title = re.sub(r"\*\*(.+?)\*\*", r"\1", cells[1]).strip()
            location = cells[2].strip()
            posted_days = parse_posted_days(cells[3])
            visa_raw = cells[4]
            link = extract_link(cells[5]) if len(cells) > 5 else ""
            if not company or not title: continue
            if not any(k in visa_raw for k in VISA_KEYWORDS): continue
            if posted_days > MAX_POSTED_DAYS: continue
            if not is_relevant(title, company): continue
            visa_label = "✅ Confirmed" if "✅" in visa_raw else "🏛 H-1B Co"
            jobs.append({
                "id": make_id(company, title, link),
                "title": title,
                "company": company,
                "domain": domain,
                "location": location,
                "posted": cells[3].strip(),
                "visa": visa_label,
                "visa_confirmed": "✅" in visa_raw,
                "link": link,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
    return jobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    all_jobs = []
    seen_ids = set()

    for url in README_URLS:
        repo = url.split("/")[4]
        try:
            content = fetch(url)
            jobs = parse_readme(content)
            new = [j for j in jobs if j["id"] not in seen_ids]
            for j in new:
                seen_ids.add(j["id"])
                all_jobs.append(j)
            print(f"[{repo}] {len(new)} new jobs", file=sys.stderr)
        except urllib.error.URLError as e:
            print(f"[{repo}] fetch error: {e}", file=sys.stderr)

    print(f"Total: {len(all_jobs)} jobs", file=sys.stderr)

    if args.pretty:
        by_domain = {}
        for j in all_jobs:
            by_domain.setdefault(j["domain"], []).append(j)
        for domain, jobs in sorted(by_domain.items()):
            print(f"\n── {domain} ({len(jobs)}) ──")
            for j in sorted(jobs, key=lambda x: x["visa_confirmed"], reverse=True):
                v = j["visa"]
                print(f"  {v:15} {j['company']:<25} {j['title'][:45]}")
                print(f"             {j['link']}")
    else:
        print(json.dumps(all_jobs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
