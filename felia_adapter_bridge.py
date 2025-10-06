# felia_adapter_bridge.py
from __future__ import annotations
import os, importlib, inspect
from typing import Any, Callable, Dict

# [Opcional] fuerza una función exacta (sobrescribe todo lo demás)
FORCE_HANDLER: str | None = None  # ej: "app.main:handle_message"

# Nombres de funciones posibles en tu core
CANDIDATE_FUNC_NAMES = [
    "handle_message", "reply", "process_message",
    "process_input", "orchestrate", "main_handler",
]

# Módulos donde buscar (en orden)
CANDIDATE_MODULES = [
    os.getenv("FELIA_CORE_MODULE"),     # si lo seteás por env
    os.getenv("FELIA_CORE_HANDLER_PATH", "").split(":")[0] or None,  # si diste ruta exacta
    "app.main", "app.core", "app.orchestrator", "app",
    "felia_orchestrator", "felia.core", "felia",
]
CANDIDATE_MODULES = [m for m in CANDIDATE_MODULES if m]

# Sesión (estado) por usuario para la demo
_SESSIONS: Dict[str, Dict[str, Any]] = {}

def reset_session(user_id: str):
    _SESSIONS.pop(user_id, None)

def _import_by_path(path: str) -> Callable[..., Any]:
    if ":" not in path:
        raise RuntimeError("Usa 'modulo.submodulo:funcion'")
    mod_name, func_name = path.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, func_name)
    if not callable(fn):
        raise RuntimeError(f"{path} no es invocable")
    return fn

def _discover_handler() -> Callable[..., Any]:
    # 1) Forzado exacto
    env_force = os.getenv("FELIA_CORE_HANDLER_PATH")
    if FORCE_HANDLER:
        return _import_by_path(FORCE_HANDLER)
    if env_force:
        return _import_by_path(env_force)

    # 2) Buscar en módulos candidatos
    for mod_name in CANDIDATE_MODULES:
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        for name in CANDIDATE_FUNC_NAMES:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn

    raise RuntimeError(
        "No encontré un handler en tu core. Seteá FORCE_HANDLER o FELIA_CORE_HANDLER_PATH "
        f"o exportá una función con alguno de: {', '.join(CANDIDATE_FUNC_NAMES)}"
    )

_core_handler = _discover_handler()
_core_sig = inspect.signature(_core_handler)

def _state_for(user_id: str) -> Dict[str, Any]:
    if user_id not in _SESSIONS:
        _SESSIONS[user_id] = {}
    return _SESSIONS[user_id]

def handle_message(user_id: str, text: str):
    """
    Adapta a firmas típicas:
      1) f(user_id, state, text)
      2) f(user_id, text)
      3) f(state, text)
      4) f(text)
    """
    params = list(_core_sig.parameters.keys())

    if len(params) >= 3:
        try:
            return _core_handler(user_id, _state_for(user_id), text)
        except TypeError:
            pass

    if len(params) >= 2:
        try:
            return _core_handler(user_id, text)
        except TypeError:
            pass

    if len(params) >= 2:
        try:
            return _core_handler(_state_for(user_id), text)
        except TypeError:
            pass

    try:
        return _core_handler(text)
    except TypeError as e:
        raise RuntimeError(
            f"No pude adaptar la llamada; firma detectada: {_core_sig}. Error: {e}\n"
            "Soluciones: fijá FORCE_HANDLER o FELIA_CORE_HANDLER_PATH a una función con firma estable."
        )
