import sys
import os
import secrets
import logging
import time
from datetime import date
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles

# ── Imports de servicios (una sola vez, al arrancar) ─────────────────────────
import google.genai as genai
from notion_client import Client as NotionClient
from main import process as gemini_process

# ── Config ────────────────────────────────────────────────────────────────────
APP_PASSWORD  = os.getenv("APP_PASSWORD", "")
NOTION_TOKEN  = os.getenv("NOTION_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
NOTION_DB_ID  = "32d95c1828928086a307fcf471e4ffc3"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Rate limiter (máx 10 requests de Gemini por minuto por token) ─────────────
_rate_buckets: dict = defaultdict(list)
RATE_LIMIT     = 10   # requests
RATE_WINDOW    = 60   # segundos

def check_rate_limit(token: str):
    now = time.time()
    bucket = _rate_buckets[token]
    # Limpiar entradas fuera de la ventana
    _rate_buckets[token] = [t for t in bucket if now - t < RATE_WINDOW]
    if len(_rate_buckets[token]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Espera un momento.")
    _rate_buckets[token].append(now)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI()

# Servir archivos estáticos (JS, CSS, imágenes futuras)
_static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

_sessions: set = set()
security = HTTPBearer(auto_error=False)

# ── Auth ─────────────────────────────────────────────────────────────────────
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or credentials.credentials not in _sessions:
        raise HTTPException(status_code=401, detail="No autorizado")
    return credentials.credentials

@app.post("/login")
async def login(request: Request):
    body = await request.json()
    password = body.get("password", "")
    if not APP_PASSWORD:
        raise HTTPException(status_code=500, detail="APP_PASSWORD no configurado en variables de entorno")
    if password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    token = secrets.token_hex(32)
    _sessions.add(token)
    logger.info("Nueva sesión creada")
    return {"token": token}

@app.post("/logout")
async def logout(token: str = Depends(verify_token)):
    _sessions.discard(token)
    return {"ok": True}

# ── Ruta pública ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, encoding="utf-8") as f:   # FIX: context manager
        return f.read()

# ── Rutas protegidas ──────────────────────────────────────────────────────────
@app.post("/process")
async def handle(request: Request, token: str = Depends(verify_token)):
    try:
        check_rate_limit(token)
        body    = await request.json()
        content = body.get("content", "")
        result  = gemini_process(content)           # FIX: import al inicio
        return JSONResponse(result)
    except Exception as e:
        logger.error("Error en /process: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/reprocess")
async def reprocess(request: Request, token: str = Depends(verify_token)):
    try:
        check_rate_limit(token)
        body    = await request.json()
        content = body.get("content", "")
        result  = gemini_process(content)           # FIX: import al inicio
        return JSONResponse(result)
    except Exception as e:
        logger.error("Error en /reprocess: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/chat")
async def chat(request: Request, token: str = Depends(verify_token)):
    try:
        body       = await request.json()
        question   = body.get("question", "")
        context    = body.get("context", "")
        ideas_mode = body.get("ideas_mode", False)
        client     = genai.Client(api_key=GEMINI_API_KEY)  # FIX: import al inicio
        ctx_block  = f"NOTAS DE CONTEXTO:\n{context}" if context else "No hay notas seleccionadas."

        if ideas_mode:
            prompt = (
                "Eres un asistente creativo de brainstorming. "
                "Basándote en las notas de contexto, genera ideas concretas, "
                "conexiones no obvias entre conceptos, oportunidades de acción "
                "y preguntas que vale la pena explorar. "
                "Sé específico, directo y propositivo. Responde en español.\n\n"
                f"{ctx_block}\n\nTEMA A EXPLORAR: {question}"
            )
        else:
            prompt = (
                f"Eres un asistente personal. Responde SOLO basándote en las notas. "
                f"Responde en español.\n\n{ctx_block}\n\nPREGUNTA: {question}"
            )

        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return JSONResponse({"answer": response.text.strip()})
    except Exception as e:
        logger.error("Error en /chat: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/delete-notion")
async def delete_notion(request: Request, token: str = Depends(verify_token)):
    try:
        body    = await request.json()
        page_id = body.get("page_id", "")
        if not page_id:
            return JSONResponse({"error": "No page_id"}, status_code=400)
        notion = NotionClient(auth=NOTION_TOKEN)    # FIX: import al inicio
        notion.pages.update(page_id=page_id, archived=True)
        logger.info("Página archivada: %s", page_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("Error en /delete-notion: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/set-reminder")
async def set_reminder(request: Request, token: str = Depends(verify_token)):
    try:
        body     = await request.json()
        page_id  = body.get("page_id", "")
        date_str = body.get("date", "")
        if not page_id:
            return JSONResponse({"error": "No page_id"}, status_code=400)
        notion = NotionClient(auth=NOTION_TOKEN)    # FIX: import al inicio
        if date_str:
            notion.pages.update(
                page_id=page_id,
                properties={"Reminder": {"date": {"start": date_str}}}
            )
        else:
            notion.pages.update(
                page_id=page_id,
                properties={"Reminder": {"date": None}}
            )
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("Error en /set-reminder: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/reminders")
async def get_reminders(token: str = Depends(verify_token)):
    try:
        notion = NotionClient(auth=NOTION_TOKEN)    # FIX: import al inicio
        today  = date.today().isoformat()

        resp = notion.databases.query(
            database_id=NOTION_DB_ID,
            filter={"property": "Reminder", "date": {"is_not_empty": True}},
            sorts=[{"property": "Reminder", "direction": "ascending"}],
            page_size=50,
        )

        reminders = []
        for page in resp.get("results", []):
            props       = page.get("properties", {})
            title_prop  = props.get("Name", {}).get("title", [])
            title       = title_prop[0]["plain_text"] if title_prop else "Sin título"
            reminder_prop = props.get("Reminder", {}).get("date")
            reminder_date = reminder_prop["start"] if reminder_prop else None
            if not reminder_date:
                continue
            reminders.append({
                "page_id":       page["id"],
                "title":         title,
                "url":           page.get("url", ""),
                "reminder_date": reminder_date,
                "is_overdue":    reminder_date < today,
                "is_today":      reminder_date == today,
            })

        return JSONResponse({"reminders": reminders})
    except Exception as e:
        logger.error("Error en /reminders: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/notes")
async def get_notes(token: str = Depends(verify_token)):
    try:
        notion  = NotionClient(auth=NOTION_TOKEN)   # FIX: import al inicio
        results = []
        cursor  = None

        while True:
            kwargs = {
                "database_id": NOTION_DB_ID,
                "sorts":       [{"property": "Name", "direction": "descending"}],
                "page_size":   100,
            }
            if cursor:
                kwargs["start_cursor"] = cursor

            resp = notion.databases.query(**kwargs)
            results.extend(resp.get("results", []))

            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")

        notes = []
        for page in results:
            props = page.get("properties", {})

            title_prop    = props.get("Name",     {}).get("title",        [])
            type_prop     = props.get("Type",     {}).get("select")
            summary_prop  = props.get("Summary",  {}).get("rich_text",    [])
            insights_prop = props.get("Insights", {}).get("rich_text",    [])
            actions_prop  = props.get("Actions",  {}).get("rich_text",    [])
            status_prop   = props.get("Status",   {}).get("select")
            reminder_prop = props.get("Reminder", {}).get("date")

            notes.append({
                "title":         title_prop[0]["plain_text"] if title_prop else "Sin título",
                "type":          type_prop["name"] if type_prop else "KNOWLEDGE",
                "tags":          [t["name"] for t in props.get("Tags", {}).get("multi_select", [])],
                "summary":       summary_prop[0]["plain_text"]  if summary_prop  else "",
                "insights":      insights_prop[0]["plain_text"] if insights_prop else "",
                "actions":       actions_prop[0]["plain_text"]  if actions_prop  else "",
                "status":        status_prop["name"] if status_prop else "",
                "date":          page.get("created_time", ""),
                "url":           page.get("url", ""),
                "page_id":       page["id"],
                "reminder_date": reminder_prop["start"] if reminder_prop else None,
            })

        return JSONResponse({"notes": notes})
    except Exception as e:
        logger.error("Error en /notes: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
