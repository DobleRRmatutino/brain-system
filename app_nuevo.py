import sys
import os
import secrets
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

app = FastAPI()

# ── Config ────────────────────────────────────────────────────────────────────
NOTION_DB_ID = os.getenv("NOTION_DB_ID", "32d95c1828928086a307fcf471e4ffc3")

# ── Auth ─────────────────────────────────────────────────────────────────────
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
_sessions: set = set()

security = HTTPBearer(auto_error=False)

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
    return {"token": token}

@app.post("/logout")
async def logout(token: str = Depends(verify_token)):
    _sessions.discard(token)
    return {"ok": True}

# ── Rutas públicas ────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home():
    return open(os.path.join(os.path.dirname(__file__), "index.html")).read()

# ── Rutas protegidas ──────────────────────────────────────────────────────────
@app.post("/process")
async def handle(request: Request, token: str = Depends(verify_token)):
    try:
        from main import process
        body = await request.json()
        content = body.get("content", "")
        result = process(content)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/chat")
async def chat(request: Request, token: str = Depends(verify_token)):
    try:
        import google.genai as genai
        body = await request.json()
        question   = body.get("question", "")
        context    = body.get("context", "")
        ideas_mode = body.get("ideas_mode", False)
        client     = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
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
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/delete-notion")
async def delete_notion(request: Request, token: str = Depends(verify_token)):
    try:
        from notion_client import Client
        body = await request.json()
        page_id = body.get("page_id", "")
        if not page_id:
            return JSONResponse({"error": "No page_id"}, status_code=400)
        notion = Client(auth=os.getenv("NOTION_TOKEN"))
        notion.pages.update(page_id=page_id, archived=True)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/set-reminder")
async def set_reminder(request: Request, token: str = Depends(verify_token)):
    try:
        from notion_client import Client
        body = await request.json()
        page_id = body.get("page_id", "")
        date_str = body.get("date", "")  # ISO date string "YYYY-MM-DD" or "" to clear
        if not page_id:
            return JSONResponse({"error": "No page_id"}, status_code=400)
        logger.info(f"set-reminder: page_id={page_id}, date={date_str!r}")
        notion = Client(auth=os.getenv("NOTION_TOKEN"))
        if date_str:
            result = notion.pages.update(
                page_id=page_id,
                properties={"Reminder": {"date": {"start": date_str}}}
            )
        else:
            result = notion.pages.update(
                page_id=page_id,
                properties={"Reminder": {"date": None}}
            )
        logger.info(f"set-reminder OK: {result.get('id', '?')}")
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error(f"set-reminder ERROR: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/reminders")
async def get_reminders(token: str = Depends(verify_token)):
    try:
        from notion_client import Client
        from datetime import date
        notion = Client(auth=os.getenv("NOTION_TOKEN"))
        today = date.today().isoformat()
        logger.info(f"get_reminders: querying DB={NOTION_DB_ID}, today={today}")

        resp = notion.databases.query(
            database_id=NOTION_DB_ID,
            filter={
                "property": "Reminder",
                "date": {"is_not_empty": True}
            },
            sorts=[{"property": "Reminder", "direction": "ascending"}],
            page_size=50,
        )

        reminders = []
        for page in resp.get("results", []):
            props = page.get("properties", {})
            title_prop = props.get("Name", {}).get("title", [])
            title = title_prop[0]["plain_text"] if title_prop else "Sin título"
            reminder_prop = props.get("Reminder", {}).get("date")
            reminder_date = reminder_prop["start"] if reminder_prop else None
            if not reminder_date:
                continue
            is_overdue = reminder_date < today
            is_today = reminder_date == today
            reminders.append({
                "page_id": page["id"],
                "title": title,
                "url": page.get("url", ""),
                "reminder_date": reminder_date,
                "is_overdue": is_overdue,
                "is_today": is_today,
            })

        logger.info(f"get_reminders: found {len(reminders)} reminders")
        return JSONResponse({"reminders": reminders})
    except Exception as e:
        logger.error(f"get_reminders ERROR: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/reprocess")
async def reprocess(request: Request, token: str = Depends(verify_token)):
    try:
        from main import process
        body = await request.json()
        content = body.get("content", "")
        result = process(content)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ── Notion Sync ───────────────────────────────────────────────────────────────

@app.get("/notes")
async def get_notes(token: str = Depends(verify_token)):
    try:
        from notion_client import Client
        notion = Client(auth=os.getenv("NOTION_TOKEN"))

        results = []
        cursor = None

        # Paginate through all pages in the database
        while True:
            kwargs = {
                "database_id": NOTION_DB_ID,
                "sorts": [{"property": "Name", "direction": "descending"}],
                "page_size": 100,
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

            # Name / title
            title_prop = props.get("Name", {}).get("title", [])
            title = title_prop[0]["plain_text"] if title_prop else "Sin título"

            # Type (select)
            type_prop = props.get("Type", {}).get("select")
            note_type = type_prop["name"] if type_prop else "KNOWLEDGE"

            # Tags (multi_select)
            tags = [t["name"] for t in props.get("Tags", {}).get("multi_select", [])]

            # Summary (rich_text)
            summary_prop = props.get("Summary", {}).get("rich_text", [])
            summary = summary_prop[0]["plain_text"] if summary_prop else ""

            # Insights (rich_text)
            insights_prop = props.get("Insights", {}).get("rich_text", [])
            insights = insights_prop[0]["plain_text"] if insights_prop else ""

            # Actions (rich_text)
            actions_prop = props.get("Actions", {}).get("rich_text", [])
            actions = actions_prop[0]["plain_text"] if actions_prop else ""

            # Status (select)
            status_prop = props.get("Status", {}).get("select")
            status = status_prop["name"] if status_prop else ""

            # Date (created_time)
            created = page.get("created_time", "")

            # Reminder (date)
            reminder_prop = props.get("Reminder", {}).get("date")
            reminder_date = reminder_prop["start"] if reminder_prop else None

            # Notion URL
            url = page.get("url", "")

            notes.append({
                "title":         title,
                "type":          note_type,
                "tags":          tags,
                "summary":       summary,
                "insights":      insights,
                "actions":       actions,
                "status":        status,
                "date":          created,
                "url":           url,
                "page_id":       page["id"],
                "reminder_date": reminder_date,
            })

        return JSONResponse({"notes": notes})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
