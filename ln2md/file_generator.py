from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


class FileGenerationError(Exception):
    """Raised when deterministic skill markdown generation fails."""


REQUIRED_KEYS = ("skills", "tools", "domains")
SECTIONS = (
    "Skill Summary",
    "Core Competencies",
    "Tools and Technologies",
    "Practical Experience",
    "Automation Opportunities",
    "Related Skills",
)


def build_profile_index(extracted_data: dict[str, list[str]]) -> dict[str, list[str]]:
    """
    Build a deterministic profile discovery index:
    {
      "skills": [...],
      "tools": [...],
      "domains": [...]
    }
    """
    normalized = _normalize_extracted_data(extracted_data)

    return {
        "skills": _to_slug_list(normalized["skills"]),
        "tools": _to_slug_list(normalized["tools"]),
        "domains": _to_slug_list(normalized["domains"]),
    }


def generate_profile_json(
    extracted_data: dict[str, list[str]],
    output_path: str | Path = "ln2md/profile.json",
) -> Path:
    """
    Generate the profile.json discovery entrypoint for AI agents.
    """
    profile_index = build_profile_index(extracted_data)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(profile_index, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def generate_skill_files(
    extracted_data: dict[str, list[str]],
    output_root: str | Path = "ln2md",
    clear_existing: bool = True,
) -> list[Path]:
    """
    Generate deterministic skill markdown files at:
    ln2md/skills/<skill>.md

    Args:
        extracted_data: Expected shape:
            {
                "skills": [...],
                "tools": [...],
                "domains": [...]
            }
        output_root: Root output directory. Defaults to "ln2md".
        clear_existing: Remove existing .md files in skills/ before writing.

    Returns:
        A sorted list of generated markdown file paths.
    """
    normalized = _normalize_extracted_data(extracted_data)
    skills_dir = Path(output_root) / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    if clear_existing:
        for old_file in sorted(skills_dir.glob("*.md")):
            old_file.unlink()

    slug_counts: dict[str, int] = {}
    generated_paths: list[Path] = []

    for skill_name in normalized["skills"]:
        slug = _unique_slug(skill_name, slug_counts)
        target_path = skills_dir / f"{slug}.md"

        markdown = build_skill_markdown(
            skill_name=skill_name,
            category="technical",
            level="intermediate",
            depends_on=[],
            tools=[],
            domains=[],
        )
        target_path.write_text(markdown, encoding="utf-8")
        generated_paths.append(target_path)

    return sorted(generated_paths, key=lambda p: p.name.lower())


def build_skill_markdown(
    skill_name: str,
    category: str = "technical",
    level: str = "intermediate",
    depends_on: list[str] | None = None,
    tools: list[str] | None = None,
    domains: list[str] | None = None,
) -> str:
    """
    Build deterministic markdown content for one skill file.
    """
    clean_skill = _clean_value(skill_name)
    if not clean_skill:
        raise FileGenerationError("Skill name cannot be empty.")

    clean_category = _clean_value(category) or "technical"
    clean_level = _clean_value(level) or "intermediate"
    clean_depends_on = _normalize_items(depends_on or [])
    clean_tools = _normalize_items(tools or [])
    clean_domains = _normalize_items(domains or [])

    lines: list[str] = [
        "---",
        f"skill: {_yaml_string(clean_skill)}",
        f"category: {_yaml_string(clean_category)}",
        f"level: {_yaml_string(clean_level)}",
        f"depends_on: {_yaml_list(clean_depends_on)}",
        f"tools: {_yaml_list(clean_tools)}",
        f"domains: {_yaml_list(clean_domains)}",
        "---",
        "",
    ]

    for section in SECTIONS:
        lines.append(f"## {section}")
        lines.append(f"- N/A ({section})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _normalize_extracted_data(extracted_data: dict[str, list[str]]) -> dict[str, list[str]]:
    if not isinstance(extracted_data, dict):
        raise FileGenerationError("Input must be a dictionary with skills/tools/domains arrays.")

    missing = [key for key in REQUIRED_KEYS if key not in extracted_data]
    if missing:
        raise FileGenerationError(f"Missing required keys: {', '.join(missing)}")

    normalized: dict[str, list[str]] = {}
    for key in REQUIRED_KEYS:
        value = extracted_data.get(key, [])
        if value is None:
            value = []
        if not isinstance(value, list):
            raise FileGenerationError(f"Field '{key}' must be a list of strings.")
        normalized[key] = _normalize_items(value)
    return normalized


def _normalize_items(values: Iterable[str]) -> list[str]:
    clean_map: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str):
            raise FileGenerationError("All items must be strings.")
        clean = _clean_value(value)
        if clean:
            clean_map[clean.casefold()] = clean
    return sorted(clean_map.values(), key=str.casefold)


def _unique_slug(skill_name: str, slug_counts: dict[str, int]) -> str:
    base_slug = _slugify(skill_name)
    count = slug_counts.get(base_slug, 0) + 1
    slug_counts[base_slug] = count
    if count == 1:
        return base_slug
    return f"{base_slug}-{count}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold().strip())
    slug = slug.strip("-")
    return slug or "skill"


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _to_slug_list(values: list[str]) -> list[str]:
    slug_map: dict[str, str] = {}
    for value in values:
        slug = _slugify(value)
        if slug:
            slug_map[slug] = slug
    return sorted(slug_map.values(), key=str.casefold)


def _yaml_string(value: str) -> str:
    # JSON string format is valid YAML and deterministic.
    return json.dumps(value, ensure_ascii=True)


def _yaml_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=True)
