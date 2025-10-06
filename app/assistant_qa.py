from __future__ import annotations
import os, json, re, unicodedata
from typing import Dict, Any, Optional, List

from pydantic import BaseModel, Field, ConfigDict
from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, RateLimitError, BadRequestError

load_dotenv(override=False)

SYSTEM_PROMPT_QA = """Eres FELIA (módulo Router+Q&A) de una ferretería llamada Felemax.

TAREA
1) CLASIFICAR el último mensaje del usuario en una de estas categorías:
   - "answer_option": eligió/indicó una opción de la última pregunta (incluye "otro/otra cosa").
   - "qa": hizo una **pregunta real** de explicación/recomendación (lleva "¿ ?" o un interrogativo explícito:
     qué/cuál/cómo/cuándo/dónde/por qué/para qué, o frases como "¿qué potencia...?", "¿cuál me conviene...?",
     "¿me explicas la diferencia...?", "¿sirve para...?", etc.).
   - "statement_need": es una **afirmación/imperativo** que expresa necesidad o instrucción (ej.: "quiero...",
     "necesito...", "busco...", "dame opciones", "mostrame", "pasame", "me sirve", "estoy buscando..."), **sin pregunta**.
   - "smalltalk": saludo, cortesía o charla sin intención ferretera.
   - "other": otro tipo de mensaje.

2) SI y SOLO SI la categoría es "qa", responder **breve** (2–4 líneas como máximo) a lo preguntado.
   - Si dice "explicame las diferencias", da 2–5 viñetas cortas.
   - No inventes stock/precios/sucursales. No cierres con preguntas (el orquestador retomará).
   - Usa la pregunta pendiente (pending_question) como referencia para “eso/esto”.

REGLAS:
- NO etiquetes como "qa" si el mensaje es imperativo/afirmativo sin signos de pregunta (p.ej. “dame opciones”,
  “mostrame modelos”, “necesito un taladro”).
- NO etiquetes como "qa" si parece respuesta directa a las opciones vigentes.
- Mantén la respuesta concisa; el orquestador hará la siguiente pregunta.

SALIDA JSON EXACTA:
{
  "kind": "qa" | "answer_option" | "statement_need" | "smalltalk" | "other",
  "is_qa": boolean,            // true solo si kind == "qa"
  "answer": str|null,          // texto breve si is_qa=true
  "confidence": float          // 0..1
}
"""

class QAConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    api_key: str = Field(default=os.getenv("OPENAI_API_KEY", ""))
    model: str = Field(default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

_client: Optional[OpenAI] = None

def _client_ok() -> Optional[OpenAI]:
    global _client
    if _client is None:
        cfg = QAConfig()
        if not cfg.api_key:
            return None
        _client = OpenAI(api_key=cfg.api_key)
    return _client

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s)

_OPTS_RE = re.compile(r"\(([^)]{0,300})\)")

def _extract_options(pending_question: str) -> List[str]:
    m = _OPTS_RE.search(pending_question or "")
    if not m:
        return []
    raw = [o.strip() for o in m.group(1).split("|")]
    return [o for o in raw if o]

def _looks_like_answer_to_option(user_text: str, pending_question: str) -> bool:
    """Heurística local barata: si el texto coincide con una opción o dice 'otro/otra cosa'."""
    ut = _norm(user_text)
    if not ut:
        return False
    opts = [ _norm(o) for o in _extract_options(pending_question) ]
    if not opts:
        return False
    if ut in ("otro", "otra cosa", "ninguno", "ninguna"):
        return True
    for on in opts:
        if ut == on or ut in on or on in ut:
            return True
    return False

def maybe_answer_felia_question(user_text: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Devuelve:
      {
        "is_qa": bool,
        "kind": "qa" | "answer_option" | "statement_need" | "smalltalk" | "other",
        "answer": str,
        "confidence": float
      }
    """
    s = (user_text or "").strip()
    pending_q = state.get("pending_question") or ""

    # atajo: si coincide con una opción de la pregunta pendiente ⇒ no es Q&A
    if _looks_like_answer_to_option(s, pending_q):
        return {"is_qa": False, "kind": "answer_option", "answer": "", "confidence": 0.9}

    client = _client_ok()
    if client is None:
        return {"is_qa": False, "kind": "other", "answer": "", "confidence": 0.0}

    payload = {
        "greeted": state.get("greeted", False),
        "pending_question": pending_q,
        "asked_questions": state.get("asked_questions") or [],
        "need_history": state.get("need_history") or [],
    }

    try:
        resp = client.chat.completions.create(
            model=QAConfig().model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_QA},
                {
                    "role": "user",
                    "content": (
                        "Clasifica y, si corresponde, responde breve.\n"
                        f"state={json.dumps(payload, ensure_ascii=False)}\n"
                        f"user='{s}'\n"
                        "Devuelve SOLO el JSON pedido."
                    ),
                },
            ],
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
    except (APIConnectionError, RateLimitError, BadRequestError, ValueError, json.JSONDecodeError):
        return {"is_qa": False, "kind": "other", "answer": "", "confidence": 0.0}

    # Normalización de salida
    if not isinstance(data, dict):
        return {"is_qa": False, "kind": "other", "answer": "", "confidence": 0.0}

    kind = data.get("kind") or ("qa" if data.get("is_qa") else "other")
    is_qa = bool(kind == "qa")
    ans = data.get("answer")
    ans = ans.strip() if isinstance(ans, str) else ""
    conf = float(data.get("confidence") or (0.8 if is_qa else 0.6))

    return {"is_qa": is_qa, "kind": kind, "answer": ans, "confidence": conf}
