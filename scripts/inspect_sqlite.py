# -*- coding: utf-8 -*-
import sqlite3, argparse
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--db", required=True)
a = ap.parse_args()

con = sqlite3.connect(a.db)
cur = con.cursor()

print("== Tablas ==")
for (name,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    print(f"- {name}")
print()

table = input("Tabla a inspeccionar: ").strip()
print(f"\n== Columnas de {table} ==")
for cid, name, ctype, notnull, dflt, pk in cur.execute(f"PRAGMA table_info({table})"):
    print(f"- {name}  ({ctype})")
con.close()
