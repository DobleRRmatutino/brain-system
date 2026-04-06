import sys
import os
import secrets
import logging
import time
import httpx
from datetime import date, datetime, timezone
from collections import defaultdict
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles

import google.genai as genai
from notion_client import Client as NotionClient
from main import process as gemini_process

# ── Config ────────────────────────────────────────────────────────────────────
APP_PASSWORD     = os.getenv("APP_PASSWORD", "")
NOTION_TOKEN     = os.getenv("NOTION_TOKEN", "")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
NOTION_DB_ID     = "32d95c1828928086a307fcf471e4ffc3"

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = "https://brain-system.onrender.com/auth/google/callback"
GOOGLE_SCOPES        = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
_rate_buckets: dict = defaultdict(list)
RATE_LIMIT  = 10
RATE_WINDOW = 60

def check_rate_limit(token: str):
    now = time.time()
    _rate_buckets[token] = [t for t in _rate_buckets[token] if now - t < RATE_WINDOW]
    if len(_rate_buckets[token]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Espera un momento.")
    _rate_buckets[token].append(now)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI()

_static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

_sessions: set      = set()
_google_tokens: dict = {}   # session_token -> {access_token, refresh_token}
security = HTTPBearer(auto_error=False)

# ── Auth ──────────────────────────────────────────────────────────────────────
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or credentials.credentials not in _sessions:
        raise HTTPException(status_code=401, detail="No autorizado")
    return credentials.credentials

@app.post("/login")
async def login(request: Request):
    body = await request.json()
    if not APP_PASSWORD:
        raise HTTPException(status_code=500, detail="APP_PASSWORD no configurado")
    if body.get("password", "") != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    token = secrets.token_hex(32)
    _sessions.add(token)
    logger.info("Nueva sesión creada")
    return {"token": token}

@app.post("/logout")
async def logout(token: str = Depends(verify_token)):
    _sessions.discard(token)
    _google_tokens.pop(token, None)
    return {"ok": True}

# ── Ruta pública ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, encoding="utf-8") as f:
        return f.read()

# ── Rutas protegidas — Brain System ──────────────────────────────────────────
@app.post("/process")
async def handle(request: Request, token: str = Depends(verify_token)):
    try:
        check_rate_limit(token)
        body   = await request.json()
        result = gemini_process(body.get("content", ""))
        return JSONResponse(result)
    except Exception as e:
        logger.error("Error en /process: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/reprocess")
async def reprocess(request: Request, token: str = Depends(verify_token)):
    try:
        check_rate_limit(token)
        body   = await request.json()
        result = gemini_process(body.get("content", ""))
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
        client     = genai.Client(api_key=GEMINI_API_KEY)
        ctx_block  = f"NOTAS DE CONTEXTO:\n{context}" if context else "No hay notas seleccionadas."

        if ideas_mode:
            prompt = (
                "Eres un asistente creativo de brainstorming. "
                "Basándote en las notas de contexto, genera ideas concretas, "
                "conexiones no obvias, oportunidades de acción y preguntas que vale explorar. "
                "Sé específico y propositivo. Responde en español.\n\n"
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
        notion = NotionClient(auth=NOTION_TOKEN)
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
        notion = NotionClient(auth=NOTION_TOKEN)
        props  = {"Reminder": {"date": {"start": date_str}}} if date_str else {"Reminder": {"date": None}}
        notion.pages.update(page_id=page_id, properties=props)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("Error en /set-reminder: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/reminders")
async def get_reminders(token: str = Depends(verify_token)):
    try:
        notion = NotionClient(auth=NOTION_TOKEN)
        today  = date.today().isoformat()
        resp   = notion.databases.query(
            database_id=NOTION_DB_ID,
            filter={"property": "Reminder", "date": {"is_not_empty": True}},
            sorts=[{"property": "Reminder", "direction": "ascending"}],
            page_size=50,
        )
        reminders = []
        for page in resp.get("results", []):
            props         = page.get("properties", {})
            title_prop    = props.get("Name", {}).get("title", [])
            title         = title_prop[0]["plain_text"] if title_prop else "Sin título"
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
        notion  = NotionClient(auth=NOTION_TOKEN)
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
            props         = page.get("properties", {})
            title_prop    = props.get("Name",     {}).get("title",     [])
            type_prop     = props.get("Type",     {}).get("select")
            summary_prop  = props.get("Summary",  {}).get("rich_text", [])
            insights_prop = props.get("Insights", {}).get("rich_text", [])
            actions_prop  = props.get("Actions",  {}).get("rich_text", [])
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

# ── Google OAuth ──────────────────────────────────────────────────────────────
@app.get("/auth/google/status")
async def google_status(token: str = Depends(verify_token)):
    return JSONResponse({"connected": token in _google_tokens})

@app.get("/auth/google")
async def google_auth(request: Request, token: str = Depends(verify_token)):
    qt = request.query_params.get("_token", "")
    if qt and qt in _sessions:
        token = qt
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(GOOGLE_SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         token,
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))

@app.get("/auth/google/callback")
async def google_callback(request: Request):
    code  = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error", "")

    if error or not code:
        return HTMLResponse(f"<h3 style='font-family:monospace;color:#f87171'>Error OAuth: {error or 'sin código'}</h3>")
    if state not in _sessions:
        return HTMLResponse("<h3 style='font-family:monospace;color:#f87171'>Sesión inválida. Vuelve a brain-system e intenta de nuevo.</h3>")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  GOOGLE_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
        )

    if resp.status_code != 200:
        logger.error("Error intercambiando token: %s", resp.text)
        return HTMLResponse(f"<h3 style='font-family:monospace;color:#f87171'>Error al obtener tokens: {resp.text}</h3>")

    tokens = resp.json()
    _google_tokens[state] = {
        "access_token":  tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
    }
    logger.info("Google OAuth OK para sesión: %s…", state[:8])

    return HTMLResponse("""
    <html><head><meta charset="UTF-8"></head>
    <body style="font-family:monospace;background:#0a0a0a;color:#f0f0f0;
                 display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
    <div style="text-align:center">
      <div style="font-size:32px;margin-bottom:14px">✓</div>
      <div style="font-size:14px;color:#4ade80;margin-bottom:6px">Google conectado</div>
      <div style="font-size:12px;color:#444">Cerrando ventana...</div>
      <script>
        if (window.opener) { window.opener.postMessage('google_connected', '*'); window.close(); }
        else { setTimeout(function(){ window.location = '/'; }, 1500); }
      </script>
    </div></body></html>
    """)

# ── Helpers Google API ────────────────────────────────────────────────────────
async def _refresh_token(session_token: str) -> str | None:
    gt = _google_tokens.get(session_token, {})
    refresh = gt.get("refresh_token")
    if not refresh:
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh,
                "grant_type":    "refresh_token",
            },
        )
    if resp.status_code == 200:
        new_access = resp.json().get("access_token")
        _google_tokens[session_token]["access_token"] = new_access
        return new_access
    return None

async def _gapi_get(url: str, session_token: str, params: dict = None):
    gt     = _google_tokens.get(session_token, {})
    access = gt.get("access_token")
    if not access:
        raise HTTPException(status_code=403, detail="Google no conectado. Ve a Inbox → Conectar Google.")
    headers = {"Authorization": f"Bearer {access}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params or {})
        if resp.status_code == 401:
            new_access = await _refresh_token(session_token)
            if not new_access:
                raise HTTPException(status_code=403, detail="Google no autorizado. Reconecta.")
            resp = await client.get(url, headers={"Authorization": f"Bearer {new_access}"}, params=params or {})
    return resp

# ── Gmail ─────────────────────────────────────────────────────────────────────
@app.get("/inbox")
async def get_inbox(token: str = Depends(verify_token)):
    try:
        list_resp = await _gapi_get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            token,
            params={"maxResults": 20, "labelIds": "INBOX"},
        )
        if list_resp.status_code != 200:
            return JSONResponse({"error": list_resp.text}, status_code=list_resp.status_code)

        msg_ids = [m["id"] for m in list_resp.json().get("messages", [])]
        gt      = _google_tokens.get(token, {})
        access  = gt.get("access_token", "")
        emails  = []

        async with httpx.AsyncClient() as client:
            for msg_id in msg_ids:
                r = await client.get(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}",
                    headers={"Authorization": f"Bearer {access}"},
                    params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                )
                if r.status_code != 200:
                    continue
                data    = r.json()
                headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
                labels  = data.get("labelIds", [])
                emails.append({
                    "id":      msg_id,
                    "from":    headers.get("From", ""),
                    "subject": headers.get("Subject", "(sin asunto)"),
                    "date":    headers.get("Date", ""),
                    "snippet": data.get("snippet", ""),
                    "unread":  "UNREAD" in labels,
                    "url":     f"https://mail.google.com/mail/u/0/#inbox/{msg_id}",
                })

        return JSONResponse({"emails": emails})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error en /inbox: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

# ── Calendar ──────────────────────────────────────────────────────────────────
@app.get("/calendar")
async def get_calendar(token: str = Depends(verify_token)):
    try:
        now  = datetime.now(timezone.utc).isoformat()
        resp = await _gapi_get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            token,
            params={
                "timeMin":      now,
                "maxResults":   15,
                "singleEvents": "true",
                "orderBy":      "startTime",
            },
        )
        if resp.status_code != 200:
            return JSONResponse({"error": resp.text}, status_code=resp.status_code)

        events = []
        for item in resp.json().get("items", []):
            start = item.get("start", {})
            end   = item.get("end",   {})
            events.append({
                "id":       item.get("id"),
                "title":    item.get("summary", "(sin título)"),
                "start":    start.get("dateTime") or start.get("date"),
                "end":      end.get("dateTime")   or end.get("date"),
                "location": item.get("location", ""),
                "url":      item.get("htmlLink", ""),
                "all_day":  "dateTime" not in start,
            })
        return JSONResponse({"events": events})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error en /calendar: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
