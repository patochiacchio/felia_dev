from __future__ import annotations
import os, re
from typing import List, Optional, Dict, Any

from fastapi import FastAPI
from pydantic import BaseModel, Field, ConfigDict, AliasChoices
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from whatsapp_adapter import app as wa_app
app = FastAPI()
app.mount("/", wa_app)
load_dotenv(override=False)

from .assistant_qa import maybe_answer_felia_question
from .llm import plan_next_step
from .normalizer import normalize_user_text
from .search import LocalCatalog, build_query_variants, hydrate_in_odoo
from .ranker import rank_and_cut, pretty_list
from .mock_products import generate_mock_products

# ========================
# Config
# ========================
class Settings(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    openai_api_key: str = Field(default=os.getenv("OPENAI_API_KEY", ""))
    catalog_path: str = Field(default=os.getenv("CATALOG_PATH", "./data/catalog.csv"))
    product_source: str = Field(default=os.getenv("PRODUCT_SOURCE", "mock"))  # "mock" | "local"
    odoo_url: Optional[str] = Field(default=os.getenv("ODOO_URL"))
    odoo_db: Optional[str] = Field(default=os.getenv("ODOO_DB"))
    odoo_user: Optional[str] = Field(default=os.getenv("ODOO_USER"))
    odoo_pass: Optional[str] = Field(default=os.getenv("ODOO_PASS"))
    show_prices: bool = Field(default=True)
    currency: str = Field(default="AR$")

SETTINGS = Settings()

# ========================
# Session
# ========================
class SessionState(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    greeted: bool = False
    asked_questions: List[str] = []
    answered_slots: Dict[str, str] = {}
    last_user_need: Optional[str] = None
    need_history: List[str] = []
    rounds: int = 0
    ask_streak: int = 0
    pending_question: Optional[str] = None
    force_more: bool = False

    # Memoria para pivoteos (las usa GPT)
    rejected_families: List[str] = []
    rejected_options: List[str] = []
    last_question_options: List[str] = []

SESSIONS: Dict[str, SessionState] = {}

# ========================
# FastAPI
# ========================
app = FastAPI(title="Felia Orchestrator", version="5.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

CATALOG = LocalCatalog(SETTINGS.catalog_path)

# ========================
# I/O
# ========================
class ChatIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=(), populate_by_name=True, extra="ignore")
    session: str = Field(validation_alias=AliasChoices("session", "session_id"))
    text: str = Field(validation_alias=AliasChoices("text", "message"))

class ChatOut(BaseModel):
    reply: str
    trace: Dict[str, Any] = {}

# ========================
# Helpers
# ========================
_OPTS_RE = re.compile(r"\(([^)]{0,300})\)")
_NOSE_CLEAN = re.compile(r'\s*\|\s*no\s*s[ée]\s*', re.IGNORECASE)
_NOSE_CLEAN2 = re.compile(r'no\s*s[ée]\s*\|\s*', re.IGNORECASE)
_NEG_RE = re.compile(r'\b(no necesito|no es|no son|otra cosa|otro|ninguno|ninguna)\b', re.I)

def _strip_no_se(q: str) -> str:
    q2 = _NOSE_CLEAN.sub('', q)
    q2 = _NOSE_CLEAN2.sub('', q2)
    q2 = re.sub(r'\(\s*\)', '', q2)
    return q2.strip()

def get_state(session: str) -> SessionState:
    if session not in SESSIONS:
        SESSIONS[session] = SessionState()
    return SESSIONS[session]

def _extract_options(q: str) -> List[str]:
    m = _OPTS_RE.search(q or "")
    if not m:
        return []
    raw = [o.strip() for o in m.group(1).split("|")]
    return [o for o in raw if o]

def _update_rejections_from_user(user_text: str, state: SessionState) -> None:
    """Si dice 'no/otra cosa/no es', marcamos opciones previas como rechazadas."""
    if not state.pending_question:
        return
    if not _NEG_RE.search(user_text or ""):
        return
    opts = _extract_options(state.pending_question)
    for o in opts:
        if o not in state.rejected_options:
            state.rejected_options.append(o)

def _facts_score(step: Dict[str, Any]) -> int:
    score = 0
    intent = step.get("intent") or {}
    if intent.get("family"):
        score += 1
    units = step.get("units") or {}
    if len(units) > 0:
        score += 1
    score += len((step.get("answered_slots") or {}))
    return score

def _force_concrete_question(user_text: str, state: SessionState, base_step: Dict[str, Any]) -> str:
    """
    Hace un segundo pase a GPT con force_more=true para que
    devuelva una pregunta **concreta** (sin 'qué dato definimos ahora').
    Si aún así no llega, arma una pregunta específica a partir de slots_required.
    """
    step2 = plan_next_step(
        user_text=user_text,
        state={
            "greeted": state.greeted,
            "asked_questions": state.asked_questions,
            "answered_slots": state.answered_slots,
            "rounds": state.rounds,
            "need_history": state.need_history,
            "force_more": True,  # <- clave
            "pending_question": state.pending_question or "",
            "rejected_families": state.rejected_families,
            "rejected_options": state.rejected_options,
            "last_question_options": state.last_question_options,
        }
    )
    q = (step2.get("question") or step2.get("disambiguation") or "").strip()
    q = _strip_no_se(q) if q else q
    if q:
        return q

    # fallback: si GPT no devolvió, usamos el primer slot requerido
    slot = None
    if isinstance(base_step.get("slots_required"), list) and base_step["slots_required"]:
        slot = str(base_step["slots_required"][0]).lower().strip()
    if not slot:
        slot = "medida"
    return f"Necesito {slot} para avanzar. ¿Cuál es? (dame una opción concreta)"

# ========================
# Endpoint
# ========================
@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    state = get_state(body.session)
    user_text = normalize_user_text(body.text)
    state.last_user_need = user_text
    state.need_history.append(user_text)
    if len(state.need_history) > 8:
        state.need_history = state.need_history[-8:]

    # Saludo
    if not state.greeted:
        state.greeted = True
        return ChatOut(reply="Hola, soy Felia, asistente de Felemax. ¿En qué puedo ayudarte hoy?",
                       trace={"note": "greeting_only"})

    # Memorizar rechazos genéricos
    _update_rejections_from_user(user_text, state)

    # Router Q&A (pregunta real vs afirmación / respuesta de opción)
    qa = maybe_answer_felia_question(
        user_text=user_text,
        state={
            "greeted": state.greeted,
            "asked_questions": state.asked_questions,
            "need_history": state.need_history,
            "pending_question": state.pending_question or "",
        }
    )

    # 1) Q&A real ⇒ responder breve + retomar pregunta pendiente
    if qa.get("is_qa") and qa.get("kind") == "qa":
        ans = (qa.get("answer") or "").strip()
        if state.pending_question:
            reply = f"{ans}\n\n{state.pending_question}" if ans else state.pending_question
        else:
            reply = ans or "¿Podés contarme un poco más del uso?"
        return ChatOut(reply=reply, trace={"mode": "qa", "qa_confidence": qa.get("confidence", 0.0)})

    # 2) answer_option / statement_need / other ⇒ seguimos con el plan principal (GPT)
    step = plan_next_step(
        user_text=user_text,
        state={
            "greeted": state.greeted,
            "asked_questions": state.asked_questions,
            "answered_slots": state.answered_slots,
            "rounds": state.rounds,
            "need_history": state.need_history,
            "force_more": state.force_more,
            "pending_question": state.pending_question or "",
            "rejected_families": state.rejected_families,
            "rejected_options": state.rejected_options,
            "last_question_options": state.last_question_options,
        }
    )

    # Si GPT pide preguntar
    if step.get("action") == "ask":
        q = (step.get("question") or step.get("disambiguation") or "").strip()
        q = _strip_no_se(q) if q else q
        if not q or q in state.asked_questions:
            # Forzar una concreta (sin genéricas)
            q = _force_concrete_question(user_text, state, step)

        if q not in state.asked_questions:
            state.asked_questions.append(q)
        state.last_question_options = _extract_options(q)
        state.rounds += 1
        state.ask_streak += 1
        state.pending_question = q
        return ChatOut(reply=q, trace={"mode": "ask", "hypotheses": step.get("hypotheses", []), "intent": step.get("intent", {})})

    # Si GPT dice buscar pero con evidencia baja, pedimos UNA concreta (sin genéricas)
    if step.get("action") == "search" and (_facts_score(step) < 3):
        q = _force_concrete_question(user_text, state, step)
        if q not in state.asked_questions:
            state.asked_questions.append(q)
        state.last_question_options = _extract_options(q)
        state.rounds += 1
        state.ask_streak += 1
        state.pending_question = q
        return ChatOut(reply=q, trace={"mode": "ask_forced", "intent": step.get("intent", {})})

    # ================= BUSCAR =================
    not_tokens = step.get("not") or []
    family = (step.get("intent") or {}).get("family")
    goal = int(step.get("variants_goal") or 25)

    variants = []
    for toks in (step.get("query_variants") or []):
        if isinstance(toks, list) and toks:
            variants.append({"tokens": toks, "not": not_tokens, "family": family})

    if not variants:
        plan = {
            "q": " ".join(state.need_history[-4:]) or user_text,
            "must": step.get("must", []),
            "not": not_tokens,
            "units": step.get("units", {}),
            "family": family,
        }
        variants = build_query_variants(plan, target=goal)

    if SETTINGS.product_source.lower() == "mock":
        items = generate_mock_products(
            plan={"q": " ".join(state.need_history[-4:]) or user_text,
                  "units": step.get("units", {}),
                  "family": family},
            context_text=" ".join(state.need_history[-4:]),
            target=4
        )
        msg = pretty_list(items, show_prices=SETTINGS.show_prices, currency=SETTINGS.currency)
        msg += "\n¿Te lo reservo/te lo envío o preferís retirar por sucursal?"

        # reset de turno
        state.rounds = 0
        state.ask_streak = 0
        state.asked_questions = []
        state.answered_slots = {}
        state.need_history = []
        state.pending_question = None
        state.force_more = False
        state.rejected_families = []
        state.rejected_options = []
        state.last_question_options = []
        return ChatOut(reply=msg, trace={"mode": "mock", "variants_used": len(variants), "intent": step.get("intent", {})})

    # LOCAL
    candidates: List[Dict[str, Any]] = []
    for vq in variants:
        hits = CATALOG.search(vq)
        if hits:
            candidates.extend(hits)
        if len(candidates) >= 200:
            break

    if not candidates:
        # En vez de “¿qué preferís definir?”, forzamos una concreta
        q = _force_concrete_question(user_text, state, step)
        if q not in state.asked_questions:
            state.asked_questions.append(q)
        state.last_question_options = _extract_options(q)
        state.rounds += 1
        state.ask_streak += 1
        state.pending_question = q
        return ChatOut(reply=q, trace={"mode": "local_no_results_ask", "intent": step.get("intent", {})})

    hydrated = hydrate_in_odoo(
        candidates=candidates,
        odoo_cfg=dict(url=SETTINGS.odoo_url, db=SETTINGS.odoo_db, user=SETTINGS.odoo_user, password=SETTINGS.odoo_pass)
    )

    top_items = rank_and_cut(hydrated or candidates, must_tokens=step.get("must", []), not_tokens=not_tokens)
    if not top_items:
        q = _force_concrete_question(user_text, state, step)
        if q not in state.asked_questions:
            state.asked_questions.append(q)
        state.last_question_options = _extract_options(q)
        state.rounds += 1
        state.ask_streak += 1
        state.pending_question = q
        return ChatOut(reply=q, trace={"mode": "local_ambiguous_ask", "intent": step.get("intent", {})})

    msg = pretty_list(top_items, show_prices=SETTINGS.show_prices, currency=SETTINGS.currency)
    msg += "\n¿Te lo reservo/te lo envío o preferís retirar por sucursal?"

    # reset para próxima consulta
    state.rounds = 0
    state.ask_streak = 0
    state.asked_questions = []
    state.answered_slots = {}
    state.need_history = []
    state.pending_question = None
    state.force_more = False
    state.rejected_families = []
    state.rejected_options = []
    state.last_question_options = []

    return ChatOut(reply=msg, trace={"mode": "local_ok", "variants_used": len(variants), "intent": step.get("intent", {})})
