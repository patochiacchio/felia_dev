# app/utils.py (reemplazo completo)
import re
from typing import Iterable, List

_token_re = re.compile(r"[\w\-/\.]+", re.UNICODE)

def tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [t.lower() for t in _token_re.findall(text)]

def contains_all(haystack: str, tokens: Iterable[str]) -> bool:
    h = haystack.lower()
    return all(tok.lower() in h for tok in tokens if tok)

def contains_any(haystack: str, tokens: Iterable[str]) -> bool:
    h = haystack.lower()
    return any(tok.lower() in h for tok in tokens if tok)

def normalize_question(q: str) -> str:
    if not q: return ""
    s = q.lower()
    s = re.sub(r"\d+([.,]\d+)?", "#", s)
    s = re.sub(r"[^\w#]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()
