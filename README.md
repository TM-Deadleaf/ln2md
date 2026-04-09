# ln2md CLI

Turn your resume into an AI-readable knowledge base for coding agents.

`ln2md` generates structured developer skill profiles from resumes and professional profiles so AI coding agents can reason over your experience consistently. Compatible with agent workflows used by **Claude**, **Codex**, and **Gemini**.

---

## 🎬 Demo

```bash
ln2md pdf resume.pdf
```

```text
ln2md/
skills/
graph.json
```

The CLI analyzes your resume and generates a deterministic, structured, AI-readable profile for downstream coding-agent use.

---

## 💡 Why This Matters

- Modern AI coding agents need structured developer context to make accurate decisions.
- Traditional resumes are unstructured text, which is hard for AI systems to interpret reliably.
- `ln2md` converts developer experience into deterministic, structured knowledge that agents can use directly.
- Structured output improves automation, retrieval, and consistency across agent workflows.

---

## 🧩 Example Generated Skill File

```md
---
id: "python"
name: "Python"
type: "skill"
category: "technical"
level: "intermediate"
depends_on: []
tools: []
domains: []
---

## Skill Summary
- Strong Python development experience.

## Core Competencies
- N/A

## Tools and Technologies
- N/A

## Practical Experience
- Built backend automation workflows in Python.

## Automation Opportunities
- N/A

## Related Skills
- N/A
```

---

## 📦 Installation

```bash
pip install ln2md
```

For local development:

```bash
pip install -e .
```

---

## ⚡ Quick Start

```bash
# 1) Generate AI profile artifacts from PDF
ln2md pdf resume.pdf

# 2) Validate structure and agent compatibility
ln2md validate
```

Optional environment setup for Gemini-powered modules:

```env
GEMINI_API_KEY="your-key-here"
GEMINI_MODEL="gemini-3.1-flash-lite-preview"
```

---

## 🗂️ Folder Structure Output

```text
ln2md/
  profile.json
  graph.json
  skills/
    <skill>.md
  tools/
    <tool>.md
  domains/
    <domain>.md
```

---

## 🛣️ Roadmap

- [ ] Higher-precision LinkedIn PDF parsing
- [ ] Better profile name/headline extraction heuristics
- [ ] Multi-language resume support
- [ ] CI workflow for schema regression tests
- [ ] Plugin hooks for custom extraction pipelines

---

## 🤝 Contributing

Contributions are welcome.

1. Fork the repo.
2. Create a feature branch.
3. Add tests and keep output deterministic.
4. Run validation locally.
5. Open a PR with a clear change summary.

If you are adding fields, update the compatibility schema and validator in the same PR.

---

## 📄 License

MIT License
