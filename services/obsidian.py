import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "./vault/Inbox"))

def save_note(parsed: dict) -> str:
    VAULT_PATH.mkdir(parents=True, exist_ok=True)

    title = parsed.get("TITLE", "Untitled").replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{title}.md"
    filepath = VAULT_PATH / filename

    content = f"""# {parsed.get('TITLE', 'Untitled')}

**Summary:** {parsed.get('SUMMARY', '')}

**Insights:** {parsed.get('INSIGHTS', '')}

**Actions:** {parsed.get('ACTIONS', 'None')}
"""

    filepath.write_text(content, encoding="utf-8")
    return str(filepath)
