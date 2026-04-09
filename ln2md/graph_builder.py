from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"
DEFAULT_RETRY_COUNT = 3

SYSTEM_INSTRUCTION = """
You infer directed technical skill relationships.

Return STRICT JSON only.
Do not return markdown.
Do not include explanations.
Do not include extra keys.

Output schema:
{
  "<skill-id>": {
    "depends_on": ["<skill-id>", "..."],
    "tools": ["<tool>", "..."]
  }
}

Rules:
- skill-id keys must come only from the provided skill IDs.
- depends_on must only reference provided skill IDs.
- No self-dependency.
- Prefer 0-3 dependencies per skill.
- Keep tools concise and lowercase.
- Sort each array alphabetically.
""".strip()


class GraphBuildError(Exception):
    """Raised when graph generation fails."""


def build_skill_graph(
    skills: list[str],
    output_path: str | Path = "graph.json",
    model: str | None = None,
) -> dict[str, dict[str, list[str]]]:
    """
    Build a deterministic skill relationship graph and save it to graph.json.

    Args:
        skills: List of skill names.
        output_path: JSON output path. Defaults to graph.json.
        model: Optional model override.

    Returns:
        Graph dictionary:
        {
          "<skill-id>": {
            "depends_on": [...],
            "tools": [...]
          }
        }
    """
    normalized = _normalize_skills(skills)
    if not normalized:
        raise GraphBuildError("Skills list is empty.")

    skill_ids = [item["id"] for item in normalized]
    skill_id_set = set(skill_ids)
    alias_map = _build_alias_map(normalized)

    payload = _infer_graph_with_llm(
        normalized_skills=normalized,
        model_name=(model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL,
    )
    graph = _normalize_graph_payload(payload, skill_ids=skill_ids, skill_id_set=skill_id_set, alias_map=alias_map)
    graph = _remove_circular_dependencies(graph)
    graph = _finalize_graph(graph)
    _write_graph_json(graph, Path(output_path))
    return graph


def _infer_graph_with_llm(normalized_skills: list[dict[str, str]], model_name: str) -> dict[str, Any]:
    api_key = _load_api_key()

    try:
        from google import genai
        from google.genai import errors
        from google.genai import types
    except ImportError as exc:
        raise GraphBuildError(
            "Missing dependency 'google-genai'. Install it before building graph relationships."
        ) from exc

    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(normalized_skills)

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
            return _parse_json_response(response.text)
        except (json.JSONDecodeError, GraphBuildError) as exc:
            last_error = exc
            if attempt == DEFAULT_RETRY_COUNT:
                break
            time.sleep(0.5 * attempt)
        except errors.ClientError as exc:
            raise GraphBuildError(f"Gemini API request failed: {exc}") from exc
        except Exception as exc:
            raise GraphBuildError(f"Unexpected Gemini graph inference failure: {exc}") from exc

    raise GraphBuildError(
        f"Gemini returned malformed graph JSON after {DEFAULT_RETRY_COUNT} attempts."
    ) from last_error


def _build_prompt(normalized_skills: list[dict[str, str]]) -> str:
    skill_block = "\n".join(f"- {item['id']}: {item['name']}" for item in normalized_skills)
    return (
        f"{SYSTEM_INSTRUCTION}\n\n"
        "Skill IDs and labels:\n"
        f"{skill_block}\n\n"
        "Return the JSON object now."
    )


def _parse_json_response(raw_text: str) -> dict[str, Any]:
    if not raw_text or not raw_text.strip():
        raise GraphBuildError("Gemini returned an empty response.")

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise GraphBuildError("Gemini output must be a JSON object.")
    return payload


def _normalize_graph_payload(
    payload: dict[str, Any],
    skill_ids: list[str],
    skill_id_set: set[str],
    alias_map: dict[str, str],
) -> dict[str, dict[str, list[str]]]:
    normalized: dict[str, dict[str, list[str]]] = {
        skill_id: {"depends_on": [], "tools": []} for skill_id in sorted(skill_ids)
    }

    for raw_skill_key, raw_value in payload.items():
        skill_id = _resolve_skill_id(str(raw_skill_key), alias_map)
        if not skill_id or skill_id not in skill_id_set:
            continue
        if not isinstance(raw_value, dict):
            continue

        raw_depends = raw_value.get("depends_on", [])
        raw_tools = raw_value.get("tools", [])

        depends = []
        if isinstance(raw_depends, list):
            for item in raw_depends:
                if not isinstance(item, str):
                    continue
                dep_id = _resolve_skill_id(item, alias_map)
                if dep_id and dep_id in skill_id_set and dep_id != skill_id:
                    depends.append(dep_id)

        tools = []
        if isinstance(raw_tools, list):
            for item in raw_tools:
                if not isinstance(item, str):
                    continue
                tool = _normalize_tool_name(item)
                if tool:
                    tools.append(tool)

        normalized[skill_id]["depends_on"] = sorted(set(depends))
        normalized[skill_id]["tools"] = sorted(set(tools))

    return normalized


def _remove_circular_dependencies(
    graph: dict[str, dict[str, list[str]]]
) -> dict[str, dict[str, list[str]]]:
    """
    Remove back-edges discovered by DFS in deterministic node/dependency order.
    """
    cleaned = {
        node: {
            "depends_on": list(values["depends_on"]),
            "tools": list(values["tools"]),
        }
        for node, values in sorted(graph.items(), key=lambda x: x[0])
    }

    state: dict[str, int] = {node: 0 for node in cleaned}

    def visit(node: str) -> None:
        state[node] = 1
        for dep in list(cleaned[node]["depends_on"]):
            if dep not in cleaned:
                cleaned[node]["depends_on"].remove(dep)
                continue
            if state[dep] == 0:
                visit(dep)
            elif state[dep] == 1:
                # Remove edge that closes the cycle.
                cleaned[node]["depends_on"].remove(dep)
        state[node] = 2

    for node in sorted(cleaned):
        if state[node] == 0:
            visit(node)

    return cleaned


def _finalize_graph(graph: dict[str, dict[str, list[str]]]) -> dict[str, dict[str, list[str]]]:
    finalized: dict[str, dict[str, list[str]]] = {}
    for node in sorted(graph):
        finalized[node] = {
            "depends_on": sorted(set(graph[node]["depends_on"])),
            "tools": sorted(set(graph[node]["tools"])),
        }
    return finalized


def _write_graph_json(graph: dict[str, dict[str, list[str]]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(graph, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_skills(skills: list[str]) -> list[dict[str, str]]:
    if not isinstance(skills, list):
        raise GraphBuildError("skills must be a list of strings.")

    seen: dict[str, str] = {}
    for item in skills:
        if not isinstance(item, str):
            continue
        clean_name = re.sub(r"\s+", " ", item.strip())
        if not clean_name:
            continue
        skill_id = _slugify(clean_name)
        if skill_id not in seen:
            seen[skill_id] = clean_name

    return [{"id": skill_id, "name": seen[skill_id]} for skill_id in sorted(seen)]


def _build_alias_map(normalized_skills: list[dict[str, str]]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for item in normalized_skills:
        skill_id = item["id"]
        name = item["name"]

        candidates = {
            skill_id,
            name,
            name.casefold(),
            name.lower(),
            name.replace("_", "-"),
            name.replace(" ", "-"),
            _slugify(name),
        }
        for candidate in candidates:
            key = candidate.strip().casefold()
            if key:
                alias_map[key] = skill_id
    return alias_map


def _resolve_skill_id(raw_skill: str, alias_map: dict[str, str]) -> str | None:
    if not isinstance(raw_skill, str):
        return None

    candidate = raw_skill.strip()
    if not candidate:
        return None

    keys = [
        candidate.casefold(),
        candidate.replace("_", "-").casefold(),
        candidate.replace(" ", "-").casefold(),
        _slugify(candidate).casefold(),
    ]
    for key in keys:
        if key in alias_map:
            return alias_map[key]
    return None


def _normalize_tool_name(value: str) -> str:
    clean = re.sub(r"\s+", " ", value.strip().lower())
    clean = re.sub(r"[^a-z0-9\-\s./+#]", "", clean)
    clean = clean.replace(" ", "-")
    clean = re.sub(r"-{2,}", "-", clean).strip("-")
    return clean


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold().strip())
    return slug.strip("-") or "skill"


def _load_api_key() -> str:
    _load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GraphBuildError("Missing GEMINI_API_KEY. Add it to .env before building graph.")
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
