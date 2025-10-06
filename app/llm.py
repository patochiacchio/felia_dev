from __future__ import annotations
import os, json, re
from typing import Dict, Any, List

from pydantic import BaseModel, Field, ConfigDict
from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, RateLimitError, BadRequestError

load_dotenv(override=False)

SYSTEM_PROMPT = """Eres FELIA, asistente de Felemax (ferretería).
Tu trabajo es decidir **TODO**: interpretar la intención, generar hipótesis, confirmar con UNA pregunta
de desambiguación si hace falta, pedir atributos críticos y, cuando estés seguro, pasar a búsqueda.
Devuelve **solo JSON** con el formato indicado.

PRINCIPIOS
- Conversación real: adaptate al *lenguaje del cliente* (“el cosito que va con el durlok”), sin depender de palabras exactas.
- Si el cliente rechaza tu propuesta (“no”, “otra cosa”, “no es eso”), **pivotá**: proponé nuevas hipótesis (no repitas lo rechazado).
- UNA pregunta por turno, con **opciones concretas** (3–5) entre paréntesis separadas por “ | ”. **Nunca** incluyas “no sé”.
- Pedí primero atributos **críticos** para identificar la familia y variante; **cantidad** va al final.
- Cuando vos estés **seguro** (familia + ≥2 atributos), marcá `ready_to_search=true` y sugerí `query_variants`.

MAPPING DE FRASES COTIDIANAS A SLOTS (no listes sinónimos fijos; deducí por contexto)
- Si el usuario dice “me lo llevo siempre”, “lo uso en obra”, “subo/bajo escaleras”, “para el auto”, etc.,
  registrá `answered_slots.portabilidad` (p.ej., "alta", "obra", "vehículo", "móvil") y **no repitas “ubicación”**.
- Si menciona “placas/tabiques/durlock”, priorizá **familias estructurales/soporte** (perfiles montantes/soleras/omega);
  si después aclara, pivotás.
- Si contesta vago (“para trabajar”, “para la casa”), **no** repreguntes la misma genérica: inferí el slot más probable
  (uso, portabilidad, entorno) y seguí con el **siguiente crítico**.

FAMILIAS CON ORDEN DE SLOTS RECOMENDADO
- `taladro`:
  1) **tipo** (percutor | atornillador | banco | otro),
  2) **fuente** (inalámbrico | con cable),
  3) **tensión de batería** (12V | 18V | 20V | 24V) **o** **potencia en W** (600W | 800W | 1000W | 1200W),
  4) **mandril/diámetro de broca** (10mm | 13mm | etc.),
  5) **material a perforar** (madera | metal | concreto | otro),
  (cantidad al final).
- **Conexiones de termofusión** (codos/tee/reducción/uniones):
  **ANTES DE BUSCAR** definí:
  - **diámetro** (mm),
  - **ángulo** si aplica (45° | 90°) — p.ej. codos,
  - **material** (PVC | CPVC | PPR | PEAD | otro),
  - **servicio/clase/PN** o **fluido** (agua | gas | PN16 | PN20 | PN25 | otro).
  Recién luego buscar.

OPCIONES
- Si el cliente ya dio un número/unidad, proponé opciones **alrededor** (±20–30%) con la **misma unidad**.
- Si no, proponé una **escalera numérica razonable** (3–5 valores) de esa unidad.
- Si es categoría, opciones claras y mutuamente excluyentes.

BÚSQUEDA
- `ready_to_search=true` solo si hay **familia (≥0.6)** y al menos **dos** atributos adicionales definidos.
- Si la familia posee variantes por **forma/tipo/ángulo** (perfiles C/U/Ω, codos 45°/90°, etc.), ese slot es **crítico** y
  debería definirse antes de buscar.
- Sugerí `query_variants` como listas de tokens que reflejen lo decidido (sin marcas ni sinónimos inventados).
- Completá `must`/`not` si corresponde.

EVITAR BUCLES / PREGUNTAS GENÉRICAS
- **Nunca** generes preguntas genéricas tipo “¿Qué dato definimos ahora?” o “¿Qué preferís definir?”.
- **Elegí vos** el **siguiente slot más crítico** y hacé una **pregunta concreta** con 3–5 opciones.
- No repitas exactamente una pregunta que ya esté en `state.asked_questions`.

FLAG DEL ORQUESTADOR
- Si `state.force_more` es `true`, **devolvé** `{"action":"ask", "question": "...con opciones..."}` para el slot
  **más crítico que falte** (no devuelvas `search` en ese caso).

SALIDA JSON EXACTA:
{
  "action": "ask" | "search",
  "question": str | null,
  "intent": { "family": str|null, "family_confidence": float },
  "ready_to_search": boolean,
  "slots_required": [str, ...],
  "answered_slots": { "slot_key": "valor" },
  "variants_goal": 25 | 30 | 40,
  "query_variants": [[tok, tok2, ...], ...],
  "must": [str, ...],
  "not": [str, ...],
  "units": { "mm": "6", "in": "1", "m": "6", "w": "500" },
  "hypotheses": [str, ...],
  "disambiguation": str|null
}
"""

class LLMConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    api_key: str = Field(default=os.getenv("OPENAI_API_KEY", ""))
    model: str = Field(default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

_client: OpenAI | None = None

def _client_ok() -> OpenAI | None:
    global _client
    if _client is None:
        cfg = LLMConfig()
        if not cfg.api_key:
            return None
        _client = OpenAI(api_key=cfg.api_key)
    return _client

# --- extractores de unidades (agnósticos de rubro) ---
_MM = re.compile(r'(\d+)\s*mm\b', re.I)
_IN_FRAC = re.compile(r'(\d+\s*/\s*\d+)\s*(?:\"|pulg|in)\b', re.I)
_IN_WHO  = re.compile(r'\b(\d+)\"', re.I)
_M      = re.compile(r'(\d+)\s*(?:m|metros)\b', re.I)
_W      = re.compile(r'(\d{2,4})\s*w\b', re.I)

def _units_from_text(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    mm = _MM.findall(text or "")
    if mm: out["mm"] = mm[-1]
    inf = _IN_FRAC.findall(text or "")
    if inf: out["in"] = inf[-1].replace(" ", "")
    inw = _IN_WHO.findall(text or "")
    if inw and "in" not in out: out["in"] = inw[-1]
    m = _M.findall(text or "")
    if m: out["m"] = m[-1]
    w = _W.findall(text or "")
    if w: out["w"] = w[-1]
    return out

def _fallback_minimal(user_text: str, state: Dict[str, Any]) -> Dict[str, Any]:
    # fallback ultra conservador (rara vez usado)
    asked = set(state.get("asked_questions") or [])
    q = "Contame el dato clave que falta (por ejemplo, medida o material)."
    if q in asked:
        q = "Dame un dato concreto (medida en mm, material, ángulo, presión/clase, etc.)."
    return {
        "action": "ask",
        "question": q,
        "intent": {"family": None, "family_confidence": 0.0},
        "ready_to_search": False,
        "slots_required": [],
        "answered_slots": {},
        "variants_goal": 25,
        "query_variants": [],
        "must": [],
        "not": [],
        "units": _units_from_text(user_text),
        "hypotheses": [],
        "disambiguation": None,
    }

def plan_next_step(user_text: str, state: Dict[str, Any]) -> Dict[str, Any]:
    client = _client_ok()
    if client is None:
        return _fallback_minimal(user_text, state)

    try:
        resp = client.chat.completions.create(
            model=LLMConfig().model,
            temperature=0.6,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",
                 "content": (
                     "Decide el próximo paso respetando las reglas.\n"
                     f"state={json.dumps(state, ensure_ascii=False)}\n"
                     f"user='{user_text}'\n"
                     "Devuelve SOLO el JSON con el formato indicado."
                 )}
            ]
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
    except (APIConnectionError, RateLimitError, BadRequestError, ValueError, json.JSONDecodeError):
        data = _fallback_minimal(user_text, state)

    # Sanitizado
    asked = set(state.get("asked_questions") or [])
    q = data.get("question")
    if not isinstance(q, str) or not q.strip() or q in asked:
        data["question"] = None
    else:
        data["question"] = re.sub(r'\s*\|\s*no\s*s[ée]\s*', '', data["question"], flags=re.IGNORECASE)
        data["question"] = re.sub(r'no\s*s[ée]\s*\|\s*', '', data["question"], flags=re.IGNORECASE)
        data["question"] = re.sub(r'\(\s*\)', '', data["question"]).strip()

    # Normalizaciones y defaults
    def _keep_strs(lst):
        return [x for x in (lst or []) if isinstance(x, str) and x.strip()]

    data["hypotheses"] = _keep_strs(data.get("hypotheses"))
    data["must"] = _keep_strs(data.get("must"))
    data["not"]  = _keep_strs(data.get("not"))
    qvars = []
    for v in (data.get("query_variants") or []):
        if isinstance(v, list):
            toks = [str(t).strip() for t in v if str(t).strip()]
            if toks:
                qvars.append(toks)
    data["query_variants"] = qvars

    data.setdefault("intent", {"family": None, "family_confidence": 0.0})
    data.setdefault("units", _units_from_text(user_text))
    data.setdefault("slots_required", [])
    data.setdefault("answered_slots", {})
    data.setdefault("action", "ask")
    data.setdefault("ready_to_search", False)
    data.setdefault("variants_goal", 25)
    if "disambiguation" not in data:
        data["disambiguation"] = None

    if data["action"] == "ask" and not data["question"]:
        if isinstance(data.get("disambiguation"), str) and data["disambiguation"].strip():
            data["question"] = data["disambiguation"].strip()
        else:
            # evita genéricas; pedí algo concreto
            data["question"] = "Necesito un dato concreto para avanzar (por ejemplo: medida en mm, material o ángulo)."

    goal = int(data.get("variants_goal") or 25)
    data["variants_goal"] = 40 if goal >= 40 else 30 if goal >= 30 else 25

    return data
