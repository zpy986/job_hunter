# Peiyi Zhang — Job Matching Profile
# Used by daily_scan.py to filter jobs

TARGET_SECTIONS = {
    "AI / ML Engineering":            "AI/ML",
    "Data, AI & Research":            "AI/ML",
    "Infrastructure & Security":      "Systems",
    "Systems & Embedded":             "Embedded",
    "Hardware & Systems Engineering": "Embedded",
    "DevOps & Infrastructure":        "Systems",
    "Software Engineering":           "Backend",
    "Security Engineering":           "Systems",
}

SKIP_TITLE_KW = [
    # seniority
    "senior ", "sr.", "principal", "staff engineer", "director",
    "manager", "head of", " vp ", "vice president",
    # experience gate
    "5+ years", "6+ years", "7+ years", "8+ years",
    # non-SW roles
    "it support", "helpdesk", "data center engineer",
    "civil ", "structural", "mechanical engi", "thermal engi",
    "munitions", "weapons", "flight dynamics", "satellite systems",
    "spacecraft systems", "model-based", "process engineer",
    "quality engineer", "manufacturing", "customer quality",
    "validation engineer", "clearance required", "secret clearance",
    "program manager", "sales ", "account ", "field service",
    # non-tech engineering
    "hvac", "electrical engineer", "electronics engineer",
    "hardware engineer", "instrumentation", "propulsion",
    "facilities", "x-ray", "pharmacology", "pathology",
    "motor controls", "avionics", "power systems",
    "thermal ", "explosives", "nuclear",
    # gov-contractor advisory (not engineering)
    "sme ", " sme", "seta ", "subject matter",
    # quant/finance/non-SW research
    "data analyst", "business intelligence", "business analyst",
    "data scientist", "quantitative research",
]

# For fresh/unscored jobs: title must contain at least one of these
REQUIRE_TITLE_KW = [
    "software", "swe", "ml ", "machine learning", "ai ", " ai",
    "embedded", "linux", "kernel", "firmware", "driver",
    "backend", "platform", "infrastructure", "sre", "devops",
    "inference", "llm", "nlp", "rag", "research engineer",
    "systems engineer", "network engineer", "security engineer",
    "cloud engineer", "data engineer",
]

SKIP_COMPANY = [
    "honeywell",    # confirmed no visa sponsor
    "sel",          # US citizen required (no trailing space — matches "sel " and "sel")
    "schweitzer",   # US citizen required
    "google",       # 7+ year experience requirement
]

VISA_KEYWORDS = ["✅", "Sponsor", "🏛", "H-1B"]
MAX_POSTED_DAYS = 2   # only pull jobs from last 2 days
