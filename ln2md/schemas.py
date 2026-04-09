from __future__ import annotations

SCHEMA_VERSION = "1.0.0"

ENTITY_SECTIONS = (
    "Skill Summary",
    "Core Competencies",
    "Tools and Technologies",
    "Practical Experience",
    "Automation Opportunities",
    "Related Skills",
)

FOLDER_STRUCTURE = {
    "root": "ln2md/",
    "required_files": ["profile.json", "graph.json"],
    "required_directories": {
        "skills": "skills/*.md",
        "tools": "tools/*.md",
        "domains": "domains/*.md",
    },
}

MARKDOWN_FRONTMATTER_SCHEMA = {
    "type": "object",
    "required": [
        "id",
        "name",
        "type",
        "category",
        "level",
        "depends_on",
        "tools",
        "domains",
    ],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
        "name": {"type": "string", "minLength": 1},
        "type": {"type": "string", "enum": ["skill", "tool", "domain"]},
        "category": {"type": "string"},
        "level": {"type": "string"},
        "depends_on": {"type": "array", "items": {"type": "string"}},
        "tools": {"type": "array", "items": {"type": "string"}},
        "domains": {"type": "array", "items": {"type": "string"}},
    },
}

PROFILE_INDEX_SCHEMA = {
    "type": "object",
    "required": [
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
    ],
    "properties": {
        "schema_version": {"type": "string", "const": SCHEMA_VERSION},
        "profile_id": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
        "name": {"type": "string"},
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "source": {
            "type": "object",
            "required": ["type", "ref"],
            "properties": {
                "type": {"type": "string"},
                "ref": {"type": "string"},
            },
        },
        "text_sha256": {
            "type": "string",
            "pattern": "^[a-f0-9]{64}$",
        },
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "name", "file"],
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
                    "name": {"type": "string"},
                    "file": {"type": "string", "pattern": "^skills/.+\\.md$"},
                },
            },
        },
        "tools": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "name", "file"],
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
                    "name": {"type": "string"},
                    "file": {"type": "string", "pattern": "^tools/.+\\.md$"},
                },
            },
        },
        "domains": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "name", "file"],
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
                    "name": {"type": "string"},
                    "file": {"type": "string", "pattern": "^domains/.+\\.md$"},
                },
            },
        },
    },
}

GRAPH_SCHEMA = {
    "type": "object",
    "required": ["nodes", "edges"],
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "type", "label"],
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": ["profile", "skill", "tool", "domain"]},
                    "label": {"type": "string"},
                },
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source", "target", "relation"],
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "relation": {
                        "type": "string",
                        "enum": ["HAS_SKILL", "USES_TOOL", "WORKS_IN_DOMAIN"],
                    },
                },
            },
        },
    },
}

AGENT_COMPATIBILITY_SCHEMA = {
    "schema_version": SCHEMA_VERSION,
    "folder_structure": FOLDER_STRUCTURE,
    "profile_json_schema": PROFILE_INDEX_SCHEMA,
    "graph_json_schema": GRAPH_SCHEMA,
    "markdown_frontmatter_schema": MARKDOWN_FRONTMATTER_SCHEMA,
    "required_markdown_sections": list(ENTITY_SECTIONS),
}
