#!/usr/bin/env python3
"""
Fetch and filter new jobs from zapplyjobs GitHub repos.
Usage:
  python fetch_jobs.py [--since YYYY-MM-DDTHH:MM:SSZ] [--domain software|data|all] [--limit N]
  python fetch_jobs.py --schema
Output: JSON envelope {"ok": true, "data": {"jobs": [...], "total": N, "fetched_at": "..."}}
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

REPOS = {
    "software": "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Software-Engineering-Jobs-2026/main/.github/data/current_jobs.json",
    "data":     "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Data-Science-Jobs-2026/main/.github/data/current_jobs.json",
    "all":      "https://raw.githubusercontent.com/zapplyjobs/New-Grad-Jobs-2026/main/.github/data/current_jobs.json",
}

SCHEMA = {
    "description": "Fetch and filter new grad jobs from zapplyjobs GitHub repos",
    "params": {
        "--since": "ISO8601 datetime, only jobs posted after this (default: 7 days ago)",
        "--domain": "software | data | all (default: software)",
        "--limit": "max jobs to return (default: 200)",
        "--visa-only": "only include jobs with sponsorship signal (default: true)",
    },
    "output": {"ok": "bool", "data": {"jobs": "list[job]", "total": "int", "fetched_at": "str"}},
    "exit_codes": {"0": "ok", "1": "runtime error", "3": "invalid args", "4": "no data"},
}

def ok(data):
    print(json.dumps({"ok": True, "data": data, "meta": {"fetched_at": datetime.now(timezone.utc).isoformat()}}))

def err(code, message, retryable=False):
    print(json.dumps({"ok": False, "error": {"code": code, "message": message, "retryable": retryable}}), file=sys.stderr)
    exit_map = {"invalid_args": 3, "no_data": 4, "runtime": 1}
    sys.exit(exit_map.get(code, 1))

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "job-hunter-skill/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def has_visa_signal(job):
    e = job.get("enrichment") or {}
    return e.get("sponsors_visa") is True or e.get("possible_sponsor") is True

# Title keywords that imply >3 years experience requirement
OVEREXP_TITLE_KW = [
    "senior", "sr.", "lead", "principal", "staff", "director",
    "head of", "manager", "vp ", "vice president", "partner",
]
# YOE patterns in title/tags that imply >3 years
OVEREXP_YOE_KW = ["4+ year", "5+ year", "6+ year", "7+ year", "8+ year",
                   "4+ yr", "5+ yr", "10+ year"]

def is_overqualified_requirement(job):
    """Return True if job explicitly requires >3 years experience."""
    title = (job.get("job_title") or "").lower()
    exp_tag = (job.get("tags") or {}).get("experience", "")

    # title-based check
    if any(kw in title for kw in OVEREXP_TITLE_KW):
        return True

    # experience tag check (senior / director level)
    if exp_tag in ("senior", "director", "executive", "manager"):
        return True

    return False

def fmt_ago(posted_iso):
    """Convert ISO timestamp to human-readable relative time, e.g. '2h ago', '3d ago'."""
    if not posted_iso:
        return "unknown"
    try:
        posted_dt = datetime.fromisoformat(posted_iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - posted_dt
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}min ago"
        elif hours < 24:
            return f"{int(hours)}h ago"
        elif hours < 24 * 7:
            return f"{int(hours / 24)}d ago"
        elif hours < 24 * 30:
            return f"{int(hours / 24 / 7)}w ago"
        else:
            return posted_dt.strftime("%Y-%m-%d")
    except Exception:
        return posted_iso[:10]

def score_domain(title, domains):
    title_l = title.lower()
    # Priority 1: Embedded / Systems
    embedded_kw = ["embedded", "firmware", "kernel", "driver", "wireless", "802.11",
                   "networking", "rtos", "freertos", "systems software", "network software",
                   "low-level", "platform software", "bsp", "bluetooth", "wi-fi", "wifi"]
    # Priority 2: ML / AI
    ai_kw = ["ml ", "llm", " ai ", "ai/", "/ai", "rag", "nlp", "machine learning",
             "deep learning", "research engineer", "research scientist", "inference",
             "language model", "generative", "foundation model", "mlops"]
    # Priority 3: Backend / Platform
    be_kw = ["backend", "back-end", "back end", "platform engineer", "distributed",
             "infrastructure engineer", "infra engineer", "data platform", "api engineer"]
    # Priority 4: SRE / DevOps
    sre_kw = ["sre", "site reliability", "reliability engineer", "devops", "dev ops",
              "production engineer", "cloud engineer", "devsecops"]

    if any(k in title_l for k in embedded_kw):
        return "embedded", 35
    if any(k in title_l for k in ai_kw):
        return "ai_ml", 30
    if any(k in title_l for k in be_kw):
        return "backend", 22
    if any(k in title_l for k in sre_kw):
        return "sre", 18
    if "software engineer" in title_l or "swe" in title_l:
        return "swe_generic", 12
    if "data" in domains:
        return "data", 12
    return "other", 5

PEIYI_SKILLS = {
    "ml", "llm", "rag", "sft", "lora", "dpo", "vllm", "langchain", "pytorch",
    "tensorflow", "rlhf", "nlp", "milvus", "elasticsearch", "faiss", "transformers",
    "fine-tuning", "fine tuning", "inference", "python", "c", "c++", "java",
    "javascript", "go", "cuda", "linux", "kernel", "embedded", "distributed",
    "networking", "tcp", "docker", "fastapi", "redis", "mysql", "mongodb", "aws",
    "git", "openmp", "hpc", "nvidia", "multimodal", "bm25", "vector", "retrieval",
    "reranking", "llamaindex", "hugging face", "huggingface", "qwen", "llava",
    "rlhf", "reinforcement", "alignment", "agent", "agents", "aho-corasick",
    "pcie", "gpu", "a100", "react", "node", "typescript", "shell", "bash",
}

HIGH_VALUE = {"vllm", "rag", "pytorch", "langchain", "cuda", "llm", "transformer",
              "fine-tuning", "fine tuning", "sft", "dpo", "milvus", "hugging face",
              "huggingface", "inference", "multimodal", "agent", "agents"}

def score_job(job):
    e = job.get("enrichment") or {}
    title = job.get("job_title", "")
    domains = (job.get("tags") or {}).get("domains", [])
    location = job.get("job_location", "")
    is_remote = job.get("job_is_remote", False) or e.get("is_remote", False)
    posted = job.get("job_posted_at", "")

    score = 0
    breakdown = {}

    # domain
    domain_type, domain_pts = score_domain(title, domains)
    score += domain_pts
    breakdown["domain"] = domain_pts

    # required skills
    req_skills = [s.lower() for s in (e.get("required_skills") or [])]
    req_pts = 0
    matched_req = []
    for s in req_skills:
        if any(p in s or s in p for p in PEIYI_SKILLS):
            matched_req.append(s)
            req_pts += 3
            if any(h in s or s in h for h in HIGH_VALUE):
                req_pts += 2
    req_pts = min(req_pts, 35)
    score += req_pts
    breakdown["required_skills"] = req_pts

    # nice-to-have
    nth_skills = [s.lower() for s in (e.get("nice_to_have_skills") or [])]
    nth_pts = 0
    matched_nth = []
    for s in nth_skills:
        if any(p in s or s in p for p in PEIYI_SKILLS):
            matched_nth.append(s)
            nth_pts += 2
    nth_pts = min(nth_pts, 15)
    score += nth_pts
    breakdown["nice_to_have"] = nth_pts

    # location/remote
    top_states = ["ca", "ny", "wa", "tx", "ma", "il", "co", "ga", "va", "fl",
                  "california", "new york", "washington", "texas", "massachusetts"]
    if is_remote:
        score += 10
        breakdown["location"] = 10
    elif any(s in location.lower() for s in top_states):
        score += 5
        breakdown["location"] = 5
    else:
        score += 3
        breakdown["location"] = 3

    # recency
    recency_pts = 0
    if posted:
        try:
            posted_dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - posted_dt).total_seconds() / 3600
            if age_hours <= 24:
                recency_pts = 5
            elif age_hours <= 72:
                recency_pts = 3
            elif age_hours <= 168:
                recency_pts = 2
        except Exception:
            pass
    score += recency_pts
    breakdown["recency"] = recency_pts

    return {
        "score": score,
        "domain_type": domain_type,
        "matched_required": matched_req,
        "matched_nice_to_have": matched_nth,
        "breakdown": breakdown,
        "visa_confirmed": e.get("sponsors_visa") is True,
        "visa_possible": e.get("possible_sponsor") is True,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", action="store_true")
    parser.add_argument("--since", default=None)
    parser.add_argument("--domain", default="software", choices=["software", "data", "all"])
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--visa-only", action="store_true", default=True)
    parser.add_argument("--min-score", type=int, default=65)
    args = parser.parse_args()

    if args.schema:
        print(json.dumps(SCHEMA, indent=2))
        return

    # parse since
    since_dt = None
    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        except ValueError:
            err("invalid_args", f"--since must be ISO8601, got: {args.since}")
    else:
        from datetime import timedelta
        since_dt = datetime.now(timezone.utc) - timedelta(days=7)

    url = REPOS[args.domain]
    try:
        jobs = fetch_json(url)
    except urllib.error.URLError as e:
        err("runtime", f"Failed to fetch jobs: {e}", retryable=True)
    except Exception as e:
        err("runtime", str(e))

    if not isinstance(jobs, list):
        err("no_data", "Unexpected data format from upstream")

    results = []
    for job in jobs:
        posted = job.get("job_posted_at", "")
        if since_dt and posted:
            try:
                posted_dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
                if posted_dt < since_dt:
                    continue
            except Exception:
                pass

        if args.visa_only and not has_visa_signal(job):
            continue

        if is_overqualified_requirement(job):
            continue

        match = score_job(job)
        if match["score"] < args.min_score:
            continue

        results.append({
            "job_id": job.get("job_id"),
            "title": job.get("job_title"),
            "company": job.get("employer_name"),
            "location": job.get("job_location"),
            "remote": job.get("job_is_remote", False),
            "posted_at": posted,
            "posted_ago": fmt_ago(posted),
            "apply_link": job.get("job_apply_link"),
            "score": match["score"],
            "domain_type": match["domain_type"],
            "matched_skills": match["matched_required"],
            "visa_confirmed": match["visa_confirmed"],
            "visa_possible": match["visa_possible"],
            "breakdown": match["breakdown"],
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:args.limit]

    if not results:
        err("no_data", f"No matching jobs found (since={since_dt.isoformat()}, domain={args.domain})", retryable=True)

    ok({"jobs": results, "total": len(results), "since": since_dt.isoformat(), "domain": args.domain})

if __name__ == "__main__":
    main()
