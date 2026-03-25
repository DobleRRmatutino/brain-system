import sys
import os
import secrets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

app = FastAPI()

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
        question = body.get("question", "")
        context = body.get("context", "")
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        ctx_block = f"NOTAS DE CONTEXTO:\n{context}" if context else "No hay notas seleccionadas."
        prompt = f"Eres un asistente personal. Responde SOLO basándote en las notas.\n\n{ctx_block}\n\nPREGUNTA: {question}"
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
