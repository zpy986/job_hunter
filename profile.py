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
    "senior ", "sr.", "principal", "staff engineer", "director",
    "manager", "head of", " vp ", "vice president",
    "5+ years", "6+ years", "7+ years", "8+ years",
    "it support", "helpdesk", "data center engineer",
    "civil ", "structural", "mechanical engi", "thermal engi",
    "munitions", "weapons", "flight dynamics", "satellite systems",
    "spacecraft systems", "model-based", "process engineer",
    "quality engineer", "manufacturing", "customer quality",
    "validation engineer", "clearance required", "secret clearance",
    "program manager", "sales ", "account ", "field service",
]

SKIP_COMPANY = [
    "honeywell",       # confirmed no visa sponsor
    "sel ",            # US citizen required
    "schweitzer",      # US citizen required
    "google",          # 7+ year experience requirement
]

VISA_KEYWORDS = ["✅", "Sponsor", "🏛", "H-1B"]
MAX_POSTED_DAYS = 2   # only pull jobs from last 2 days
