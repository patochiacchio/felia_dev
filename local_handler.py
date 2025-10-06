# local_handler.py  — SAFE MODE (demo estable)
from __future__ import annotations
import os, importlib, inspect, logging
from typing import Any, Dict, Callable

log = logging.getLogger("local_handler")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

# Si más adelante querés enchufar TU core real, seteá LOCAL_HANDLER_TARGET=mod.submod:func
TARGET = os.getenv("LOCAL_HANDLER_TARGET", "").strip()

# Estado mínimo por usuario (para demo)
_SESS: Dict[str, Dict[str, Any]] = {}

def _state(u: str) -> Dict[str, Any]:
    if u not in _SESS:
        _SESS[u] = {
            "greeted": False,
            "asked_questions": [],
            "answered_slots": {},
            "rounds": 0,
            "need_history": [],
            "pending_question": None,
            "force_more": False,
            "rejected_families": [],
            "rejected_options": [],
            "last_question_options": [],
        }
    return _SESS[u]

# ----------------- (opcional) enchufo core real si me das TARGET) -----------------
def _import_by_path(path: str) -> Callable[..., Any]:
    if ":" not in path:
        raise RuntimeError("LOCAL_HANDLER_TARGET debe ser 'mod.submod:func'")
    mod_name, func_name = path.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, func_name)
    if not callable(fn):
        raise RuntimeError(f"{path} no es invocable")
    return fn

_core_fn: Callable[..., Any] | None = None
_core_sig: inspect.Signature | None = None

def _try_core():
    global _core_fn, _core_sig
    if _core_fn is not None:
        return True
    if not TARGET:
        return False
    try:
        fn = _import_by_path(TARGET)
        _core_fn = fn
        _core_sig = inspect.signature(fn)
        log.info("Core real conectado via LOCAL_HANDLER_TARGET = %s (firma %s)", TARGET, _core_sig)
        return True
    except Exception as e:
        log.warning("No pude importar el core real (%s). Sigo en modo demo. Detalle: %s", TARGET, e)
        return False

def _call_core_flexible(user_id: str, text: str, st: Dict[str, Any]):
    """
    Si configuraste LOCAL_HANDLER_TARGET, adaptamos firma:
      1) f(user_id, state, text) 2) f(user_id, text) 3) f(state, text) 4) f(text)
    """
    fn, sig = _core_fn, _core_sig
    params = list(sig.parameters.keys())
    # 1
    if len(params) >= 3:
        try:
            return fn(user_id, st, text)
        except TypeError:
            pass
    # 2
    if len(params) >= 2:
        try:
            return fn(user_id, text)
        except TypeError:
            pass
    # 3
    if len(params) >= 2:
        try:
            return fn(st, text)
        except TypeError:
            pass
    # 4
    return fn(text)

# ----------------- demo orquestada con llm.plan_next_step -----------------
def _demo_step(user_id: str, text: str) -> str:
    st = _state(user_id)
    if not st["greeted"]:
        st["greeted"] = True
        return "Hola, soy Felia 👋 ¿En qué te ayudo?"

    # plan con LLM si tenés OPENAI_API_KEY, si no usa fallback interno
    try:
        from llm import plan_next_step  # mismo repo
    except Exception:
        # ultra fallback: eco amable
        return "Contame qué necesitás (medida, material, uso) y te guío 😉"

    step = plan_next_step(text, {
        "greeted": st["greeted"],
        "asked_questions": st["asked_questions"],
        "answered_slots": st["answered_slots"],
        "rounds": st["rounds"],
        "need_history": st["need_history"],
        "force_more": st["force_more"],
        "pending_question": st["pending_question"] or "",
        "rejected_families": st["rejected_families"],
        "rejected_options": st["rejected_options"],
        "last_question_options": st["last_question_options"],
    })

    # solo modo "ask" para demo rápida (sin catálogos), limpio la pregunta
    q = (step.get("question") or step.get("disambiguation") or "").strip()
    q = q or "Necesito un dato concreto para avanzar (por ejemplo: medida en mm o material)."
    if q not in st["asked_questions"]:
        st["asked_questions"].append(q)
    st["pending_question"] = q
    st["need_history"].append(text)
    if len(st["need_history"]) > 8:
        st["need_history"] = st["need_history"][-8:]
    st["rounds"] += 1
    return q

# ----------------- entrypoint que usa el adapter/bridge -----------------
def handle_message(user_id: str, text: str):
    """
    1) Si configuraste LOCAL_HANDLER_TARGET, intentamos llamar a TU core real (con adaptación de firma).
    2) Si falla o no está configurado, respondemos en 'modo demo' estable sin excepciones.
    """
    try:
        if _try_core():
            try:
                return _call_core_flexible(user_id, text, _state(user_id))
            except Exception as e:
                log.warning("Tu core real tiró excepción (%s). Sigo en modo demo.", e)
        # demo estable
        return _demo_step(user_id, text)
    except Exception as e:
        log.exception("Fallo inesperado en local_handler: %s", e)
        return "Estoy lista, contame tu necesidad (medida/material/uso) y te guío."
