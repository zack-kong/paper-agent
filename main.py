#!/usr/bin/env python3
"""PaperAgent — 学术文献检索与精读 Agent.

Usage:
    python main.py --mode search          # 交互式检索
    python main.py --mode search --query "adversarial attacks on RL"
    python main.py --mode read            # 交互式精读
    python main.py --mode read --title "Paper Title" --authors "Author1, Author2"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from paper_agent.core.paper import Paper
from paper_agent.modes.search_mode import run_search_mode
from paper_agent.modes.reading_mode import run_reading_mode

app = typer.Typer(
    name="paper-agent",
    help="学术文献检索与精读 Agent",
    add_completion=False,
)

console = Console()


@app.command()
def search(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="检索关键词"),
    years: Optional[str] = typer.Option(None, "--years", "-y", help="年份范围，如 2022-2025"),
    auto: bool = typer.Option(False, "--auto", "-a", help="自动确认，跳过交互"),
):
    """/search 模式：从顶会顶刊检索论文."""
    year_tuple = None
    if years:
        try:
            parts = years.split("-")
            year_tuple = (int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            console.print("[red]年份格式错误，应为 YYYY-YYYY[/red]")
            raise typer.Exit(1)

    try:
        results = run_search_mode(
            query=query,
            years=year_tuple,
            auto_confirm=auto,
        )
        if results and len(results) == 1:
            # Single result from "深入某篇" — switch to read mode
            console.print("\n[bold]切换到 /read 模式...[/bold]")
            read(paper_title=results[0].paper.title)
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消[/yellow]")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def read(
    paper_title: Optional[str] = typer.Option(None, "--title", "-t", help="论文标题"),
    authors: Optional[str] = typer.Option(None, "--authors", "-a", help="作者（逗号分隔）"),
    venue: Optional[str] = typer.Option(None, "--venue", "-v", help="出处（会议/期刊）"),
    year: Optional[int] = typer.Option(None, "--year", "-y", help="年份"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="论文链接"),
    abstract: Optional[str] = typer.Option(None, "--abstract", help="摘要文本"),
    keywords: Optional[str] = typer.Option(None, "--keywords", "-k", help="关键词（逗号分隔）"),
):
    """/read 模式：漏斗式三层精读."""
    paper = None

    if paper_title:
        # Build paper from CLI args
        author_list = [a.strip() for a in authors.split(",") if a.strip()] if authors else []
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
        paper = Paper(
            title=paper_title,
            authors=author_list,
            venue=venue or "",
            year=year,
            url=url or "",
            abstract=abstract or "",
            keywords=kw_list,
        )

    try:
        note = run_reading_mode(paper=paper)
        if note and note.deep and note.deep.problem_definition:
            console.print("\n[bold green]精读完成！[/bold green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消[/yellow]")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def version():
    """显示版本信息."""
    console.print("[bold]PaperAgent[/bold] v0.1.0")
    console.print("学术文献检索与精读 Agent")
    console.print("支持 /search 和 /read 两种模式")


def main():
    """Entry point for console_scripts."""
    app()


if __name__ == "__main__":
    main()
