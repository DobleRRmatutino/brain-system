import os
from notion_client import Client
from dotenv import load_dotenv
load_dotenv()

notion = Client(auth=os.getenv("NOTION_TOKEN"))
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def save_to_notion(data: dict, original_content: str = "") -> str:
    children = []

    if data.get("summary"):
        children.append({"object": "block", "type": "callout", "callout": {
            "rich_text": [{"type": "text", "text": {"content": data["summary"]}}],
            "icon": {"emoji": "📝"}
        }})

    if data.get("insights"):
        children.append({"object": "block", "type": "callout", "callout": {
            "rich_text": [{"type": "text", "text": {"content": data["insights"]}}],
            "icon": {"emoji": "💡"}
        }})

    if data.get("actions"):
        children.append({"object": "block", "type": "callout", "callout": {
            "rich_text": [{"type": "text", "text": {"content": data["actions"]}}],
            "icon": {"emoji": "⚡"}
        }})

    if data.get("tags"):
        tags_text = "  ".join(["#" + t for t in data["tags"]])
        children.append({"object": "block", "type": "callout", "callout": {
            "rich_text": [{"type": "text", "text": {"content": tags_text}}],
            "icon": {"emoji": "🏷️"}
        }})

    children.append({"object": "block", "type": "divider", "divider": {}})

    if original_content:
        for line in original_content.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("# "):
                children.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
            elif line.startswith("## "):
                children.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:]}}]}})
            elif line.startswith("### "):
                children.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:]}}]}})
            elif line.startswith("- [ ] ") or line.startswith("* [ ] "):
                children.append({"object": "block", "type": "to_do", "to_do": {"rich_text": [{"type": "text", "text": {"content": line[6:]}}], "checked": False}})
            elif line.startswith("- [x] ") or line.startswith("* [x] "):
                children.append({"object": "block", "type": "to_do", "to_do": {"rich_text": [{"type": "text", "text": {"content": line[6:]}}], "checked": True}})
            elif line.startswith("- ") or line.startswith("* "):
                children.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
            else:
                children.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}})

    properties = {
        "Name": {"title": [{"text": {"content": data.get("title", "Untitled")}}]},
        "Type": {"select": {"name": data.get("type", "KNOWLEDGE")}},
        "Summary": {"rich_text": [{"text": {"content": data.get("summary", "")}}]},
        "Tags": {"multi_select": [{"name": t} for t in data.get("tags", [])]},
        "Status": {"select": {"name": data.get("status", "INBOX")}},
    }

    if data.get("actions"):
        properties["Actions"] = {"rich_text": [{"text": {"content": data["actions"]}}]}
    if data.get("insights"):
        properties["Insights"] = {"rich_text": [{"text": {"content": data["insights"]}}]}

    response = notion.pages.create(
        parent={"database_id": DATABASE_ID},
        properties=properties,
        children=children
    )
    return response["url"]
