from __future__ import annotations
import csv, os, unicodedata, re
from typing import List, Dict, Any, Iterable, Tuple

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode()
    return re.sub(r'\s+',' ', s).strip().lower()

# Tokenizador genérico (palabras, números, medidas). NO agrega sinónimos.
_TOKEN_RE = re.compile(r'(#\d+|\d+/\d+|\d+mm|\d+\s*mm|\d+["]|[a-z0-9áéíóúñ]+)')

def _tokenize(s: str) -> List[str]:
    s = _norm(s)
    toks = [t.strip().replace(" mm","mm") for t in _TOKEN_RE.findall(s) if t.strip()]
    # dedup manteniendo orden
    out, seen = [], set()
    for t in toks:
        if t not in seen:
            seen.add(t); out.append(t)
    return out

class LocalCatalog:
    def __init__(self, csv_path: str):
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Catálogo no encontrado: {csv_path}")
        self.rows: List[Dict[str, Any]] = []
        with open(csv_path, newline='', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                r["_norm_name"] = _norm(r.get("name",""))
                r["_norm_code"] = _norm(r.get("default_code",""))
                self.rows.append(r)

    def search(self, q: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        q = { "tokens": ["..."], "not": ["..."], "family": "..." }
        AND suave (sin reglas por rubro):
          - >=3 tokens → pedimos al menos 2 coincidencias (name/code).
          - 1–2 tokens  → pedimos todas.
        NOT fuerte: si aparece en name/code, se descarta.
        family, si viene, se usa como SUBCADENA literal (no hay mapeos).
        """
        tokens = [_norm(t) for t in q.get("tokens", []) if t]
        nots   = [_norm(t) for t in q.get("not", []) if t]
        family = _norm(q.get("family","")) if q.get("family") else None

        needed = len(tokens)
        min_hits = 2 if needed >= 3 else needed

        out: List[Dict[str, Any]] = []
        for r in self.rows:
            name = r["_norm_name"]; code = r["_norm_code"]

            if any(n in name or n in code for n in nots):
                continue

            hits = sum(1 for tok in tokens if tok in name or tok in code)
            if hits < min_hits:
                continue

            if family and (family not in name and family not in code):
                continue

            out.append(r)
        return out

# Variantes genéricas (sin sinónimos)
def _variants_from_tokens(tokens: List[str]) -> Iterable[List[str]]:
    if tokens:
        yield tokens
    if len(tokens) > 1:
        rev = list(reversed(tokens))
        if rev != tokens:
            yield rev
    # singular/plural simple (morfología genérica, no sinónimos)
    def sgpl(tok: str) -> Tuple[str, str]:
        return (tok, tok[:-1]) if tok.endswith('s') else (tok, tok + 's')
    if tokens:
        y = [sgpl(t)[0] for t in tokens]
        if y != tokens:
            yield y
    # ventanas
    if len(tokens) >= 2:
        yield tokens[:2]; yield tokens[-2:]
    if len(tokens) >= 3:
        yield tokens[:3]; yield tokens[-3:]

def build_query_variants(plan: Dict[str, Any], target: int = 30) -> List[Dict[str, Any]]:
    """
    plan = {q, must[], not[], units{}, family}
    Genera 25/30/40 variantes SOLO con tokens del usuario (y unidades si vinieron).
    """
    def nrm(x): 
        return _norm(x) if isinstance(x, str) else ""

    # tokens base
    base_tokens = _tokenize(nrm(plan.get("q","")))
    for m in (plan.get("must") or []):
        base_tokens += _tokenize(nrm(m))

    # unidades como tokens neutrales (si existen)
    u = plan.get("units") or {}
    if "mm" in u: base_tokens += [f'{_norm(u["mm"])}mm']
    if "in" in u: base_tokens += [f'{_norm(u["in"])}"']
    if "m"  in u: base_tokens += [f'{_norm(u["m"])}m']

    # dedup preservando orden
    tokens: List[str] = []
    seen: set = set()
    for t in base_tokens:
        if t and t not in seen:
            seen.add(t); tokens.append(t)

    nots = [nrm(t) for t in (plan.get("not") or []) if t]
    family = plan.get("family")

    variants: List[Dict[str, Any]] = []
    seen_sets = set()

    def _push(tok_list: List[str]):
        key = tuple(tok_list)
        if key in seen_sets or not tok_list:
            return
        seen_sets.add(key)
        variants.append({"tokens": tok_list, "not": nots, "family": family})

    # Semillas
    for var in _variants_from_tokens(tokens):
        _push(var)
        if len(variants) >= target:
            return variants[:target]

    # Sliding windows + drop-1 hasta llegar al target (sin combinatoria explosiva)
    n = len(tokens)
    if n >= 4:
        for i in range(0, n-1):
            _push(tokens[i:i+2]); 
            if len(variants) >= target: return variants[:target]
        for i in range(0, n-2):
            _push(tokens[i:i+3]); 
            if len(variants) >= target: return variants[:target]
    if n >= 2:
        for i in range(n):
            t2 = tokens[:i] + tokens[i+1:]
            _push(t2)
            if len(variants) >= target: return variants[:target]

    return variants[:target]

# Stub de hidratación Odoo (opcional)
def hydrate_in_odoo(candidates: List[Dict[str, Any]], odoo_cfg: Dict[str,str]|None):
    return candidates
