from app.search import Catalog

CATALOG = [
  {"name": "Perfil C galvanizado 70x35x0.9mm 3m", "default_code": "PF-C-70x35-09-3000", "price": 14350.0, "qty_available": 25},
  {"name": "Perfil U galvanizado 35x35x0.9mm 3m", "default_code": "PF-U-35x35-09-3000", "price": 11800.0, "qty_available": 0},
  {"name": "Omega galvanizado 45x15x0.9mm 3m",   "default_code": "PF-O-45x15-09-3000", "price": 12990.0, "qty_available": 12}
]

class Dummy(Catalog):
    def __init__(self):
        self.items = CATALOG

def test_search_must_filtra_bien():
    c = Dummy()
    res = c.search("perfil", ["perfil", "c"], [], 10)
    assert len(res) == 1
    assert res[0]["default_code"] == "PF-C-70x35-09-3000"

def test_retry_q_only():
    c = Dummy()
    res = c.retry_variants("omega", ["no_existe"], [], 10)
    # Debe caer a búsqueda por q-only
    assert any(r["default_code"] == "PF-O-45x15-09-3000" for r in res)
