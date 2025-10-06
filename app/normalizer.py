import re

def normalize_user_text(t: str) -> str:
    t = (t or "").strip()
    return re.sub(r'\s+', ' ', t)

def normalize_units(text: str):
    units = {}
    mm = re.findall(r'(\d+)\s*mm\b', text, flags=re.I)
    if mm: units["mm"] = mm[-1]
    pulg = re.findall(r'(\d+\s*/\s*\d+)\s*("|pulg|in)\b', text, flags=re.I)
    if pulg: units["in"] = pulg[-1].replace(" ", "")
    return units
