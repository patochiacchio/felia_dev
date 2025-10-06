# find_core.py
import os, ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache"}

CANDIDATE_NAMES = {"handle_message","reply","process_message","process_input","orchestrate","main_handler"}

def to_module(p: Path) -> str | None:
    """Convierte ruta a nombre de módulo importable (si los dirs tienen __init__.py)."""
    rel = p.relative_to(ROOT)
    if rel.name == "__init__.py":
        rel = rel.parent
    else:
        rel = rel.with_suffix("")
    parts = []
    for part in rel.parts:
        if part in ("", "."):
            continue
        parts.append(part)
    if not parts:
        return None
    return ".".join(parts)

def has_init_chain(p: Path) -> bool:
    """¿Todos los directorios hasta ROOT tienen __init__.py? (para import dotted)"""
    if p.name == "__init__.py":
        p = p.parent
    parent = p.parent
    while parent != ROOT:
        if not (parent / "__init__.py").exists():
            return False
        parent = parent.parent
    return True

def scan():
    hits = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(".py"): 
                continue
            path = Path(dirpath) / fn
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in CANDIDATE_NAMES:
                    params = [a.arg for a in node.args.args]
                    mod = to_module(path) if has_init_chain(path) else None
                    hits.append({
                        "file": str(path.relative_to(ROOT)),
                        "func": node.name,
                        "params": params,
                        "import_path": (mod + f":{node.name}") if mod else None,
                        "needs_inits": mod is None,
                    })
    return hits

def main():
    hits = scan()
    if not hits:
        print("❌ No encontré funciones típicas. Buscá 'def handle_message' en el repo.")
        sys.exit(1)
    print("Posibles handlers en tu proyecto:\n")
    for h in hits:
        sig = "(" + ", ".join(h["params"]) + ")"
        mark = "⭐" if h["import_path"] else "⛔"
        print(f" {mark} {h['file']} :: def {h['func']}{sig}")
        if h["import_path"]:
            print(f"     import path → {h['import_path']}")
        else:
            print(f"     ⚠ Para importarlo por módulo agregá __init__.py en sus carpetas.")
    print("\nSugerencia: elegí un 'import path' y ponelo en FELIA_CORE_HANDLER_PATH del .env")
    print("Si ninguno tiene import path, agregá __init__.py en carpetas y re-ejecutá.")
if __name__ == "__main__":
    main()
