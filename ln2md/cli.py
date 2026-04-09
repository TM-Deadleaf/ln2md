from __future__ import annotations

import hashlib
import json
import re
import sys
import traceback
from pathlib import Path
from typing import Any

import typer
from ln2md.schemas import ENTITY_SECTIONS
from ln2md.schemas import SCHEMA_VERSION
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn
from rich.progress import Progress
from rich.progress import SpinnerColumn
from rich.progress import TextColumn
from rich.progress import TimeElapsedColumn
from rich.table import Table

APP_NAME = "ln2md"
DEFAULT_OUTPUT_DIR = Path("ln2md")
STATE_DIR = Path(".ln2md")
STATE_FILE = STATE_DIR / "state.json"

PROFILE_FILE = "profile.json"
GRAPH_FILE = "graph.json"
SKILLS_DIR = "skills"
TOOLS_DIR = "tools"
DOMAINS_DIR = "domains"

app = typer.Typer(
    name=APP_NAME,
    help="Convert developer resumes into deterministic AI-agent-readable knowledge profiles.",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


class CLIError(Exception):
    """Known, user-facing CLI errors."""


def _success_mark() -> str:
    mark = "✔"
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        mark.encode(encoding)
    except Exception:
        return "OK"
    return mark


SUCCESS_MARK = _success_mark()


SKILL_BANK: list[tuple[str, str, str]] = [
    ("python", "Python", "Strong Python development experience."),
    ("java", "Java", "Experience building JVM-based applications."),
    ("golang", "Go", "Experience building services in Go."),
    ("go ", "Go", "Experience building services in Go."),
    ("typescript", "TypeScript", "Typed JavaScript application development."),
    ("javascript", "JavaScript", "Modern JavaScript application development."),
    ("sql", "SQL", "Relational data modeling and query optimization."),
    ("machine learning", "Machine Learning", "Applied ML model development and evaluation."),
    ("system design", "System Design", "Designing scalable distributed systems."),
    ("microservices", "Microservices", "Service-oriented architecture and decomposition."),
]

TOOL_BANK: list[tuple[str, str, str]] = [
    ("docker", "Docker", "Containerized development and deployments."),
    ("kubernetes", "Kubernetes", "Container orchestration in production environments."),
    ("aws", "AWS", "Cloud infrastructure on Amazon Web Services."),
    ("gcp", "GCP", "Cloud infrastructure on Google Cloud Platform."),
    ("azure", "Azure", "Cloud infrastructure on Microsoft Azure."),
    ("git", "Git", "Version control and collaborative workflows."),
    ("postgres", "PostgreSQL", "Relational database operations and tuning."),
    ("redis", "Redis", "Caching and high-throughput data access patterns."),
    ("terraform", "Terraform", "Infrastructure as code provisioning."),
    ("linux", "Linux", "Linux-based deployment and operations."),
]

DOMAIN_BANK: list[tuple[str, str, str]] = [
    ("fintech", "FinTech", "Financial systems and regulated product delivery."),
    ("healthcare", "Healthcare", "Healthcare platforms and data workflows."),
    ("e-commerce", "E-Commerce", "Commerce systems and customer lifecycle flows."),
    ("developer tools", "Developer Tools", "Platforms and workflows for engineers."),
    ("ai", "AI/ML", "Artificial intelligence and machine learning applications."),
    ("ml", "AI/ML", "Artificial intelligence and machine learning applications."),
    ("cloud", "Cloud Infrastructure", "Cloud-native platforms and operations."),
    ("saas", "SaaS", "Software-as-a-service product development."),
]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _yaml_list(values: list[str]) -> str:
    normalized = sorted({item for item in values if isinstance(item, str) and item.strip()})
    return json.dumps(normalized, ensure_ascii=True)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CLIError(f"Invalid JSON in {path}") from exc


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().strip()).strip("-")
    return slug or "item"


def _normalize_text(text: str) -> str:
    normalized_lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            normalized_lines.append(cleaned)
    return "\n".join(normalized_lines).strip()


def _extract_pdf_text(pdf_path: Path) -> str:
    if pdf_path.suffix.lower() != ".pdf":
        raise CLIError("The `pdf` command requires a .pdf file.")

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise CLIError("Missing dependency `pypdf`. Install it with: pip install pypdf") from exc

    try:
        reader = PdfReader(str(pdf_path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise CLIError(f"Failed to parse PDF: {pdf_path}") from exc

    normalized = _normalize_text(text)
    if not normalized:
        raise CLIError("No readable text found in the PDF.")
    return normalized


def _extract_entities(text: str) -> dict[str, list[dict[str, Any]]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lowered = text.lower()

    def extract_from_bank(bank: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for needle, label, description in bank:
            if needle.lower() in lowered:
                evidence = []
                for line in lines:
                    if needle.lower() in line.lower():
                        evidence.append(line[:200])
                evidence = sorted(set(evidence))[:3]
                if not evidence:
                    evidence = ["Mentioned in resume/profile text."]
                found[label.lower()] = {
                    "name": label,
                    "description": description,
                    "evidence": evidence,
                }
        return sorted(found.values(), key=lambda x: x["name"].lower())

    skills = extract_from_bank(SKILL_BANK)
    tools = extract_from_bank(TOOL_BANK)
    domains = extract_from_bank(DOMAIN_BANK)

    if not skills:
        skills = [
            {
                "name": "Software Engineering",
                "description": "General software engineering and problem-solving capability.",
                "evidence": ["Derived from provided resume/profile text."],
            }
        ]

    return {"skills": skills, "tools": tools, "domains": domains}


def _build_profile(
    text: str,
    source_type: str,
    source_ref: str,
    skills: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    domains: list[dict[str, Any]],
) -> dict[str, Any]:
    lines = [line for line in text.splitlines() if line.strip()]
    first = lines[0] if lines else "Unknown"
    second = lines[1] if len(lines) > 1 else ""
    summary = " ".join(lines[2:6]) if len(lines) > 2 else ""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    profile_id = _slugify(first) if first.strip() else "profile"

    return {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile_id,
        "name": first,
        "headline": second,
        "summary": summary,
        "source": {
            "type": source_type,
            "ref": source_ref,
        },
        "text_sha256": digest,
        "skills": [{"id": item["id"], "name": item["name"], "file": item["file"]} for item in skills],
        "tools": [{"id": item["id"], "name": item["name"], "file": item["file"]} for item in tools],
        "domains": [{"id": item["id"], "name": item["name"], "file": item["file"]} for item in domains],
    }


def _build_graph(
    profile: dict[str, Any],
    skills: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    domains: list[dict[str, Any]],
) -> dict[str, Any]:
    profile_node_id = f"profile:{profile['profile_id']}"
    nodes: list[dict[str, Any]] = [
        {"id": profile_node_id, "type": "profile", "label": profile.get("name") or "Unknown"},
    ]
    edges: list[dict[str, Any]] = []

    for skill in skills:
        node_id = f"skill:{skill['id']}"
        nodes.append({"id": node_id, "type": "skill", "label": skill["name"]})
        edges.append({"source": profile_node_id, "target": node_id, "relation": "HAS_SKILL"})

    for tool in tools:
        node_id = f"tool:{tool['id']}"
        nodes.append({"id": node_id, "type": "tool", "label": tool["name"]})
        edges.append({"source": profile_node_id, "target": node_id, "relation": "USES_TOOL"})

    for domain in domains:
        node_id = f"domain:{domain['id']}"
        nodes.append({"id": node_id, "type": "domain", "label": domain["name"]})
        edges.append({"source": profile_node_id, "target": node_id, "relation": "WORKS_IN_DOMAIN"})

    nodes = sorted(nodes, key=lambda n: (n["type"], n["label"].lower(), n["id"]))
    edges = sorted(edges, key=lambda e: (e["relation"], e["source"], e["target"]))
    return {"nodes": nodes, "edges": edges}


def _prepare_output(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for subdir in (SKILLS_DIR, TOOLS_DIR, DOMAINS_DIR):
        directory = output_dir / subdir
        directory.mkdir(parents=True, exist_ok=True)
        for old_file in directory.glob("*.md"):
            old_file.unlink()


def _build_entity_records(folder_name: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used_slugs: dict[str, int] = {}
    records: list[dict[str, Any]] = []

    for item in sorted(entities, key=lambda x: x["name"].lower()):
        base_slug = _slugify(item["name"])
        used_slugs[base_slug] = used_slugs.get(base_slug, 0) + 1
        suffix = "" if used_slugs[base_slug] == 1 else f"-{used_slugs[base_slug]}"
        entity_id = f"{base_slug}{suffix}"
        records.append(
            {
                "id": entity_id,
                "name": item["name"],
                "description": item.get("description", "").strip(),
                "evidence": sorted(set(item.get("evidence", []))),
                "file": f"{folder_name}/{entity_id}.md",
            }
        )
    return sorted(records, key=lambda x: x["id"])


def _entity_category(entity_type: str) -> str:
    if entity_type == "skill":
        return "technical"
    if entity_type == "tool":
        return "tooling"
    return "domain"


def _entity_level(entity_type: str) -> str:
    if entity_type == "skill":
        return "intermediate"
    if entity_type == "tool":
        return "applied"
    return "contextual"


def _render_entity_markdown(entity_type: str, record: dict[str, Any]) -> str:
    lines: list[str] = [
        "---",
        f"id: {_yaml_scalar(record['id'])}",
        f"name: {_yaml_scalar(record['name'])}",
        f"type: {_yaml_scalar(entity_type)}",
        f"category: {_yaml_scalar(_entity_category(entity_type))}",
        f"level: {_yaml_scalar(_entity_level(entity_type))}",
        "depends_on: []",
        "tools: []",
        "domains: []",
        "---",
        "",
    ]

    for section in ENTITY_SECTIONS:
        lines.append(f"## {section}")
        if section == "Skill Summary":
            summary = record.get("description") or "N/A"
            lines.append(f"- {summary}")
        elif section == "Practical Experience":
            evidence = record.get("evidence") or []
            if evidence:
                for item in evidence:
                    lines.append(f"- {item}")
            else:
                lines.append("- N/A")
        else:
            lines.append("- N/A")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _write_markdown_files(
    output_dir: Path,
    folder_name: str,
    entity_type: str,
    records: list[dict[str, Any]],
) -> None:
    folder = output_dir / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    for record in records:
        path = output_dir / record["file"]
        markdown = _render_entity_markdown(entity_type=entity_type, record=record)
        path.write_text(markdown, encoding="utf-8")


def _save_state(payload: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(STATE_FILE, payload)


def _load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        raise CLIError("No cached state found. Run `ln2md pdf <resume.pdf>` or `ln2md paste` first.")
    return _read_json(STATE_FILE)


def _render_summary(output_dir: Path, entities: dict[str, list[dict[str, Any]]]) -> None:
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Artifact")
    table.add_column("Count", justify="right")
    table.add_row("skills/*.md", str(len(entities["skills"])))
    table.add_row("tools/*.md", str(len(entities["tools"])))
    table.add_row("domains/*.md", str(len(entities["domains"])))
    table.add_row("profile.json", "1")
    table.add_row("graph.json", "1")
    console.print(table)
    console.print(f"[dim]Output directory:[/dim] {output_dir.resolve()}")


def _run_step(step_title: str, fn: Any) -> Any:
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=30),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task(step_title, total=1)
        result = fn()
        progress.advance(task_id, 1)
    console.print(f"[bold green]{SUCCESS_MARK}[/bold green] {step_title}")
    return result


def _render_success_banner(title: str, subtitle: str) -> None:
    panel = Panel.fit(
        f"[bold green]{SUCCESS_MARK} {title}[/bold green]\n[dim]{subtitle}[/dim]",
        border_style="green",
    )
    console.print(panel)


def _run_generation(text: str, output_dir: Path, source_type: str, source_ref: str) -> None:
    normalized_text = _normalize_text(text)
    if not normalized_text:
        raise CLIError("Input resume text is empty.")

    entities = _run_step("Detecting skills", lambda: _extract_entities(normalized_text))
    skill_records = _build_entity_records(SKILLS_DIR, entities["skills"])
    tool_records = _build_entity_records(TOOLS_DIR, entities["tools"])
    domain_records = _build_entity_records(DOMAINS_DIR, entities["domains"])
    profile = _build_profile(
        normalized_text,
        source_type,
        source_ref,
        skills=skill_records,
        tools=tool_records,
        domains=domain_records,
    )

    def _generate_files() -> None:
        _prepare_output(output_dir)
        _write_markdown_files(output_dir, SKILLS_DIR, "skill", skill_records)
        _write_markdown_files(output_dir, TOOLS_DIR, "tool", tool_records)
        _write_markdown_files(output_dir, DOMAINS_DIR, "domain", domain_records)
        _write_json(output_dir / PROFILE_FILE, profile)

    _run_step("Generating AI profile files", _generate_files)

    def _build_and_write_graph() -> None:
        graph = _build_graph(profile, skill_records, tool_records, domain_records)
        _write_json(output_dir / GRAPH_FILE, graph)

    _run_step("Building knowledge graph", _build_and_write_graph)
    _render_success_banner("Generating AI profile", str(output_dir.resolve()))
    _render_summary(output_dir, entities)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, KeyboardInterrupt):
        console.print("[bold yellow]Cancelled by user.[/bold yellow]")
        raise typer.Exit(code=130)
    if isinstance(exc, CLIError):
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
    console.print(f"[dim]{traceback.format_exc(limit=1).strip()}[/dim]")
    raise typer.Exit(code=1)


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show CLI version and exit.",
        is_eager=True,
    ),
) -> None:
    if version:
        console.print(f"{APP_NAME} 1.0.0")
        raise typer.Exit()


@app.command("init")
def init(
    output_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR,
        "--output-dir",
        "-o",
        help="Output directory for generated AI profile artifacts.",
    ),
) -> None:
    """Initialize an empty deterministic ln2md workspace."""
    try:
        def _initialize() -> None:
            _prepare_output(output_dir)
            _write_json(
                output_dir / PROFILE_FILE,
                {
                    "schema_version": SCHEMA_VERSION,
                    "profile_id": "",
                    "name": "",
                    "headline": "",
                    "summary": "",
                    "source": {"type": "", "ref": ""},
                    "text_sha256": "",
                    "skills": [],
                    "tools": [],
                    "domains": [],
                },
            )
            _write_json(output_dir / GRAPH_FILE, {"nodes": [], "edges": []})
            _save_state({"source_type": "", "source_ref": "", "resume_text": ""})

        _run_step("Initializing workspace", _initialize)
        _render_success_banner(f"{APP_NAME} initialized", str(output_dir.resolve()))
    except Exception as exc:
        _handle_error(exc)


@app.command("pdf")
def pdf(
    resume_pdf: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to resume PDF.",
    ),
    output_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR,
        "--output-dir",
        "-o",
        help="Output directory for generated AI profile artifacts.",
    ),
) -> None:
    """Parse a resume PDF and generate deterministic ln2md artifacts."""
    try:
        def _extract_and_cache_text() -> str:
            text = _extract_pdf_text(resume_pdf)
            _save_state(
                {
                    "source_type": "pdf",
                    "source_ref": str(resume_pdf),
                    "resume_text": text,
                }
            )
            return text

        text = _run_step("Extracting profile", _extract_and_cache_text)
        _run_generation(text=text, output_dir=output_dir, source_type="pdf", source_ref=str(resume_pdf))
    except Exception as exc:
        _handle_error(exc)


@app.command("paste")
def paste(
    text: str = typer.Option(
        "",
        "--text",
        "-t",
        help="Resume/profile text. If omitted, CLI reads from stdin until EOF.",
    ),
    output_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR,
        "--output-dir",
        "-o",
        help="Output directory for generated AI profile artifacts.",
    ),
) -> None:
    """Paste raw resume text and generate deterministic ln2md artifacts."""
    try:
        resume_text = text
        if not resume_text:
            console.print(
                Panel.fit(
                    "Paste your resume text, then send EOF.\nWindows: Ctrl+Z + Enter\nmacOS/Linux: Ctrl+D",
                    title="Input",
                    border_style="cyan",
                )
            )
            resume_text = sys.stdin.read()

        def _extract_and_cache_text() -> str:
            normalized = _normalize_text(resume_text)
            if not normalized:
                raise CLIError("No text provided. Paste non-empty resume/profile text.")
            _save_state({"source_type": "paste", "source_ref": "stdin", "resume_text": normalized})
            return normalized

        normalized = _run_step("Extracting profile", _extract_and_cache_text)
        _run_generation(text=normalized, output_dir=output_dir, source_type="paste", source_ref="stdin")
    except Exception as exc:
        _handle_error(exc)


@app.command("generate")
def generate(
    output_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR,
        "--output-dir",
        "-o",
        help="Output directory for generated AI profile artifacts.",
    ),
) -> None:
    """Generate artifacts from the most recently cached input (`pdf` or `paste`)."""
    try:
        state = _load_state()
        text = _normalize_text(str(state.get("resume_text", "")))
        source_type = str(state.get("source_type", "unknown"))
        source_ref = str(state.get("source_ref", "unknown"))
        if not text:
            raise CLIError("Cached input is empty. Run `ln2md pdf <resume.pdf>` or `ln2md paste` first.")

        normalized = _run_step(
            "Extracting profile",
            # Kept as an explicit step for consistent UX across commands.
            lambda: _normalize_text(text),
        )

        _run_generation(text=normalized, output_dir=output_dir, source_type=source_type, source_ref=source_ref)
    except Exception as exc:
        _handle_error(exc)


@app.command("validate")
def validate(
    output_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR,
        "--output-dir",
        "-o",
        help="Output directory for generated AI profile artifacts.",
    ),
) -> None:
    """Validate generated ln2md output structure and core schema."""
    try:
        from ln2md.validator import validate_ai_profile_structure

        result = _run_step(
            "Validating structure and schema",
            lambda: validate_ai_profile_structure(output_dir),
        )
        if not result.is_valid:
            for index, message in enumerate(result.errors, start=1):
                console.print(f"[red]{index}.[/red] {message}")
            raise CLIError("Validation failed. See errors above.")

        console.print(f"[bold green]{SUCCESS_MARK} ln2md output is valid[/bold green]")
        console.print(f"[dim]Validated:[/dim] {output_dir.resolve()}")
    except Exception as exc:
        _handle_error(exc)


def run() -> None:
    """Console script entrypoint."""
    app()


if __name__ == "__main__":
    run()
