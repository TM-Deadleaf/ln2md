from pathlib import Path

from setuptools import find_packages
from setuptools import setup


def read_requirements() -> list[str]:
    requirements_path = Path(__file__).parent / "requirements.txt"
    lines = requirements_path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def read_readme() -> str:
    readme_path = Path(__file__).parent / "README.md"
    if not readme_path.exists():
        return "ln2md: Convert resumes into AI-agent-readable knowledge profiles."
    return readme_path.read_text(encoding="utf-8")


setup(
    name="ln2md",
    version="0.1.0",
    description="CLI to convert developer resumes into AI-agent-readable knowledge profiles.",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="ln2md maintainers",
    author_email="maintainers@example.com",
    license="MIT",
    url="https://github.com/TM-Deadleaf/ln2md",
    python_requires=">=3.9",
    packages=find_packages(include=["ln2md", "ln2md.*"]),
    install_requires=read_requirements(),
    include_package_data=False,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Utilities",
    ],
    entry_points={
        "console_scripts": [
            "ln2md=ln2md.cli:run",
        ]
    },
)
