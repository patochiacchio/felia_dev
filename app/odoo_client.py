from typing import List, Dict
from .settings import settings
import xmlrpc.client

class OdooClient:
    def __init__(self):
        self.url = settings.odoo_url
        self.db = settings.odoo_db
        self.username = settings.odoo_user
        self.password = settings.odoo_password
        self._uid = None
        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def _login(self):
        if self._uid is None:
            self._uid = self._common.authenticate(self.db, self.username, self.password, {})
        return self._uid

    def read_product_by_code(self, default_code: str):
        uid = self._login()
        if not uid:
            return None
        dom = [["default_code", "=", default_code]]
        ids = self._models.execute_kw(self.db, uid, self.password, "product.product", "search", [dom], {"limit": 1})
        if not ids:
            ids_t = self._models.execute_kw(self.db, uid, self.password, "product.template", "search", [dom], {"limit": 1})
            if not ids_t:
                return None
            recs = self._models.execute_kw(self.db, uid, self.password, "product.template", "read", [ids_t, ["name", "list_price", "qty_available", "default_code"]])
            return recs[0] if recs else None
        recs = self._models.execute_kw(self.db, uid, self.password, "product.product", "read", [ids, ["name", "lst_price", "qty_available", "default_code"]])
        return recs[0] if recs else None

def hydrate_candidates(items: List[Dict]) -> List[Dict]:
    """Enriquece precio/stock desde Odoo por default_code (si ODOO_HYDRATE=true)."""
    if not settings.odoo_hydrate:
        return items
    cli = OdooClient()
    out: List[Dict] = []
    for it in items:
        code = it.get("default_code")
        rec = cli.read_product_by_code(code) if code else None
        if rec:
            qty = rec.get("qty_available", it.get("qty_available", 0))
            price = rec.get("lst_price") or rec.get("list_price") or it.get("price", 0)
            it = {**it, "qty_available": qty, "price": float(price)}
        out.append(it)
    return out
