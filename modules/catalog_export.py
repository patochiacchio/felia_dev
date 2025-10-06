# modules/catalog_export.py — v2.0
import os
import csv
import logging
import ssl
import http.client
import xmlrpc.client
from typing import List, Dict, Tuple
from pathlib import Path

log = logging.getLogger(__name__)

# ── .env: detectar automáticamente el archivo en el árbol ─────────────────────
try:
    from dotenv import load_dotenv, find_dotenv
    env_path = find_dotenv(filename=".env", usecwd=True)
    if env_path:
        load_dotenv(env_path, override=False)
        log.debug(f"[catalog_export] .env loaded from: {env_path}")
    else:
        log.debug("[catalog_export] .env not found; relying on OS env vars")
except Exception as e:
    log.debug(f"[catalog_export] dotenv not used: {e}")

# ── Variables Odoo (acepta ODOO_USERNAME o ODOO_USER) ─────────────────────────
ODOO_URL      = (os.getenv("ODOO_URL", "") or "").rstrip("/")
ODOO_DB       = os.getenv("ODOO_DB", "") or ""
ODOO_USERNAME = os.getenv("ODOO_USERNAME") or os.getenv("ODOO_USER") or ""
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD") or ""

class InsecureTransport(xmlrpc.client.Transport):
    def make_connection(self, host):
        return http.client.HTTPSConnection(host, context=ssl._create_unverified_context())

def _missing_vars() -> List[str]:
    missing = []
    if not ODOO_URL: missing.append("ODOO_URL")
    if not ODOO_DB: missing.append("ODOO_DB")
    if not ODOO_USERNAME: missing.append("ODOO_USERNAME (o ODOO_USER)")
    if not ODOO_PASSWORD: missing.append("ODOO_PASSWORD")
    return missing

def _session() -> Tuple[int, xmlrpc.client.ServerProxy]:
    missing = _missing_vars()
    if missing:
        raise RuntimeError(
            "Faltan credenciales Odoo en .env: " + ", ".join(missing) +
            "\nTips: verificá el archivo .env en la raíz del proyecto; "
            "soportamos ODOO_USERNAME o ODOO_USER."
        )
    transport = InsecureTransport() if ODOO_URL.startswith("https://") else None
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", transport=transport)
    uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
    if not uid:
        raise RuntimeError("Autenticación Odoo falló (usuario/contraseña/DB/URL).")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", transport=transport)
    return uid, models

FIELDS = ["id", "name", "default_code", "qty_available", "list_price", "categ_id", "uom_id"]

def export_catalog(csv_path: str, limit_batch: int = 200) -> int:
    uid, models = _session()
    ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, "product.template", "search", [[("active", "=", True)]])
    total = len(ids)
    if total == 0:
        log.info("No hay productos para exportar.")
        return 0

    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    log.info(f"Exportando {total} productos a {csv_path} …")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for i in range(0, total, limit_batch):
            batch_ids = ids[i:i + limit_batch]
            rows = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                "product.template", "read", [batch_ids],
                {"fields": FIELDS}
            )
            for r in rows:
                categ = r.get("categ_id") or [None, ""]
                uom = r.get("uom_id") or [None, ""]
                w.writerow([
                    r.get("id"),
                    (r.get("name") or "").replace("\n", " ").strip(),
                    (r.get("default_code") or "").strip(),
                    r.get("qty_available") or 0,
                    r.get("list_price") or 0,
                    categ[1] or "",
                    uom[1] or ""
                ])
    log.info("Export finalizado.")
    return total

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    out = os.getenv("CATALOG_CSV_PATH", "./catalog.csv")
    export_catalog(out)
