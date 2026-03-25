import os

# Vault path - Windows via WSL
VAULT_PATH = "/mnt/c/Users/Diego/brain-system/vault"
INBOX_PATH = os.path.join(VAULT_PATH, "Inbox")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

# Notion
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
