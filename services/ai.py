import os
import google.genai as genai
from dotenv import load_dotenv
load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PROMPT_TEMPLATE = """
You are a personal knowledge assistant. Analyze the following note and extract metadata.
Do NOT rewrite the content. ALWAYS respond in Spanish. All text values in the JSON (title, summary, actions, insights) MUST be written in Spanish.
Return a JSON object with this exact structure:

{{
  "title": "título claro y conciso",
    "type": "KNOWLEDGE or BUSINESS",
      "summary": "resumen de 2-3 oraciones",
        "tags": ["tag1", "tag2", "tag3"],
          "actions": "próximos pasos concretos si los hay, o null",
            "insights": "idea clave o aprendizaje en 1-2 oraciones, o null",
              "status": "INBOX"
}}

Rules:
- type: BUSINESS for work/projects/meetings, KNOWLEDGE for learning/ideas/personal
- tags: 3-5 relevant lowercase tags
- actions: specific actionable tasks, or null if none
- insights: most important thing to remember, or null

Return ONLY valid JSON, no extra text, no markdown backticks.

Raw note:
{content}
"""

def process_note(content: str) -> str:
      prompt = PROMPT_TEMPLATE.format(content=content)
      response = client.models.generate_content(
          model="gemini-2.5-flash",
          contents=prompt
      )
      return response.text.strip()
