# -*- coding: utf-8 -*-
import sqlite3, json, argparse, sys
from pathlib import Path

def export_sqlite(db_path: Path, out_json: Path, table=None, name_col=None, code_col=None, price_col=None, qty_col=None):
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    rows = []
    if all([table, name_col, code_col]):
        q = f"""
        SELECT
          {name_col} AS name,
          {code_col} AS default_code,
          COALESCE({price_col or 0}, 0) AS price,
          COALESCE({qty_col or 0}, 0) AS qty_available
        FROM {table}
        """
        try:
            cur.execute(q)
            rows = cur.fetchall()
        except Exception as e:
            print("ERROR al ejecutar query custom:", e, file=sys.stderr)
            con.close(); sys.exit(2)
    else:
        print("No pude autodetectar la tabla/columnas. Pasá --table y columnas.", file=sys.stderr)
        con.close(); sys.exit(2)

    out = []
    for r in rows:
        name = (r["name"] or "").strip()
        code = (r["default_code"] or "").strip()
        if not name or not code: continue
        price = float(r["price"] or 0)
        qty = int(float(r["qty_available"] or 0))
        out.append({"name": name, "default_code": code, "price": price, "qty_available": qty})

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    con.close()
    print(f"OK: {len(out)} ítems → {out_json}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Exportar catálogo SQLite → catalog.json")
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="catalog.json")
    ap.add_argument("--table", required=True)
    ap.add_argument("--name-col", required=True)
    ap.add_argument("--code-col", required=True)
    ap.add_argument("--price-col")
    ap.add_argument("--qty-col")
    a = ap.parse_args()
    export_sqlite(Path(a.db), Path(a.out), a.table, a.name_col, a.code_col, a.price_col, a.qty_col)
