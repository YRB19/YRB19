"""Lightweight convention checks for flagship repository READMEs (Phase 8).

Checks one staged repo directory (README.md + assets/). It cannot prove a claim is true -
that is the audit's job - but it catches the mechanical failures: dead local links, missing
alt text, wrong card size, leftover placeholders, local paths, secrets, unsupported licence
badges, static CI badges and malformed Mermaid.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

PLACEHOLDERS = ("your-username", "your-name", "your-server-url.com", "<your-repo-url>", "your-email@example.com")
LOCAL_PATHS = re.compile(r"(/home/\w+|/Users/\w+|[A-Za-z]:\\Users\\|/tmp/claude)")
SECRETS = re.compile(r"(nvapi-[A-Za-z0-9]{10,}|tvly-[A-Za-z0-9]{8,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
MERMAID_START = ("flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram")
STATIC_CI_BADGE = re.compile(r"img\.shields\.io/badge/(?:build|ci|tests?)[-_]", re.I)
LINK = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)\)")


def _strip_fences(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.S)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


def check_repo(folder: Path) -> list[str]:
    problems: list[str] = []
    readme = folder / "README.md"
    if not readme.is_file():
        return [f"{folder.name}: README.md missing"]
    text = readme.read_text(encoding="utf-8")
    prose = _strip_fences(text)
    name = folder.name
    # Files that exist in the real repository but are not staged here (listed by `git ls-files` at audit time).
    listing = folder / ".upstream-files"
    upstream = set(listing.read_text(encoding="utf-8").split("\n")) if listing.is_file() else set()

    for m in LINK.finditer(prose):
        alt, target = m.groups()
        is_image = m.group(0).startswith("!")
        if is_image and not alt.strip():
            problems.append(f"{name}: image without alt text: {target}")
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            continue
        rel = target.split("#")[0]
        if rel and not ((folder / rel).exists() or rel in upstream):
            problems.append(f"{name}: broken local link/image: {target}")

    for ph in PLACEHOLDERS:
        # a line that names the placeholder *as* a placeholder is documentation, not a leftover
        if any(ph in ln and "placeholder" not in ln.lower() for ln in prose.splitlines()):
            problems.append(f"{name}: placeholder in prose: {ph}")
    if LOCAL_PATHS.search(text):
        problems.append(f"{name}: local machine path")
    if SECRETS.search(text):
        problems.append(f"{name}: secret-looking token")
    if STATIC_CI_BADGE.search(text):
        problems.append(f"{name}: static CI/test badge")
    if re.search(r"license-MIT|licen[sc]e.{0,20}MIT", text, re.I) and not (folder / "LICENSE").exists():
        problems.append(f"{name}: MIT claim without a LICENSE file")

    fences = re.findall(r"```mermaid\n(.*?)```", text, flags=re.S)
    if text.count("```") % 2:
        problems.append(f"{name}: unbalanced code fence")
    for block in fences:
        if not block.lstrip().startswith(MERMAID_START):
            problems.append(f"{name}: unrecognised Mermaid diagram type")
    if not fences:
        problems.append(f"{name}: no architecture diagram")

    card = folder / "assets" / "social-preview.png"
    svg = folder / "assets" / "social-preview.svg"
    if not card.is_file() or not svg.is_file():
        problems.append(f"{name}: social preview PNG/SVG missing")
    else:
        if png_size(card) != (1280, 640):
            problems.append(f"{name}: social preview is {png_size(card)}, expected (1280, 640)")
        if "#3B82F6" not in svg.read_text(encoding="utf-8"):
            problems.append(f"{name}: social preview lacks accent #3B82F6")

    if name == "ResearchOS":
        for line in prose.splitlines():
            if "telegram" in line.lower() and not re.search(r"\b(no|not|without)\b", line, re.I):
                problems.append(f"ResearchOS: unqualified Telegram claim: {line.strip()[:60]}")
    return problems


def check_all(root: Path) -> list[str]:
    out: list[str] = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        out += check_repo(folder)
    return out
