from __future__ import annotations
import hashlib, random, re, unicodedata
from typing import Dict, Any, List, Set

# Stopwords/fillers conversacionales (no son sinónimos de rubro)
STOPWORDS_RAW: Set[str] = {
    "hola","buenas","buenos","dias","tardes","noches",
    "necesito","quiero","busco","tengo","traigo","me","va","vale",
    "para","por","de","del","la","el","un","una","unos","unas","los","las","y","o","con","sin","que",
    "eso","esa","esos","esas","este","esta","estos","estas","ahi","aca","ahora","porfa","porfavor","favor",
    "algo","medio","creo","tipo","dato","primero","definir","prefieris","preferis","prefiero","prefiere",
    "ok","dale","bien","gracias","listo","cualquiera","todo"
}

TOKEN_RE    = re.compile(r'[a-z0-9áéíóúñ#"/\-]+', re.I)
W_RE        = re.compile(r'\b(\d{2,4})\s*w\b', re.I)
MM_RE       = re.compile(r'\b(\d+)\s*mm\b', re.I)
IN_FRAC_RE  = re.compile(r'\b(\d+\s*/\s*\d+)\s*(?:"|pulg|in)\b', re.I)
IN_WHO_RE   = re.compile(r'\b(\d+)"\b', re.I)
M_RE        = re.compile(r'\b(\d+)\s*(?:m|metros)\b', re.I)
TAIL_RUNS   = re.compile(r'(.)\1+$', re.I)  # colapsa finales alargados: holaa -> hola

def _seed(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:12], 16)

def _price(seed: int) -> float:
    rng = random.Random(seed + 3)
    return round(1500 + rng.random() * 12000, 2)

def _stock(seed: int) -> int:
    rng = random.Random(seed + 11)
    return (1 if rng.random() < 0.8 else 0) * (1 + int(rng.random() * 30))

def _title(s: str) -> str:
    s = (s or "").strip()
    if not s: return ""
    return s[:1].upper() + s[1:]

def _norm(s: str) -> str:
    # minúsculas + sin acentos
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r'\s+', ' ', s)

# stopwords normalizadas (acentos fuera)
STOPWORDS: Set[str] = { _norm(w) for w in STOPWORDS_RAW }

def _units_from_text(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    w  = W_RE.findall(text or "")
    mm = MM_RE.findall(text or "")
    inf = IN_FRAC_RE.findall(text or "")
    inw = IN_WHO_RE.findall(text or "")
    m  = M_RE.findall(text or "")
    if w:   out["w"]  = w[-1]
    if mm:  out["mm"] = mm[-1]
    if inf: out["in"] = inf[-1].replace(" ", "")
    if inw and "in" not in out: out["in"] = inw[-1]
    if m:   out["m"]  = m[-1]
    return out

def _family_tokens(family: str) -> Set[str]:
    # tokens de la familia, normalizados (para no repetirlos en los detalles)
    return { t for t in re.findall(r'[a-z0-9]+', _norm(family)) if t }

def _collapse_trailing_runs(tok: str) -> str:
    # Solo colapsa repeticiones al final (holaa -> hola). No afecta 'llave', 'perro', etc.
    return TAIL_RUNS.sub(r'\1', tok)

def _is_stopword(tok: str) -> bool:
    """
    Considera stopword si:
      - el token normalizado está en STOPWORDS, o
      - tras colapsar repeticiones finales (holaa->hola), el resultado está en STOPWORDS.
    """
    n = _norm(tok)
    if n in STOPWORDS:
        return True
    n2 = _collapse_trailing_runs(n)
    return n2 in STOPWORDS

def _sig_tokens(text: str, limit: int, ban_norm: Set[str]) -> List[str]:
    """
    Extrae tokens 'fuertes' SOLO de lo que dijo el usuario/GPT.
    - Sin sinónimos ni mapeos.
    - Filtra stopwords, números sueltos, repeticiones finales (holaa), y tokens de family/unidades (por su forma normalizada).
    - Mantiene la forma original del token para mostrar (no todo en ascii), pero compara con normalizado.
    """
    tokens_raw = TOKEN_RE.findall(text or "")
    out: List[str] = []
    seen_norm: Set[str] = set()
    for t in tokens_raw:
        t_strip = t.strip("-/").strip()
        if not t_strip:
            continue
        t_norm = _collapse_trailing_runs(_norm(t_strip))
        if len(t_norm) < 2:
            continue
        if t_norm.isdigit():
            continue
        if _is_stopword(t_norm):
            continue
        if t_norm in ban_norm:
            continue
        if t_norm in seen_norm:
            continue
        seen_norm.add(t_norm)
        out.append(t_strip)
        if len(out) >= limit:
            break
    return out

def _units_label(u: Dict[str, str]) -> List[str]:
    parts: List[str] = []
    if not isinstance(u, dict): 
        return parts
    # Orden amigable
    if u.get("w"):  parts.append(f'{u["w"]}W')
    if u.get("mm"): parts.append(f'{u["mm"]}mm')
    if u.get("in"): parts.append(f'{u["in"]}"')
    if u.get("m"):  parts.append(f'{u["m"]}m')
    return parts

def _compose_name(family: str, units: Dict[str,str], tokens: List[str]) -> str:
    head = _title(family) if family else "Ítem"
    uni  = _units_label(units)
    details: List[str] = []
    if uni: details.append(" ".join(uni))
    if tokens: details.append(" · ".join(tokens[:3]))
    name = f"{head} — {' · '.join(details)}" if details else head
    name = re.sub(r'\s+', ' ', name).strip()
    name = name.replace(' . ', ' · ')
    return name

def generate_mock_products(plan: Dict[str, Any], context_text: str, target: int = 3) -> List[Dict[str, Any]]:
    """
    Genera items de demo ESPECÍFICOS pero NEUTROS:
    - Usa family literal si viene (no mapea familias).
    - Usa únicamente unidades y tokens reales del chat.
    - Elimina basura: acentos normalizados para comparar, 'holaa'/'holaaa', 'todo', etc.
    - Evita duplicar el nombre de la familia o las unidades en los tokens (comparación normalizada).
    - No agrega sinónimos ni palabras nuevas.
    """
    family = (plan.get("family") or "").strip()
    # Unidades: preferimos las del plan, luego detectamos del contexto
    units = (plan.get("units") or {}) | _units_from_text(context_text or plan.get("q", ""))

    # Lista de ban normalizada = unidades + tokens de la familia
    ban_norm: Set[str] = set(_norm(v) for v in units.values() if isinstance(v, str))
    ban_norm |= _family_tokens(family)

    # Tokens significativos del último tramo de conversación (forma original preservada)
    tokens = _sig_tokens(context_text or plan.get("q",""), limit=6, ban_norm=ban_norm)

    base_name = _compose_name(family, units, tokens)

    n = max(2, min(target or 3, 4))
    items: List[Dict[str, Any]] = []
    for i in range(n):
        name = f"{base_name} — Variante {i+1}"
        sd = _seed(name)
        items.append({
            "name": name,
            "default_code": str(1000 + (sd % 9000)),
            "price": _price(sd),
            "qty_available": _stock(sd),
        })
    return items
