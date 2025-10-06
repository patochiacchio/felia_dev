# modules/catalog_cache.py — v1.9.9
import os, csv, sqlite3, re, unicodedata, logging
from typing import List, Dict
log = logging.getLogger(__name__)

def _unaccent(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))

def _canon(s: str) -> str:
    import re
    s = (s or "").lower().replace("×","x")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _fts_query_from_text(q: str) -> str:
    toks = re.findall(r'[a-zA-Z0-9]+|"', _unaccent(q))
    toks = [t.lower().strip('"') for t in toks if t and t != '"']
    toks = [t for t in toks if len(t) > 1]
    if not toks: return ''
    parts = [f'{t}*' for t in toks]
    return " OR ".join(parts)

class CatalogCache:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._ensure_schema()

    def _ensure_schema(self):
        c = self.conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS products(
            pid INTEGER PRIMARY KEY,
            name TEXT,
            name_canon TEXT,
            default_code TEXT,
            qty REAL,
            price REAL,
            category TEXT,
            uom TEXT
        );
        """)
        c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_products USING fts5(
            name, default_code, name_canon, category, uom, content=''
        );
        """)
        self.conn.commit()

    def rebuild_from_csv(self, csv_path: str):
        if not os.path.exists(csv_path):
            raise FileNotFoundError(csv_path)
        c = self.conn.cursor()
        c.execute("DELETE FROM products;")
        c.execute("DELETE FROM fts_products;")
        with open(csv_path, newline='', encoding='utf-8') as f:
            r = csv.DictReader(f)
            rows, fts = [], []
            for row in r:
                pid = int(row['id'])
                name = (row['name'] or "").strip()
                dc   = (row['default_code'] or "").strip()
                qty  = float(row['qty_available'] or 0)
                price= float(row['list_price'] or 0)
                cat  = (row.get('categ_id') or row.get('categ') or "").strip()
                uom  = (row.get('uom_id') or row.get('uom') or "").strip()
                name_c = _unaccent(_canon(name))
                rows.append((pid, name, name_c, dc, qty, price, cat, uom))
                fts.append((name, dc, name_c, cat, uom))
            c.executemany("INSERT INTO products(pid,name,name_canon,default_code,qty,price,category,uom) VALUES(?,?,?,?,?,?,?,?)", rows)
            c.executemany("INSERT INTO fts_products(name,default_code,name_canon,category,uom) VALUES(?,?,?,?,?)", fts)
        self.conn.commit()
        log.info(f"[CACHE] Rebuild OK — {len(rows)} productos")

    def search(self, q: str, limit: int = 60) -> List[Dict]:
        if not q or not q.strip(): return []
        fts = _fts_query_from_text(q)
        c = self.conn.cursor()
        out = []
        if fts:
            sql = "SELECT rowid, name, default_code, name_canon, category, uom FROM fts_products WHERE fts_products MATCH ? LIMIT ?;"
            for row in c.execute(sql, (fts, limit)):
                pid = row[0]
                p = c.execute("SELECT pid,name,default_code,qty,price FROM products WHERE pid=?", (pid,)).fetchone()
                if p:
                    out.append({"id": p[0], "name": p[1], "default_code": p[2], "qty_available": p[3], "list_price": p[4]})
        if not out:
            like = f"%{_unaccent(q).lower()}%"
            for row in c.execute("SELECT pid,name,default_code,qty,price FROM products WHERE name_canon LIKE ? LIMIT ?;", (like, limit)):
                out.append({"id": row[0], "name": row[1], "default_code": row[2], "qty_available": row[3], "list_price": row[4]})
        with_stock  = [i for i in out if (i.get("qty_available") or 0) > 0]
        without     = [i for i in out if (i.get("qty_available") or 0) <= 0]
        with_stock.sort(key=lambda x: (-(x.get("qty_available") or 0), x.get("name") or ""))
        without.sort(key=lambda x: (x.get("name") or ""))
        res = with_stock + without
        return res[:limit]

    def sample(self, terms: List[str], limit: int = 40) -> List[Dict]:
        items, seen = [], set()
        for t in terms or []:
            for p in self.search(t, limit=limit):
                pid = p["id"]
                if pid in seen: continue
                items.append(p); seen.add(pid)
                if len(items) >= limit: break
            if len(items) >= limit: break
        return items

_cache_singleton = None
def get_cache(db_path: str, csv_path: str, rebuild_if_missing: bool = True) -> "CatalogCache":
    global _cache_singleton
    if _cache_singleton is None:
        _cache_singleton = CatalogCache(db_path)
        try:
            cur = _cache_singleton.conn.cursor()
            n = cur.execute("SELECT COUNT(*) FROM products;").fetchone()[0]
            if n == 0 and rebuild_if_missing and os.path.exists(csv_path):
                _cache_singleton.rebuild_from_csv(csv_path)
        except Exception as e:
            log.warning(f"[CACHE] init warn: {e}")
    return _cache_singleton
