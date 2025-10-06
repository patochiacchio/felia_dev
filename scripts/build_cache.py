# scripts/build_cache.py
import os, logging
from modules.catalog_cache import get_cache

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

DB  = os.getenv("CATALOG_DB_PATH", "./catalog.db")
CSV = os.getenv("CATALOG_CSV_PATH", "./catalog.csv")

if __name__ == "__main__":
    cache = get_cache(DB, CSV, rebuild_if_missing=True)
    print("Cache listo en:", DB)
