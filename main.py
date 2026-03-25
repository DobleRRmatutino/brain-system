import sys
import json
from services.ai import process_note
from services.notion import save_to_notion
from utils.logger import get_logger

logger = get_logger()

def process(content: str):
    logger.info(f"Processing note ({len(content)} chars)")
    raw = process_note(content)
    logger.debug(f"AI response: {raw}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
    logger.info(f"Title: {data.get('title')} | Type: {data.get('type')}")
    url = save_to_notion(data, original_content=content)
    logger.info(f"Notion page created: {url}")
    data["url"] = url
    return data

if __name__ == "__main__":
    if len(sys.argv) > 1:
        import pathlib
        path = pathlib.Path(sys.argv[1])
        content = path.read_text(encoding="utf-8")
    else:
        content = input("Paste note content:\n")
    result = process(content)
    print(f"\n✅ {result['title']} → Notion")
