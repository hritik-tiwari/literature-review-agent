from __future__ import annotations

import json

from google import genai


class GeminiJSONClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate_json(self, prompt: str, payload: dict) -> dict:
        response = self.client.models.generate_content(
            model=self.model,
            contents=f"{prompt}\n\nINPUT:\n{json.dumps(payload, ensure_ascii=True, indent=2)}",
        )
        text = self._clean_json_text(response.text.strip())
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model did not return valid JSON: {text}") from exc

    def generate_text(self, prompt: str, payload: dict) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=f"{prompt}\n\nINPUT:\n{json.dumps(payload, ensure_ascii=True, indent=2)}",
        )
        return response.text.strip()

    @staticmethod
    def _clean_json_text(text: str) -> str:
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return text
