from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"
DEFAULT_RETRY_COUNT = 3

SYSTEM_INSTRUCTION = """
You extract structured technical knowledge from developer profile text.

Return valid JSON only.
Do not wrap the JSON in markdown fences.
Do not include commentary, explanations, or extra keys.
The response schema is exactly:
{
  "skills": ["..."],
  "tools": ["..."],
  "domains": ["..."]
}

Rules:
- All values must be arrays of strings.
- Use concise canonical names.
- Deduplicate entries.
- Sort each array alphabetically.
- Only include items strongly supported by the profile text.
- If nothing is found for a category, return an empty array.
""".strip()


class SkillExtractionError(Exception):
    """Raised when structured skill extraction fails."""


def extract_skills(profile_text: str) -> dict[str, list[str]]:
    """
    Extract technical skills, tools, and domains from profile text using Gemini.

    Args:
        profile_text: Resume/profile text to analyze.

    Returns:
        A strict JSON-compatible dictionary with keys: skills, tools, domains.

    Raises:
        SkillExtractionError: If the API key is missing, the model call fails, or JSON remains invalid.
    """
    normalized_text = _normalize_profile_text(profile_text)
    if not normalized_text:
        raise SkillExtractionError("Profile text is empty.")

    api_key = _load_api_key()
    model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    try:
        from google import genai
        from google.genai import errors
        from google.genai import types
    except ImportError as exc:
        raise SkillExtractionError(
            "Missing dependency 'google-genai'. Install it before using Gemini extraction."
        ) from exc

    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(normalized_text)

    last_error: Exception | None = None
    for attempt in range(1, DEFAULT_RETRY_COUNT + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
            payload = _parse_response_text(response.text)
            return _normalize_payload(payload)
        except (json.JSONDecodeError, SkillExtractionError) as exc:
            last_error = exc
            if attempt == DEFAULT_RETRY_COUNT:
                break
            time.sleep(0.5 * attempt)
        except errors.ClientError as exc:
            raise SkillExtractionError(f"Gemini API request failed: {exc}") from exc
        except Exception as exc:
            raise SkillExtractionError(f"Unexpected Gemini extraction failure: {exc}") from exc

    raise SkillExtractionError(
        f"Gemini returned malformed JSON after {DEFAULT_RETRY_COUNT} attempts."
    ) from last_error


def _load_api_key() -> str:
    _load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SkillExtractionError(
            "Missing GEMINI_API_KEY. Add it to the project .env file before running extraction."
        )
    return api_key


def _load_dotenv() -> None:
    dotenv_path = Path(".env")
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _build_prompt(profile_text: str) -> str:
    return (
        f"{SYSTEM_INSTRUCTION}\n\n"
        "Profile text:\n"
        '"""\n'
        f"{profile_text[:16000]}\n"
        '"""'
    )


def _parse_response_text(raw_text: str) -> dict[str, Any]:
    if not raw_text or not raw_text.strip():
        raise SkillExtractionError("Gemini returned an empty response.")

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise SkillExtractionError("Gemini response must be a JSON object.")
    return payload


def _normalize_payload(payload: dict[str, Any]) -> dict[str, list[str]]:
    required_keys = ("skills", "tools", "domains")
    normalized: dict[str, list[str]] = {}

    for key in required_keys:
        raw_value = payload.get(key, [])
        if raw_value is None:
            raw_value = []
        if not isinstance(raw_value, list):
            raise SkillExtractionError(f"Field '{key}' must be a JSON array.")

        cleaned_items = []
        for item in raw_value:
            if not isinstance(item, str):
                raise SkillExtractionError(f"Field '{key}' must only contain strings.")
            cleaned = " ".join(item.split()).strip()
            if cleaned:
                cleaned_items.append(cleaned)

        normalized[key] = sorted(set(cleaned_items), key=str.lower)

    extra_keys = set(payload.keys()) - set(required_keys)
    if extra_keys:
        raise SkillExtractionError(
            f"Gemini response contains unexpected keys: {', '.join(sorted(extra_keys))}"
        )

    return normalized


def _normalize_profile_text(profile_text: str) -> str:
    return "\n".join(line.strip() for line in profile_text.splitlines() if line.strip()).strip()
