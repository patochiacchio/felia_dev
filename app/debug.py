# app/debug.py
import json, logging, os
from pathlib import Path
from .settings import settings

_LOGGER = logging.getLogger("felia")
if not _LOGGER.handlers:
    level = logging.DEBUG if settings.debug else logging.INFO
    _LOGGER.setLevel(level)

    # consola
    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _LOGGER.addHandler(sh)

    # archivo (json lines)
    logdir = Path(settings.log_dir)
    logdir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(logdir / "felia.log", encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(message)s"))  # ya mandamos JSON
    _LOGGER.addHandler(fh)

def trace(event: str, session_id: str, **kv):
    """Log estructurado (una línea JSON) + breve rastro legible en consola."""
    payload = {
        "event": event,
        "session": session_id,
        **kv
    }
    # línea humana (corta)
    _LOGGER.info(f"{event} s={session_id}")
    # línea JSON
    _LOGGER.info(json.dumps(payload, ensure_ascii=False))
