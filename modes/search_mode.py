"""/search 模式 — 交互式学术文献检索."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from ..core.paper import Paper, SearchResult, UserProfile
from ..core.search_engine import (
    analyze_query,
    recommend_venues,
    search_papers,
)
from ..core.validator import validate_paper, validate_results

console = Console()

PROFILE_PATH = Path(__file__).parent.parent / "config" / "user_profile.json"


def _load_profile() -> UserProfile:
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH) as f:
            data = json.load(f)
        return UserProfile(**data)
    return UserProfile()


def _save_profile(profile: UserProfile) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)


def _display_venue_recommendations(venues, query: str) -> None:
    table = Table(title=f"推荐会议/期刊 — 针对查询: {query}")
    table.add_column("#", style="dim", width=3)
    table.add_column("名称", style="cyan")
    table.add_column("全称")
    table.add_column("领域", style="green")
    table.add_column("类型")
    table.add_column("推荐理由")

    domain_reasons = {
        "robotics": "机器人学核心会议/期刊",
        "ai_security": "AI 安全与隐私领域顶会/顶刊",
        "general_ai": "通用 AI/ML 顶会/顶刊，交叉引用",
    }

    for i, v in enumerate(venues, 1):
        reason = domain_reasons.get(v.domain, "相关领域")
        table.add_row(
            str(i), v.name, v.full_name, v.domain,
            "期刊" if v.venue_type == "journal" else "会议",
            reason,
        )

    console.print(table)


def _display_search_results(results: list[SearchResult]) -> None:
    """Display search results as a rich table."""
    table = Table(title="检索结果", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("标题", style="bold cyan", max_width=50)
    table.add_column("作者", max_width=25)
    table.add_column("出处", style="green", max_width=20)
    table.add_column("年份", width=5)
    table.add_column("相关度", justify="center")
    table.add_column("推荐理由", max_width=30)
    table.add_column("验证", width=6)

    for i, r in enumerate(results, 1):
        vr = validate_paper(r.paper)
        authors = ", ".join(r.paper.authors[:2])
        if len(r.paper.authors) > 2:
            authors += " et al."

        table.add_row(
            str(i),
            r.paper.title,
            authors,
            r.paper.venue,
            str(r.paper.year) if r.paper.year else "?",
            f"{'★' * r.relevance_score}{'☆' * (5 - r.relevance_score)}",
            r.recommendation_reason,
            vr.verified_mark if vr.needs_verification else "✓",
        )

    console.print(table)


def _display_paper_detail(result: SearchResult) -> None:
    """Display full details of a single paper."""
    p = result.paper
    vr = validate_paper(p)

    lines = [
        f"[bold cyan]{p.title}[/bold cyan]",
        "",
        f"[dim]作者:[/dim] {', '.join(p.authors)}",
        f"[dim]出处:[/dim] {p.venue} ({p.year or 'N/A'})",
        f"[dim]链接:[/dim] {p.url}",
        f"[dim]关键词:[/dim] {', '.join(p.keywords) if p.keywords else 'N/A'}",
        f"[dim]相关度:[/dim] {'★' * result.relevance_score}{'☆' * (5 - result.relevance_score)}",
        f"[dim]来源:[/dim] {p.source}",
        "",
        f"[bold]Abstract:[/bold]",
        p.abstract or "N/A",
    ]

    if vr.needs_verification:
        lines.append("")
        lines.append(f"[bold red]⚠ 验证未通过: {vr.verified_mark}[/bold red]")
        for item in vr.items:
            if not item.passed:
                lines.append(f"  [red]✗[/red] {item.check_name}: {item.detail}")

    console.print(Panel("\n".join(lines), title="论文详情"))


def _learn_from_interaction(
    profile: UserProfile,
    query: str,
    adopted: list[SearchResult],
    rejected: list[SearchResult],
) -> None:
    """Update user profile based on this interaction."""
    profile.interaction_count += 1

    profile.search_history.append({
        "query": query,
        "adopted_titles": [r.paper.title for r in adopted],
        "rejected_titles": [r.paper.title for r in rejected],
        "venue_names": list({r.paper.venue for r in adopted if r.paper.venue}),
    })

    for r in adopted:
        profile.adopted.append({
            "title": r.paper.title,
            "venue": r.paper.venue,
            "year": r.paper.year,
            "relevance_score": r.relevance_score,
        })

    for r in rejected:
        profile.rejected.append({
            "title": r.paper.title,
            "reason": r.recommendation_reason,
        })

    # Update preferences based on adopted items
    venues = list({r.paper.venue for r in adopted if r.paper.venue})
    if venues:
        existing = set(profile.preferences.get("preferred_venues", []))
        existing.update(venues)
        profile.preferences["preferred_venues"] = list(existing)

    # Extract common keywords from adopted papers
    all_keywords = []
    for r in adopted:
        all_keywords.extend(r.paper.keywords)
    if all_keywords:
        existing_kw = set(profile.preferences.get("preferred_keywords", []))
        existing_kw.update(all_keywords[:10])
        profile.preferences["preferred_keywords"] = list(existing_kw)

    _save_profile(profile)
    console.print("[dim]偏好已更新到 user_profile.json[/dim]")


def run_search_mode(
    query: Optional[str] = None,
    years: Optional[tuple[int, int]] = None,
    auto_confirm: bool = False,
) -> list[SearchResult]:
    """Run the interactive /search mode.

    Args:
        query: Search query. If None, prompt user.
        years: (start_year, end_year) tuple. Defaults to last 3 years.
        auto_confirm: Skip venue confirmation prompt.
    """
    profile = _load_profile()

    # Step 1: Clarify needs
    if query is None:
        console.print(Panel.fit(
            "[bold]学术文献检索模式[/bold]\n"
            "从顶会顶刊中检索论文，返回结构化元数据。\n"
            "输入 'quit' 退出。",
            title="/search",
        ))
        query = Prompt.ask("\n请输入检索主题/关键词")

    if query.lower() == "quit":
        return []

    console.print(f"\n[bold]检索查询:[/bold] {query}")

    # Show preferences if available
    if profile.preferences.get("preferred_venues"):
        console.print(
            f"[dim]已学习的偏好会议: {', '.join(profile.preferences.get('preferred_venues', [])[:5])}[/dim]"
        )

    # Step 1: Query analysis (translation + concept extraction) and venue recommendation
    # Note: search_papers() also accepts the analysis to avoid a second API call
    analysis = analyze_query(query)

    if analysis.is_chinese and analysis.translated_query != query:
        console.print(f"\n[bold]查询翻译:[/bold] [cyan]{query}[/cyan] → [green]{analysis.translated_query}[/green]")
        if analysis.key_concepts:
            console.print(f"[bold]提取概念:[/bold] {', '.join(analysis.key_concepts)}")

    venues = recommend_venues(query, analysis=analysis)
    _display_venue_recommendations(venues, analysis.translated_query or query)

    if not auto_confirm:
        console.print("\n你可以：✅ 确认 / 🔄 换推荐 / ➕ 添加会议 / 🔍 调整时间范围")
        action = Prompt.ask("选择操作", default="确认", choices=["确认", "换推荐", "添加会议", "调整时间"])
        if action == "quit":
            return []
    else:
        action = "确认"

    if action == "确认":
        pass
    elif action == "调整时间":
        yrs = Prompt.ask("时间范围（如 2022-2025）", default="2022-2025")
        try:
            parts = yrs.split("-")
            years = (int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            console.print("[red]时间格式错误，使用默认近 3 年[/red]")

    # Step 2-5: Execute search with AI optimization + self-evaluation
    console.print("\n[bold]正在执行搜索...[/bold]")
    results, evaluation = search_papers(query, venues, years, analysis=analysis)
    # Note: execute_search_batch, build_search_batches, deduplicate, rank_results
    # are now internal to search_papers()

    if not results:
        console.print("[yellow]未找到结果。尝试调整关键词或会议范围。[/yellow]")
        if evaluation.suggested_queries:
            console.print(f"[dim]建议尝试: {', '.join(evaluation.suggested_queries[:3])}[/dim]")
        return []

    # Step 5: Display AI evaluation summary
    console.print(Panel.fit(
        f"[bold]AI 评估: {'★' * evaluation.overall_quality}{'☆' * (5 - evaluation.overall_quality)}"
        f" ({evaluation.overall_quality}/5)[/bold]\n"
        f"{evaluation.summary}",
        title="AI 自评结果",
        border_style="blue",
    ))

    # Step 6: Display results (with AI-adjusted scores)
    _display_search_results(results[:15])

    if auto_confirm:
        _learn_from_interaction(profile, query, results[:3], results[-2:] if len(results) > 3 else [])
        return results

    # Step 7: Interactive refinement
    console.print("\n操作选项：✅ 确认结果 / 🔄 换一批 / ➕ 深入某篇 / 💾 保存 / 🚫 退出")
    action = Prompt.ask(
        "选择操作",
        default="确认结果",
        choices=["确认结果", "换一批", "深入某篇", "保存", "退出"],
    )

    if action == "退出":
        return []

    if action == "深入某篇":
        idx = Prompt.ask("输入论文序号", default="1")
        try:
            i = int(idx) - 1
            if 0 <= i < len(results):
                _display_paper_detail(results[i])
                switch = Confirm.ask("切换到 /read 模式精读此论文？", default=False)
                if switch:
                    return [results[i]]
        except (ValueError, IndexError):
            console.print("[red]无效序号[/red]")

    if action == "保存":
        # Save results as JSON
        output_path = Path("search_results.json")
        data = [r.model_dump(mode="json") for r in results]
        with open(output_path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        console.print(f"[green]结果已保存到 {output_path}[/green]")

    # Learn from interaction
    adopted = results[:3]  # Top 3 considered adopted
    rejected = results[-2:] if len(results) > 3 else []  # Bottom 2 rejected
    _learn_from_interaction(profile, query, adopted, rejected)

    return results


if __name__ == "__main__":
    run_search_mode()
