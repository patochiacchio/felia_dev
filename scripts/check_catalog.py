# -*- coding: utf-8 -*-
import json, random, argparse
from pathlib import Path

def read_text_smart(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("No pude decodificar el archivo (UTF-8/UTF-8-SIG/CP1252/Latin-1)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="catalog.utf8.json")
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()

    txt = read_text_smart(Path(a.path))
    data = json.loads(txt)
    print(f"Ítems: {len(data)}")
    for it in random.sample(data, min(a.n, len(data))):
        print(f"- {it.get('default_code')}: {it.get('name')}  ${it.get('price')}  stock={it.get('qty_available')}")
