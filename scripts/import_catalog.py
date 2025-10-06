# scripts/import_catalog.py
import csv, json, argparse, sys
from pathlib import Path

def _pick(headers, *candidates):
    hset = {h.lower().strip(): h for h in headers}
    for group in candidates:
        for key in group:
            k = key.lower().strip()
            if k in hset:
                return hset[k]
    return None

def _to_float(x):
    if x is None:
        return 0.0
    s = str(x).strip()
    if s == "":
        return 0.0
    # soportar coma decimal y separador de miles
    s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") >= 1 else s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

def _to_int(x):
    try:
        return int(float(str(x).replace(",", ".").strip()))
    except Exception:
        return 0

def sniff_open(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        sample = f.read(2048)
    try:
        dialect = csv.Sniffer().sniff(sample)
    except Exception:
        class _D: delimiter = ";"
        dialect = _D()
    return open(path, "r", encoding="utf-8", newline=""), dialect

def convert_csv_to_json(src_csv: Path, out_json: Path, limit=None):
    f, dialect = sniff_open(src_csv)
    reader = csv.DictReader(f, dialect=dialect)
    headers = reader.fieldnames or []
    # mapeo flexible de columnas
    name_col = _pick(headers,
        ("name","product_name","display_name","nombre","descripcion","description","product"))
    code_col = _pick(headers,
        ("default_code","sku","internal_reference","codigo","code","referencia","ref"))
    price_col = _pick(headers,
        ("price","list_price","lst_price","precio","unit_price","sale_price"))
    qty_col = _pick(headers,
        ("qty_available","stock","on_hand","onhand","quantity","qty","existencia","disponible"))

    if not name_col or not code_col:
        print("ERROR: No pude detectar columnas nombre/código. Encabezados detectados:", headers, file=sys.stderr)
        sys.exit(2)

    out = []
    for i, row in enumerate(reader):
        if limit and i >= limit:
            break
        name = (row.get(name_col) or "").strip()
        code = (row.get(code_col) or "").strip()
        if not name or not code:
            continue
        price = _to_float(row.get(price_col)) if price_col else 0.0
        qty = _to_int(row.get(qty_col)) if qty_col else 0
        out.append({
            "name": name,
            "default_code": code,
            "price": price,
            "qty_available": qty,
        })

    f.close()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as fw:
        json.dump(out, fw, ensure_ascii=False, indent=2)
    print(f"OK: {len(out)} ítems → {out_json}")

def main():
    p = argparse.ArgumentParser(description="Importar catálogo CSV → catalog.json (búsqueda local)")
    p.add_argument("--src", required=True, help="Ruta al CSV real")
    p.add_argument("--out", default="catalog.json", help="Salida JSON (default: catalog.json)")
    p.add_argument("--limit", type=int, default=None, help="(opcional) limitar filas para prueba")
    args = p.parse_args()
    convert_csv_to_json(Path(args.src), Path(args.out), args.limit)

if __name__ == "__main__":
    main()
