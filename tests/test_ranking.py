from app.ranking import score_item

BASE = {
    "name": "Perfil C galvanizado 70x35x0.9mm 3m",
    "default_code": "PF-C-70x35-09-3000",
    "price": 100.0,
    "qty_available": 10,
}

def test_score_prefiere_stock():
    a = dict(BASE)
    b = dict(BASE, qty_available=0, default_code="X")
    sa = score_item(a, ["perfil"], [], ["perfil"])  # tiene stock
    sb = score_item(b, ["perfil"], [], ["perfil"])  # sin stock
    assert sa > sb

def test_penaliza_not_tokens():
    item = dict(BASE)
    s1 = score_item(item, [], ["madera"], [])  # no contiene 'madera'
    s2 = score_item(dict(BASE, name="Perfil C madera"), [], ["madera"], [])
    assert s1 > s2
