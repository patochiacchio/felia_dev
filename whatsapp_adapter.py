# whatsapp_adapter.py
from __future__ import annotations
import os, re, json, time, importlib, logging
from typing import Callable, Iterable, List, Optional, Tuple, Union

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv(override=False)

WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN")                  # ej: felia-dev-token
WA_ACCESS_TOKEN = os.getenv("WA_ACCESS_TOKEN")                  # tu token de Meta
WA_PHONE_ID     = os.getenv("WA_DEFAULT_PHONE_ID")              # ej: 874624205724101
FELIA_HANDLER_PATH = os.getenv("FELIA_HANDLER", "felia_adapter_bridge:handle_message")
FELIA_RESET_HANDLER_PATH = os.getenv("FELIA_RESET_HANDLER")     # opcional: mod:func

def _require_env():
    missing = [k for k, v in {
        "WA_VERIFY_TOKEN": WA_VERIFY_TOKEN,
        "WA_ACCESS_TOKEN": WA_ACCESS_TOKEN,
        "WA_DEFAULT_PHONE_ID": WA_PHONE_ID,
        "FELIA_HANDLER": FELIA_HANDLER_PATH,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Faltan variables de entorno: {', '.join(missing)}")
_require_env()

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
log = logging.getLogger("whatsapp_adapter")

# ------------------------------------------------------------------------------
# Import dinámico (handler y reset)
# ------------------------------------------------------------------------------
HandlerReturn = Union[str, dict, List[str], Iterable[str]]

def _import_handler(path: str) -> Callable[[str, str], HandlerReturn]:
    if ":" not in path:
        raise RuntimeError("FELIA_HANDLER debe ser 'modulo.submodulo:funcion'")
    module_name, func_name = path.split(":", 1)
    mod = importlib.import_module(module_name)
    fn = getattr(mod, func_name)
    if not callable(fn):
        raise RuntimeError("FELIA_HANDLER no es invocable")
    return fn

def _import_optional_callable(path: Optional[str]):
    if not path:
        return None
    try:
        if ":" not in path:
            log.warning("FELIA_RESET_HANDLER inválido (usa 'mod:func')")
            return None
        module_name, func_name = path.split(":", 1)
        mod = importlib.import_module(module_name)
        fn = getattr(mod, func_name, None)
        if callable(fn):
            return fn
        log.warning("Reset handler no invocable: %s", path)
    except Exception as e:
        log.warning("No se pudo importar FELIA_RESET_HANDLER '%s': %s", path, e)
    return None

handle_message = _import_handler(FELIA_HANDLER_PATH)
_reset_callable = _import_optional_callable(FELIA_RESET_HANDLER_PATH)

def reset_session(user_id: str) -> bool:
    """
    Limpia el estado de demo:
      1) Si existe FELIA_RESET_HANDLER=mod:func, lo llama
      2) Si existe felia_adapter_bridge.reset_session(user_id), lo llama
      3) Si nada existe, devuelve False (pero no rompe)
    """
    if _reset_callable:
        try:
            _reset_callable(user_id)
            return True
        except Exception as e:
            log.warning("Fallo reset custom: %s", e)
    try:
        bridge = importlib.import_module("felia_adapter_bridge")
        fn = getattr(bridge, "reset_session", None)
        if callable(fn):
            fn(user_id)
            return True
    except Exception:
        pass
    return False

# ------------------------------------------------------------------------------
# WhatsApp Cloud API
# ------------------------------------------------------------------------------
class WhatsAppClient:
    def __init__(self, access_token: str, phone_id: str) -> None:
        self.base_url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        })

    def send_text(self, to: str, text: str) -> Tuple[bool, dict]:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text[:4096]},
        }
        r = self.session.post(self.base_url, json=payload, timeout=20)
        ok = 200 <= r.status_code < 300
        try:
            data = r.json()
        except Exception:
            data = {"status_code": r.status_code, "text": r.text}
        if not ok:
            log.warning("Fallo al enviar a %s: %s %s", to, r.status_code, data)
        return ok, data

    def send_text_try_arg_variants(self, to_base: str, text: str) -> Tuple[bool, dict, List[str]]:
        tried: List[str] = []
        last = {}
        for cand in generate_argentina_variants(to_base):
            if cand in tried:
                continue
            tried.append(cand)
            ok, data = self.send_text(cand, text)
            last = data
            if ok:
                return True, data, tried
        return False, last, tried

# ------------------------------------------------------------------------------
# Números AR (variantes) — evita "doble 9", soporta "54 <area> 54 <numero>"
# y agrega forzados tipo 2941→2941 54 ...
# ------------------------------------------------------------------------------
ARG_CC = "54"

def only_digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")

def strip_leading_zeros(s: str) -> str:
    return re.sub(r"^0+", "", s or "")

def remove_15_after_area(n: str) -> str:
    # elimina "15" justo después del código de área (2-4 dígitos)
    m = re.match(r"^(\d{2,4})15(\d+)$", n or "")
    return f"{m.group(1)}{m.group(2)}" if m else (n or "")

def generate_argentina_variants(raw: str) -> List[str]:
    """
    Genera variantes E.164 para AR:
      - Si ya trae 549..., NO agrega otro 9.
      - Si trae 54..., prueba 54... y 549...
      - Si viene nacional (con/sin 0), arma 54... y 549...
      - Quita '15' post-área.
      - Caso raro: '54 <area> 54 <numero>' => también prueba quitando ese '54' intermedio.
      - Forzados: áreas en AR_FORCE_MID54_AREAS (por defecto '2941') → intenta '<area>54<resto>'
        cuando el local empieza con los 3 primeros dígitos de esa área.
        EJ: 5492944899918 → fuerza 54 2941 54 899918.
    """
    s = only_digits(raw)
    variants: List[str] = []

    def push(x: str):
        if x and x not in variants:
            variants.append(x)

    def add_pair(local: str):
        # local = <area><numero> (sin '54' país)
        if not local:
            return
        if local.startswith("9"):
            # Ya tiene el '9' de móviles → NO duplicar
            push(ARG_CC + local)        # 549...
            push(ARG_CC + local[1:])    # 54...
        else:
            push(ARG_CC + local)        # 54...
            push(ARG_CC + "9" + local)  # 549...

    # --- normalización base ---
    if s.startswith(ARG_CC):
        rest = s[len(ARG_CC):]
    else:
        rest = strip_leading_zeros(s)

    # local sin '9' líder
    local_no9 = rest[1:] if rest.startswith("9") else rest
    base_local = remove_15_after_area(local_no9)

    # --- forzados por env (por defecto 2941) ---
    # Nota: si el local comienza con los 3 primeros dígitos del área forzada,
    # generamos <area>54<resto> quitando 1 dígito tras esos 3 (asumiendo área de 4 dígitos),
    # que es lo que necesitás para 2941.
    import os as _os
    forced_areas = [only_digits(x) for x in (_os.getenv("AR_FORCE_MID54_AREAS", "2941").split(","))]
    for area in [a for a in forced_areas if 3 <= len(a) <= 4]:
        pref3 = area[:3]
        if base_local.startswith(pref3) and len(base_local) >= 4:
            # quitamos el 4º dígito del local y forzamos el área deseada + '54'
            forced_local = area + "54" + base_local[4:]
            add_pair(forced_local)  # genera 54<area>54... y 549<area>54...

    # --- pares normales ---
    add_pair(base_local)

    # --- caso raro: "54" incrustado después del área (2-4 dígitos)
    #   También cubrir si hay un '9' al inicio (ya lo removimos en base_local)
    for area_len in (2, 3, 4):
        if len(base_local) > area_len:
            mid = base_local[:area_len] + "54" + base_local[area_len:]
            add_pair(mid)

    return variants

# ------------------------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------------------------
app = FastAPI(title="Felia WhatsApp Adapter", version="1.2.0")
wa = WhatsAppClient(WA_ACCESS_TOKEN, WA_PHONE_ID)

@app.get("/health")
def health():
    return PlainTextResponse("ok")

# GET webhook: acepta /webhook y /whatsapp/webhook, con claves con/sin punto
@app.get("/webhook")
@app.get("/whatsapp/webhook")
async def verify_webhook(request: Request):
    qp = request.query_params
    mode = qp.get("hub.mode") or qp.get("hub_mode")
    verify_token = qp.get("hub.verify_token") or qp.get("hub_verify_token")
    challenge = qp.get("hub.challenge") or qp.get("hub_challenge") or ""
    if mode == "subscribe" and verify_token == WA_VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Token de verificación inválido")

# POST webhook: alias en ambos paths
@app.post("/webhook")
@app.post("/whatsapp/webhook")
async def webhook_post(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    log.debug("Webhook body: %s", json.dumps(body, ensure_ascii=False))

    changes = []
    try:
        changes = body.get("entry", [])[0].get("changes", [])
    except Exception:
        pass

    for change in changes:
        value = change.get("value", {}) or {}
        messages = value.get("messages", []) or []
        contacts = value.get("contacts", []) or []
        profile_name = None
        if contacts:
            profile_name = (contacts[0].get("profile") or {}).get("name")

        for msg in messages:
            wa_id = msg.get("from")  # E.164 sin '+'
            mtype = msg.get("type")
            text: Optional[str] = None

            if mtype == "text":
                text = (msg.get("text") or {}).get("body")
            elif mtype == "interactive":
                itype = (msg.get("interactive") or {}).get("type")
                if itype == "button_reply":
                    text = (msg["interactive"]["button_reply"] or {}).get("title")
                elif itype == "list_reply":
                    text = (msg["interactive"]["list_reply"] or {}).get("title")
            elif mtype == "button":
                text = (msg.get("button") or {}).get("text")

            if not text:
                text = f"[Tipo {mtype} recibido]"

            user_id = wa_id or "unknown"
            log.info("Mensaje de %s (%s): %s", profile_name, user_id, text)

            # RESET DEMO
            if text and text.strip().lower() == "reset":
                try:
                    done = reset_session(user_id)
                except Exception:
                    done = False
                wa.send_text_try_arg_variants(
                    user_id,
                    "Listo, reiniciamos la conversación. Arrancamos de cero. Contame qué necesitás."
                )
                log.info("Reset solicitado por %s → %s", user_id, "OK" if done else "sin handler")
                continue

            # Llamar al orquestador (tu lógica)
            try:
                result = handle_message(user_id, text)
            except Exception as e:
                log.exception("Error en handle_message: %s", e)
                wa.send_text_try_arg_variants(user_id, "Tuvimos un problema interno, ¿podés repetir tu consulta?")
                continue

            # Normalizar y responder (probando variantes AR)
            for chunk in normalize_replies(result):
                ok, data, tried = wa.send_text_try_arg_variants(user_id, chunk)
                if not ok:
                    log.error("No se pudo enviar respuesta a %s. Probadas: %s. Última resp: %s",
                              user_id, tried, data)
                time.sleep(0.25)
    return JSONResponse({"status": "ok"})


# Helpers
def normalize_replies(result: HandlerReturn) -> List[str]:
    if result is None:
        return []
    if isinstance(result, str):
        return [result]
    if isinstance(result, dict):
        if "replies" in result and isinstance(result["replies"], (list, tuple)):
            return [str(x) for x in result["replies"]]
        if "reply" in result:
            return [str(result["reply"])]
        return [json.dumps(result, ensure_ascii=False)]
    if isinstance(result, (list, tuple, set)):
        return [str(x) for x in result]
    if hasattr(result, "__iter__"):
        try:
            return [str(x) for x in result]
        except Exception:
            pass
    return [str(result)]

# Entrypoint
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
