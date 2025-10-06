from __future__ import annotations
from typing import List, Dict, Any
import re, unicodedata

def _n(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode()
    return re.sub(r'\s+',' ', s).strip().lower()

def _qty(it):
    try:
        return float(str(it.get("qty_available","0")).replace(",",".")) 
    except: 
        return 0.0

def score(item: Dict[str, Any], must: List[str], nots: List[str]) -> float:
    name = _n(item.get("name","")) + " " + _n(item.get("default_code",""))
    s = 0.0
    for m in must:
        if _n(m) in name: s += 2.0
    for n in nots:
        if _n(n) in name: s -= 3.0
    if _qty(item) > 0: s += 1.5
    return s

def rank_and_cut(items: List[Dict[str, Any]], must_tokens: List[str], not_tokens: List[str]) -> List[Dict[str, Any]]:
    # dedup por default_code
    seen = set(); uniq: List[Dict[str, Any]] = []
    for it in items:
        code = it.get("default_code") or it.get("code") or ""
        if code in seen: 
            continue
        seen.add(code); uniq.append(it)
    scored = [(score(it, must_tokens, not_tokens), it) for it in uniq]
    scored.sort(key=lambda x: x[0], reverse=True)
    # devolvemos 2–4 items con umbral básico
    return [it for sc,it in scored[:4] if sc > -1.5]

def pretty_list(items: List[Dict[str, Any]], show_prices=True, currency="AR$") -> str:
    out: List[str] = []
    for it in items:
        name = (it.get("name","") or "").strip()
        code = (it.get("default_code","") or "").strip()
        price = it.get("price")
        disp = "Disponible" if it.get("qty_available") not in (None, "", "0", 0, "None") else "Sin stock"
        if show_prices and price not in (None, ""):
            out.append(f"**{name}** — Código: {code} — {currency} {price} — {disp}")
        else:
            out.append(f"**{name}** — Código: {code} — {disp}")
    return "\n".join(out)
