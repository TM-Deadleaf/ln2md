from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ln2md.schemas import AGENT_COMPATIBILITY_SCHEMA
from ln2md.schemas import ENTITY_SECTIONS
from ln2md.schemas import SCHEMA_VERSION


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]


def get_agent_compatibility_schema() -> dict[str, Any]:
    return AGENT_COMPATIBILITY_SCHEMA


def validate_ai_profile_structure(base_dir: str | Path = "ln2md") -> ValidationResult:
    """
    Validate ln2md outputs for AI-agent compatibility.
    """
    root = Path(base_dir)
    errors: list[str] = []

    profile_path = root / "profile.json"
    graph_path = root / "graph.json"
    skills_dir = root / "skills"
    tools_dir = root / "tools"
    domains_dir = root / "domains"

    for file_path in (profile_path, graph_path):
        if not file_path.exists():
            errors.append(f"Missing required file: {file_path}")
        elif not file_path.is_file():
            errors.append(f"Expected file but got non-file path: {file_path}")

    for dir_path in (skills_dir, tools_dir, domains_dir):
        if not dir_path.exists():
            errors.append(f"Missing required directory: {dir_path}")
        elif not dir_path.is_dir():
            errors.append(f"Expected directory but got non-directory path: {dir_path}")

    profile: dict[str, Any] | None = None
    graph: dict[str, Any] | None = None

    if profile_path.exists() and profile_path.is_file():
        profile = _read_json_object(profile_path, errors)
    if graph_path.exists() and graph_path.is_file():
        graph = _read_json_object(graph_path, errors)

    index_ids: dict[str, set[str]] = {"skill": set(), "tool": set(), "domain": set()}
    index_files: dict[str, set[str]] = {"skill": set(), "tool": set(), "domain": set()}

    if profile is not None:
        _validate_profile(profile, root, errors, index_ids, index_files)

    markdown_ids: dict[str, set[str]] = {
        "skill": _validate_entity_markdown_folder(skills_dir, "skill", errors),
        "tool": _validate_entity_markdown_folder(tools_dir, "tool", errors),
        "domain": _validate_entity_markdown_folder(domains_dir, "domain", errors),
    }

    for entity_type in ("skill", "tool", "domain"):
        extra_from_index = sorted(index_ids[entity_type] - markdown_ids[entity_type])
        extra_from_markdown = sorted(markdown_ids[entity_type] - index_ids[entity_type])

        if extra_from_index:
            errors.append(
                f"profile.json {entity_type}s missing markdown files for ids: {', '.join(extra_from_index)}"
            )
        if extra_from_markdown:
            errors.append(
                f"Markdown {entity_type}s missing in profile.json index ids: {', '.join(extra_from_markdown)}"
            )

    if graph is not None:
        _validate_graph(graph, profile, index_ids, errors)

    return ValidationResult(is_valid=(len(errors) == 0), errors=errors)


def format_validation_result(result: ValidationResult) -> str:
    if result.is_valid:
        return "Validation successful"
    lines = ["Validation failed:"]
    for i, error in enumerate(result.errors, start=1):
        lines.append(f"{i}. {error}")
    return "\n".join(lines)


def _validate_profile(
    profile: dict[str, Any],
    root: Path,
    errors: list[str],
    index_ids: dict[str, set[str]],
    index_files: dict[str, set[str]],
) -> None:
    required_keys = {
        "schema_version",
        "profile_id",
        "name",
        "headline",
        "summary",
        "source",
        "text_sha256",
        "skills",
        "tools",
        "domains",
    }
    missing = sorted(required_keys - set(profile.keys()))
    if missing:
        errors.append(f"profile.json missing keys: {', '.join(missing)}")
        return

    if profile.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"profile.json schema_version must be {SCHEMA_VERSION!r}, got {profile.get('schema_version')!r}"
        )

    profile_id = str(profile.get("profile_id", "")).strip()
    if not _is_slug(profile_id):
        errors.append("profile.json profile_id must be kebab-case (e.g. tanishq-mishra).")

    text_sha = str(profile.get("text_sha256", "")).strip()
    if not re.fullmatch(r"[a-f0-9]{64}", text_sha):
        errors.append("profile.json text_sha256 must be a lowercase 64-char hex sha256.")

    source = profile.get("source")
    if not isinstance(source, dict):
        errors.append("profile.json source must be an object.")
    else:
        if not isinstance(source.get("type"), str):
            errors.append("profile.json source.type must be a string.")
        if not isinstance(source.get("ref"), str):
            errors.append("profile.json source.ref must be a string.")

    _validate_index_collection(
        profile=profile,
        key="skills",
        entity_type="skill",
        root=root,
        errors=errors,
        index_ids=index_ids,
        index_files=index_files,
    )
    _validate_index_collection(
        profile=profile,
        key="tools",
        entity_type="tool",
        root=root,
        errors=errors,
        index_ids=index_ids,
        index_files=index_files,
    )
    _validate_index_collection(
        profile=profile,
        key="domains",
        entity_type="domain",
        root=root,
        errors=errors,
        index_ids=index_ids,
        index_files=index_files,
    )


def _validate_index_collection(
    profile: dict[str, Any],
    key: str,
    entity_type: str,
    root: Path,
    errors: list[str],
    index_ids: dict[str, set[str]],
    index_files: dict[str, set[str]],
) -> None:
    value = profile.get(key)
    if not isinstance(value, list):
        errors.append(f"profile.json {key} must be a list.")
        return

    expected_prefix = f"{key}/"
    for item in value:
        if not isinstance(item, dict):
            errors.append(f"profile.json {key} entries must be objects.")
            continue

        item_id = str(item.get("id", "")).strip()
        item_name = item.get("name")
        item_file = str(item.get("file", "")).strip()

        if not _is_slug(item_id):
            errors.append(f"profile.json {key} item id must be kebab-case, got {item_id!r}.")
            continue
        if not isinstance(item_name, str) or not item_name.strip():
            errors.append(f"profile.json {key} item {item_id!r} missing non-empty name.")
        if not item_file.startswith(expected_prefix) or not item_file.endswith(".md"):
            errors.append(
                f"profile.json {key} item {item_id!r} file must start with {expected_prefix!r} and end in .md."
            )

        file_path = root / item_file
        if not file_path.exists() or not file_path.is_file():
            errors.append(f"profile.json {key} item {item_id!r} references missing file: {item_file}")

        index_ids[entity_type].add(item_id)
        index_files[entity_type].add(item_file)

    normalized = [entry.get("id", "") for entry in value if isinstance(entry, dict)]
    if normalized != sorted(normalized):
        errors.append(f"profile.json {key} must be sorted by id for deterministic output.")


def _validate_entity_markdown_folder(directory: Path, entity_type: str, errors: list[str]) -> set[str]:
    ids: set[str] = set()
    if not directory.exists() or not directory.is_dir():
        return ids

    files = sorted(directory.glob("*.md"))
    if entity_type == "skill" and not files:
        errors.append("skills folder must contain at least one .md file.")
        return ids

    for file_path in files:
        file_id = _slugify(file_path.stem)
        if not file_id:
            errors.append(f"Invalid markdown filename: {file_path.name}")
            continue
        ids.add(file_id)
        _validate_entity_markdown_file(file_path, expected_type=entity_type, expected_id=file_id, errors=errors)
    return ids


def _validate_entity_markdown_file(
    file_path: Path,
    expected_type: str,
    expected_id: str,
    errors: list[str],
) -> None:
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        errors.append(f"Could not read markdown file {file_path}: {exc}")
        return

    frontmatter = _extract_frontmatter(content)
    if frontmatter is None:
        errors.append(f"{file_path} missing YAML frontmatter.")
        return

    metadata, metadata_error = _parse_frontmatter(frontmatter)
    if metadata_error:
        errors.append(f"{file_path} has invalid YAML frontmatter: {metadata_error}")
        return

    required = {"id", "name", "type", "category", "level", "depends_on", "tools", "domains"}
    missing = sorted(required - set(metadata.keys()))
    if missing:
        errors.append(f"{file_path} missing frontmatter keys: {', '.join(missing)}")

    if str(metadata.get("id", "")).strip() != expected_id:
        errors.append(f"{file_path} frontmatter id must match filename id {expected_id!r}.")
    if str(metadata.get("type", "")).strip() != expected_type:
        errors.append(f"{file_path} frontmatter type must be {expected_type!r}.")
    if not isinstance(metadata.get("name"), str) or not str(metadata.get("name", "")).strip():
        errors.append(f"{file_path} frontmatter name must be non-empty string.")

    for list_key in ("depends_on", "tools", "domains"):
        value = metadata.get(list_key)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            errors.append(f"{file_path} frontmatter {list_key} must be list[str].")

    for section in ENTITY_SECTIONS:
        section_header = f"## {section}"
        if section_header not in content:
            errors.append(f"{file_path} missing required section: {section_header}")


def _validate_graph(
    graph: dict[str, Any],
    profile: dict[str, Any] | None,
    index_ids: dict[str, set[str]],
    errors: list[str],
) -> None:
    if not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        errors.append("graph.json must contain nodes and edges arrays.")
        return

    nodes = graph["nodes"]
    edges = graph["edges"]

    node_map: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("graph.json nodes must contain objects only.")
            continue
        node_id = str(node.get("id", "")).strip()
        node_type = str(node.get("type", "")).strip()
        label = str(node.get("label", "")).strip()
        if not node_id:
            errors.append("graph.json node missing id.")
            continue
        if node_id in node_map:
            errors.append(f"graph.json duplicate node id: {node_id}")
        node_map[node_id] = node
        if node_type not in {"profile", "skill", "tool", "domain"}:
            errors.append(f"graph.json node {node_id} has invalid type {node_type!r}.")
        if not label:
            errors.append(f"graph.json node {node_id} has empty label.")

    for edge in edges:
        if not isinstance(edge, dict):
            errors.append("graph.json edges must contain objects only.")
            continue
        source = str(edge.get("source", "")).strip()
        target = str(edge.get("target", "")).strip()
        relation = str(edge.get("relation", "")).strip()

        if source not in node_map or target not in node_map:
            errors.append(f"graph.json edge references unknown nodes: {source} -> {target}")
            continue
        if relation not in {"HAS_SKILL", "USES_TOOL", "WORKS_IN_DOMAIN"}:
            errors.append(f"graph.json edge has invalid relation {relation!r}.")

    if profile is None:
        return

    profile_node_id = f"profile:{profile.get('profile_id', '')}"
    if profile_node_id not in node_map:
        errors.append(f"graph.json missing profile node id: {profile_node_id}")

    expected_skill_nodes = {f"skill:{item_id}" for item_id in index_ids["skill"]}
    expected_tool_nodes = {f"tool:{item_id}" for item_id in index_ids["tool"]}
    expected_domain_nodes = {f"domain:{item_id}" for item_id in index_ids["domain"]}

    missing_nodes = sorted((expected_skill_nodes | expected_tool_nodes | expected_domain_nodes) - set(node_map))
    if missing_nodes:
        errors.append(f"graph.json missing expected nodes: {', '.join(missing_nodes)}")


def _read_json_object(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in {path}: {exc}")
        return None
    except Exception as exc:
        errors.append(f"Could not read JSON file {path}: {exc}")
        return None

    if not isinstance(payload, dict):
        errors.append(f"JSON root in {path} must be an object.")
        return None
    return payload


def _extract_frontmatter(markdown_text: str) -> str | None:
    lines = markdown_text.splitlines()
    if not lines:
        return None
    if not _is_delimiter(lines[0].strip()):
        return None

    end_index = None
    for i in range(1, len(lines)):
        if _is_delimiter(lines[i].strip()):
            end_index = i
            break
    if end_index is None:
        return None
    return "\n".join(lines[1:end_index]).strip()


def _parse_frontmatter(frontmatter_text: str) -> tuple[dict[str, Any], str | None]:
    try:
        import yaml  # type: ignore
    except Exception:
        yaml = None

    if yaml is not None:
        try:
            data = yaml.safe_load(frontmatter_text)
        except Exception as exc:
            return {}, str(exc)
        if not isinstance(data, dict):
            return {}, "YAML frontmatter must be an object."
        return data, None

    # Fallback parser for simple key/value with inline lists.
    parsed: dict[str, Any] = {}
    for raw_line in frontmatter_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            return {}, f"Invalid frontmatter line: {raw_line}"
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            return {}, f"Invalid frontmatter key line: {raw_line}"

        if value.startswith("["):
            list_value = _parse_inline_list(value)
            if list_value is None:
                return {}, f"Invalid inline list for key {key!r}"
            parsed[key] = list_value
        else:
            parsed[key] = _strip_quotes(value)
    return parsed, None


def _parse_inline_list(value: str) -> list[str] | None:
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            return list(parsed)
    except Exception:
        pass
    try:
        parsed = ast.literal_eval(value)
        if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            return list(parsed)
    except Exception:
        return None
    return None


def _strip_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _is_delimiter(line: str) -> bool:
    return bool(re.fullmatch(r"-{3,}", line))


def _is_slug(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value))


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold().strip()).strip("-")

