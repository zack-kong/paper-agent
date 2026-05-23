"""论文数据模型 — Pydantic schemas for PaperAgent."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class ReadingLevel(str, Enum):
    SCAN = "scan"      # Level 1: title + abstract + conclusion
    SKIM = "skim"      # Level 2: intro + method overview + experiments
    DEEP = "deep"      # Level 3: full paper deep reading


class VenueType(str, Enum):
    CONFERENCE = "conference"
    JOURNAL = "journal"


class Venue(BaseModel):
    name: str
    full_name: str
    domain: str
    venue_type: VenueType = VenueType.CONFERENCE
    aliases: list[str] = Field(default_factory=list)


class Paper(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    venue: str = ""                          # e.g. "ICRA 2025", "IEEE T-RO"
    year: Optional[int] = None
    url: str = ""
    abstract: str = ""
    keywords: list[str] = Field(default_factory=list)
    source: str = ""                         # e.g. "arxiv", "openreview", "ieee"

    def citation(self) -> str:
        authors_str = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += " et al."
        parts = [authors_str, f'"{self.title}"', self.venue]
        if self.year:
            parts.append(str(self.year))
        return ", ".join(parts)


class SearchResult(BaseModel):
    paper: Paper
    relevance_score: int = Field(default=3, ge=1, le=5)
    recommendation_reason: str = ""
    batch_number: int = 1


class ValidationItem(BaseModel):
    check_name: str
    passed: bool = True
    detail: str = ""


class ValidationResult(BaseModel):
    paper_title: str
    items: list[ValidationItem] = Field(default_factory=list)
    all_passed: bool = True
    needs_verification: bool = False
    verified_mark: str = ""                  # "" or "[待验证]"

    @classmethod
    def create_default(cls, title: str) -> "ValidationResult":
        checks = [
            "标题可在 Google Scholar / arXiv / DBLP 检索",
            "作者名单与出处匹配",
            "会议/期刊名称在白名单中且真实存在",
            "年份合理",
            "链接域名属于可信源",
            "Abstract 内容与标题和会议主题逻辑一致",
            "无 A 论文摘要套到 B 论文标题的混淆",
            "无看起来合理但查无此文的幻觉",
        ]
        items = [ValidationItem(check_name=c, passed=False, detail="") for c in checks]
        return cls(paper_title=title, items=items)


class ScanResult(BaseModel):
    """Level 1 阅读结果."""
    one_sentence_summary: str = ""
    relevance_score: int = Field(default=3, ge=1, le=5)
    should_continue: bool = True
    continue_reason: str = ""


class SkimResult(BaseModel):
    """Level 2 阅读结果."""
    core_contributions: list[str] = Field(default_factory=list)
    method_highlights: str = ""
    threat_model_summary: str = ""
    key_experiment_results: str = ""
    match_points: str = ""


class DeepReadResult(BaseModel):
    """Level 3 阅读结果."""
    problem_definition: str = ""
    method_framework: str = ""
    key_formulas: list[dict[str, str]] = Field(default_factory=list)  # [{formula, meaning, derivation}]
    experiment_setup: str = ""
    key_results: str = ""
    ablation_study: str = ""
    strengths: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    improvement_directions: list[str] = Field(default_factory=list)
    relevance_to_own_work: str = ""
    follow_up_papers: list[str] = Field(default_factory=list)
    open_source_code: str = ""


class ReadingNote(BaseModel):
    """完整的精读笔记."""
    paper: Paper
    level: ReadingLevel = ReadingLevel.SCAN
    reading_date: date = Field(default_factory=date.today)
    one_sentence_summary: str = ""
    relevance_score: int = Field(default=3, ge=1, le=5)
    scan: Optional[ScanResult] = None
    skim: Optional[SkimResult] = None
    deep: Optional[DeepReadResult] = None

    def get_markdown_content(self, template: str | None = None) -> str:
        """Generate Markdown from the reading note."""
        lines = [
            f"# {self.paper.title}",
            "",
            "## 元信息",
            f"- **作者**：{', '.join(self.paper.authors) if self.paper.authors else 'N/A'}",
            f"- **出处**：{self.paper.venue or 'N/A'}",
            f"- **年份**：{self.paper.year or 'N/A'}",
            f"- **链接**：{self.paper.url or 'N/A'}",
            f"- **相关性评分**：{self.relevance_score}/5",
            f"- **阅读日期**：{self.reading_date}",
            "",
            "## 一句话总结",
            self.one_sentence_summary or "N/A",
            "",
        ]

        if self.skim:
            lines.append("## 核心贡献")
            if self.skim.core_contributions:
                for i, c in enumerate(self.skim.core_contributions, 1):
                    lines.append(f"{i}. {c}")
            else:
                lines.append("N/A")
            lines.append("")

        if self.deep:
            d = self.deep
            lines += [
                "## 方法精要",
                "### 问题定义",
                d.problem_definition or "N/A",
                "",
                "### 方法框架",
                d.method_framework or "N/A",
                "",
                "### 关键公式与解释",
                "| 公式 | 含义/直觉 | 关键推导 |",
                "|---|---|---|",
            ]
            for f in d.key_formulas:
                formula = f.get("formula", "")
                meaning = f.get("meaning", "")
                derivation = f.get("derivation", "")
                lines.append(f"| $$ {formula} $$ | {meaning} | {derivation} |")
            if not d.key_formulas:
                lines.append("| N/A | N/A | N/A |")
            lines += [
                "",
                "## 实验与结果",
                "### 实验设置",
                d.experiment_setup or "N/A",
                "",
                "### 关键结果",
                d.key_results or "N/A",
                "",
                "### Ablation Study",
                d.ablation_study or "N/A",
                "",
                "## 批判性思考",
                "### 优点",
            ]
            if d.strengths:
                for s in d.strengths:
                    lines.append(f"- {s}")
            else:
                lines.append("- N/A")
            lines += [
                "",
                "### 局限与强假设",
            ]
            if d.limitations:
                for l in d.limitations:
                    lines.append(f"- {l}")
            else:
                lines.append("- N/A")
            lines += [
                "",
                "### 可改进方向",
            ]
            if d.improvement_directions:
                for i in d.improvement_directions:
                    lines.append(f"- {i}")
            else:
                lines.append("- N/A")
            lines += [
                "",
                "### 与我工作的关联",
                d.relevance_to_own_work or "N/A",
                "",
                "## 待跟进清单",
            ]
            for p in d.follow_up_papers:
                lines.append(f"- [ ] 相关论文：{p}")
            if d.open_source_code:
                lines.append(f"- [ ] 开源代码：{d.open_source_code}")
            lines.append("- [ ] 复现关键实验")

        return "\n".join(lines)


class UserProfile(BaseModel):
    search_history: list[dict] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)
    adopted: list[dict] = Field(default_factory=list)
    rejected: list[dict] = Field(default_factory=list)
    interaction_count: int = 0
