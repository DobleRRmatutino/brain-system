import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def home():
    return open(os.path.join(os.path.dirname(__file__), "index.html")).read()

@app.post("/process")
async def handle(request: Request):
    try:
        from main import process
        body = await request.json()
        content = body.get("content", "")
        result = process(content)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/chat")
async def chat(request: Request):
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
async def delete_notion(request: Request):
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
async def reprocess(request: Request):
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
