# app/whatsapp_bridge_handler.py
from __future__ import annotations

def _get_core():
    """
    Import tardío para evitar el import circular:
    whatsapp_adapter -> este archivo -> (recién acá) app.main
    """
    from .main import ChatIn, chat  # tu lógica real de la demo por terminal
    try:
        from .main import SESSIONS   # dict de estado por sesión, si existe
    except Exception:
        SESSIONS = {}
    return ChatIn, chat, SESSIONS

def handle_message(user_id: str, text: str):
    """
    Reproduce EXACTAMENTE el flujo de la terminal:
      ChatIn(session=<wa_id>, text=<mensaje>) -> chat(...) -> ChatOut.reply
    """
    ChatIn, chat, _ = _get_core()
    ci = ChatIn(session=user_id, text=text)
    co = chat(ci)  # debe devolver ChatOut
    try:
        return co.reply
    except Exception:
        # por las dudas, devuelve algo legible si no es ChatOut
        return str(co)

def reset_session(user_id: str):
    """
    Limpia el estado guardado por tu core para esa sesión (para el comando 'reset').
    """
    _, _, SESSIONS = _get_core()
    try:
        SESSIONS.pop(user_id, None)
    except Exception:
        pass
