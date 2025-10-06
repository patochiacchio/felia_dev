# Felia Orquestador v0.3

**Objetivo**: que GPT haga el razonamiento (sin sinónimos hardcodeados) y el servidor haga la búsqueda local + ranking + anti-loop, con opción de hidratar candidatos en Odoo por `default_code`.

## Cómo correr

1) Entorno
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2) Configurar `.env`
```bash
cp .env.example .env
# Completar OPENAI_API_KEY y, si querés Odoo, ODOO_* y ODOO_HYDRATE=true
```

3) Levantar API
```bash
make run
# o
uvicorn app.main:app --reload --port 8000
```

4) Probar salud
```bash
curl http://localhost:8000/health
```

5) Probar búsqueda directa
```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"q":"perfil 70","must":["perfil"],"not":[]}'
```

6) Probar conversación
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","message":"Necesito perfiles para tabiques de 70"}'
```

## Tests
```bash
make test
```

## Comportamiento esperado de Felia
- **Saludo único** por sesión (flag `greeted`).
- **Rondas**: hasta 2; por ronda, hasta 3 preguntas nuevas (anti-loop por `asked_questions`).
- **Planner JSON** (GPT) devuelve `{q, must, not, units, decision, questions}` sin ejemplos ni marcas.
- **Búsqueda local**: cache-first en `catalog.json`; si 0 resultados, retries internos (must-only → q-only).
- **Ranking**: stock>0 primero, +must, +q, −not; dedupe por `default_code`.
- **Salida al cliente**: 2–4 ítems, **negrita**, **código**, **precio**, **Disponible/Sin stock**. Sin cantidades.
- **Odoo opcional**: si `ODOO_HYDRATE=true`, se leen `qty_available` (campo computado) y `lst_price/list_price` por `default_code` para **los candidatos**.

## Dónde modificar
- **Pesos**: `app/ranking.py`
- **Prompt**: `app/llm.py` (`SYSTEM_PROMPT`)
- **Catálogo**: `catalog.json` o `CATALOG_PATH` en `.env`
- **Límites**: `MAX_RETURN`, `MIN_RETURN` en `.env`
- **Odoo**: `app/odoo_client.py` (dominios, campos)

## Notas
- No ordenamos por `qty_available` en Odoo (campo no stored). Sólo lo **leemos** al hidratar.
- Si el modelo devuelve JSON inválido, hay fallback con una pregunta estándar para no romper la sesión.
