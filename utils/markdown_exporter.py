"""Markdown 笔记生成 — 按 spec 模板导出 Level 3 精读笔记."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..core.paper import ReadingNote


def _sanitize_filename(title: str, max_len: int = 60) -> str:
    """Convert paper title to a safe filename."""
    # Remove or replace special characters
    safe = re.sub(r'[<>:"/\\|?*]', '', title)
    safe = re.sub(r'\s+', '_', safe)
    safe = re.sub(r'[^\w\-_.]', '', safe)
    if len(safe) > max_len:
        safe = safe[:max_len]
    return safe or "reading_note"


def export_deep_read_note(
    note: ReadingNote,
    output_dir: str | Path = "./reading_notes",
    filename: str | None = None,
) -> Path:
    """Export a Level 3 deep reading note as a Markdown file.

    Args:
        note: The complete ReadingNote (must have deep read results).
        output_dir: Directory to save the note.
        filename: Custom filename (without extension). Auto-generated if None.

    Returns:
        Path to the created file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        date_str = date.today().strftime("%Y%m%d")
        safe_title = _sanitize_filename(note.paper.title)
        filename = f"{date_str}_{safe_title}"

    filepath = output_dir / f"{filename}.md"

    md_content = note.get_markdown_content()

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md_content)

    return filepath


def export_search_results(
    results: list,
    output_dir: str | Path = "./search_results",
    filename: str | None = None,
) -> Path:
    """Export search results as a Markdown summary table.

    Args:
        results: List of SearchResult objects.
        output_dir: Directory to save.
        filename: Custom filename.

    Returns:
        Path to the created file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        date_str = date.today().strftime("%Y%m%d")
        filename = f"{date_str}_search_results"

    filepath = output_dir / f"{filename}.md"

    lines = [
        "# 文献检索结果",
        "",
        f"**检索日期**: {date.today()}",
        f"**结果数量**: {len(results)}",
        "",
        "| 序号 | 标题 | 作者 | 出处 | 年份 | 相关度 | 推荐理由 |",
        "|---|---|---|---|---|---|---|",
    ]

    for i, r in enumerate(results, 1):
        authors = ", ".join(r.paper.authors[:2])
        if len(r.paper.authors) > 2:
            authors += " et al."
        lines.append(
            f"| {i} | {r.paper.title} | {authors} | {r.paper.venue} | "
            f"{r.paper.year or '?'} | {r.relevance_score}/5 | {r.recommendation_reason} |"
        )

    lines += [
        "",
        "## 详细信息",
        "",
    ]

    for i, r in enumerate(results, 1):
        p = r.paper
        lines += [
            f"### {i}. {p.title}",
            "",
            f"- **作者**: {', '.join(p.authors)}",
            f"- **出处**: {p.venue} ({p.year or 'N/A'})",
            f"- **链接**: {p.url}",
            f"- **相关度**: {r.relevance_score}/5",
            f"- **理由**: {r.recommendation_reason}",
            "",
            f"**Abstract**: {p.abstract}",
            "",
        ]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath
