"""/read 模式 — 漏斗式三层精读."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from ..core.paper import Paper, ReadingNote, ScanResult
from ..core.reading_pipeline import (
    scan_paper,
    skim_paper,
    deep_read_paper,
)
from ..utils.markdown_exporter import export_deep_read_note

console = Console()


def _collect_paper_info() -> Paper:
    """Interactively collect paper information from the user."""
    console.print(Panel.fit(
        "[bold]论文精读模式[/bold]\n"
        "漏斗式三层阅读：扫描 → 速读 → 精读",
        title="/read",
    ))

    title = Prompt.ask("论文标题")
    authors_str = Prompt.ask("作者（逗号分隔）", default="")
    authors = [a.strip() for a in authors_str.split(",") if a.strip()] if authors_str else []
    venue = Prompt.ask("出处（会议/期刊）", default="")
    year_str = Prompt.ask("年份", default="")
    year = int(year_str) if year_str.isdigit() else None
    url = Prompt.ask("链接（URL）", default="")
    abstract = Prompt.ask("Abstract（可粘贴，回车结束）", default="")
    keywords_str = Prompt.ask("关键词（逗号分隔）", default="")
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()] if keywords_str else []

    return Paper(
        title=title,
        authors=authors,
        venue=venue,
        year=year,
        url=url,
        abstract=abstract,
        keywords=keywords,
    )


def _display_scan_result(scan: ScanResult) -> None:
    """Display Level 1 scan results."""
    stars = "★" * scan.relevance_score + "☆" * (5 - scan.relevance_score)
    lines = [
        f"[bold]一句话总结:[/bold] {scan.one_sentence_summary}",
        f"[bold]相关性评分:[/bold] {stars} ({scan.relevance_score}/5)",
        f"[bold]建议:[/bold] {'继续阅读 →' if scan.should_continue else '可能不相关'}",
        f"[dim]{scan.continue_reason}[/dim]",
    ]
    console.print(Panel("\n".join(lines), title="Level 1 — 扫描结果"))


def _display_skim_result(skim) -> None:
    """Display Level 2 skim results."""
    lines = []
    if skim.core_contributions:
        lines.append("[bold]核心贡献:[/bold]")
        for c in skim.core_contributions:
            lines.append(f"  • {c}")
        lines.append("")

    if skim.method_highlights:
        lines.append(f"[bold]方法亮点:[/bold] {skim.method_highlights}")
        lines.append("")

    if skim.threat_model_summary:
        lines.append(f"[bold]Threat Model:[/bold] {skim.threat_model_summary}")
        lines.append("")

    if skim.key_experiment_results:
        lines.append(f"[bold]关键实验结果:[/bold] {skim.key_experiment_results}")
        lines.append("")

    if skim.match_points:
        lines.append(f"[bold dim]匹配点:[/bold dim] {skim.match_points}")

    console.print(Panel("\n".join(lines), title="Level 2 — 速读结果"))


def _display_deep_result(deep) -> None:
    """Display Level 3 deep read summary."""
    lines = []
    if deep.problem_definition:
        lines.append(f"[bold]问题定义:[/bold] {deep.problem_definition[:300]}...")
        lines.append("")

    if deep.strengths:
        lines.append("[bold green]优点:[/bold green]")
        for s in deep.strengths:
            lines.append(f"  ✓ {s}")
        lines.append("")

    if deep.limitations:
        lines.append("[bold red]局限:[/bold red]")
        for l in deep.limitations:
            lines.append(f"  ✗ {l}")
        lines.append("")

    if deep.improvement_directions:
        lines.append("[bold yellow]可改进方向:[/bold yellow]")
        for d in deep.improvement_directions:
            lines.append(f"  → {d}")

    console.print(Panel("\n".join(lines), title="Level 3 — 精读完成"))


def run_reading_mode(paper: Optional[Paper] = None) -> Optional[ReadingNote]:
    """Run the interactive /read mode with funnel reading.

    Args:
        paper: If provided, skip the paper info collection step.
    """
    if paper is None:
        paper = _collect_paper_info()

    if not paper.title:
        console.print("[red]论文标题不能为空[/red]")
        return None

    user_interest = Prompt.ask("你的研究方向（可选，用于匹配度分析）", default="")

    console.print(f"\n[bold]开始阅读:[/bold] {paper.title}")
    console.print("[dim]漏斗式阅读：Level 1 → Level 2 → Level 3（可随时输入 stop 停止）[/dim]\n")

    note = ReadingNote(paper=paper)

    # Level 1 — Scan
    console.print("[bold cyan]═══ Level 1: 扫描 (Scanning, ~30s) ═══[/bold cyan]")
    with console.status("[bold green]分析中...[/bold green]"):
        scan = scan_paper(paper, user_interest)
    note.scan = scan
    note.one_sentence_summary = scan.one_sentence_summary
    note.relevance_score = scan.relevance_score
    _display_scan_result(scan)

    if not scan.should_continue:
        console.print("[yellow]建议停止。匹配度较低。[/yellow]")
        resp = Prompt.ask("仍然继续？", default="否", choices=["是", "否", "stop"])
        if resp in ("否", "stop"):
            return note

    resp = Prompt.ask("进入 Level 2 速读？", default="是", choices=["是", "否", "stop"])
    if resp in ("否", "stop"):
        return note

    # Level 2 — Skim
    console.print("\n[bold cyan]═══ Level 2: 速读 (Skimming, ~3-5min) ═══[/bold cyan]")
    with console.status("[bold green]速读分析中...[/bold green]"):
        skim = skim_paper(paper, user_interest)
    note.skim = skim
    _display_skim_result(skim)

    resp = Prompt.ask("进入 Level 3 精读？", default="是", choices=["是", "否", "stop"])
    if resp in ("否", "stop"):
        return note

    # Level 3 — Deep Read
    console.print("\n[bold cyan]═══ Level 3: 精读 (Deep Reading, ~15-30min) ═══[/bold cyan]")
    full_text = Prompt.ask(
        "如有全文可粘贴（可选，回车跳过）",
        default="",
    )

    with console.status("[bold green]深度分析中...[/bold green]"):
        deep = deep_read_paper(paper, full_text, user_interest)
    note.deep = deep
    note.level = "deep"
    _display_deep_result(deep)

    # Export
    if deep.problem_definition:
        export = Confirm.ask("导出 Markdown 精读笔记？", default=True)
        if export:
            output_dir = Prompt.ask("输出目录", default="./reading_notes")
            filepath = export_deep_read_note(note, output_dir)
            console.print(f"[green]笔记已保存到: {filepath}[/green]")

    return note


if __name__ == "__main__":
    run_reading_mode()
