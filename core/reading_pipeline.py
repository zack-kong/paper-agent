"""三层阅读流水线 — 全部走 DeepSeek API 进行分析."""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from openai import OpenAI

from .paper import (
    DeepReadResult,
    Paper,
    ReadingNote,
    ScanResult,
    SkimResult,
)


def _get_deepseek_client() -> OpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 环境变量未设置")
    return OpenAI(api_key=api_key, base_url=base_url)


def _call_deepseek(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """Internal helper to call DeepSeek and return text content."""
    client = _get_deepseek_client()
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=4096,
    )
    return response.choices[0].message.content or ""


def _extract_json(text: str) -> dict:
    """Extract JSON object from text that may contain markdown code fences."""
    # Remove markdown code fences
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    # Find JSON object
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        return json.loads(match.group())
    return {}


def scan_paper(paper: Paper, user_research_interest: str = "") -> ScanResult:
    """Level 1 — 扫描：30 秒快速判断论文相关性."""
    system_prompt = (
        "你是一个学术论文快速筛选助手。你需要在 30 秒内判断一篇论文是否值得深入阅读。"
        "请用中文回答，专业术语保留英文。"
        "以 JSON 格式返回结果："
        '{"one_sentence_summary": "...", "relevance_score": 4, "should_continue": true, "continue_reason": "..."}'
    )

    user_prompt = f"""请快速扫描以下论文，给出判断：

**标题**: {paper.title}
**作者**: {', '.join(paper.authors)}
**出处**: {paper.venue} ({paper.year})
**摘要**: {paper.abstract}

{"**用户研究方向**: " + user_research_interest if user_research_interest else ""}

请返回：
1. 一句话总结（中文，<80字）
2. 相关性评分（1-5）
3. 是否建议继续阅读
4. 继续/不继续的理由"""

    try:
        content = _call_deepseek(system_prompt, user_prompt)
        data = _extract_json(content)
        return ScanResult(
            one_sentence_summary=data.get("one_sentence_summary", ""),
            relevance_score=data.get("relevance_score", 3),
            should_continue=data.get("should_continue", True),
            continue_reason=data.get("continue_reason", ""),
        )
    except Exception as e:
        return ScanResult(
            one_sentence_summary=f"[分析失败: {e}]",
            relevance_score=3,
            should_continue=True,
            continue_reason="API 调用失败，建议手动判断",
        )


def skim_paper(paper: Paper, user_research_interest: str = "") -> SkimResult:
    """Level 2 — 速读：Introduction + Method概览 + 关键实验."""
    system_prompt = (
        "你是一个学术论文分析助手。请对论文进行 3-5 分钟的快速阅读分析。"
        "用中文回答，专业术语保留英文，数学公式保留 LaTeX。"
        "以 JSON 格式返回："
        '{"core_contributions": ["贡献1", "贡献2", "贡献3"], '
        '"method_highlights": "...", "threat_model_summary": "...", '
        '"key_experiment_results": "...", "match_points": "..."}'
    )

    user_prompt = f"""请对以下论文进行速读分析（Level 2）：

**标题**: {paper.title}
**作者**: {', '.join(paper.authors)}
**出处**: {paper.venue} ({paper.year})
**链接**: {paper.url}
**摘要**: {paper.abstract}
**关键词**: {', '.join(paper.keywords)}

{"**用户研究方向**: " + user_research_interest if user_research_interest else ""}

请提供：
1. 核心贡献清单（3-5 条 bullet points）
2. 方法亮点（与传统方法的区别，<200字）
3. Threat Model 概要（攻击者能力、假设；如不适用写"无"）
4. 关键实验结果（最优指标 + 与 baseline 对比）
5. 与用户需求的匹配点（为什么值得或不值得精读）"""

    try:
        content = _call_deepseek(system_prompt, user_prompt)
        data = _extract_json(content)
        return SkimResult(
            core_contributions=data.get("core_contributions", []),
            method_highlights=data.get("method_highlights", ""),
            threat_model_summary=data.get("threat_model_summary", ""),
            key_experiment_results=data.get("key_experiment_results", ""),
            match_points=data.get("match_points", ""),
        )
    except Exception as e:
        return SkimResult(
            core_contributions=[f"[分析失败: {e}]"],
            method_highlights="API 调用失败",
        )


def deep_read_paper(
    paper: Paper,
    full_text: str = "",
    user_research_interest: str = "",
) -> DeepReadResult:
    """Level 3 — 精读：完整 Method + 公式直觉 + 批判性分析."""
    system_prompt = (
        "你是一个资深学术论文审稿人。请对论文进行深度精读分析。"
        "用中文回答，专业术语保留英文并附中文解释，数学公式用 LaTeX。"
        "以 JSON 格式返回："
        '{"problem_definition": "...", "method_framework": "...", '
        '"key_formulas": [{"formula": "...", "meaning": "...", "derivation": "..."}], '
        '"experiment_setup": "...", "key_results": "...", "ablation_study": "...", '
        '"strengths": ["优点1", "优点2"], '
        '"limitations": ["局限1", "局限2"], '
        '"improvement_directions": ["改进1", "改进2"], '
        '"relevance_to_own_work": "...", '
        '"follow_up_papers": ["引用论文1", "引用论文2"], '
        '"open_source_code": ""}'
    )

    paper_context = f"""请对以下论文进行深度精读分析（Level 3）：

**标题**: {paper.title}
**作者**: {', '.join(paper.authors)}
**出处**: {paper.venue} ({paper.year})
**链接**: {paper.url}
**摘要**: {paper.abstract}
**关键词**: {', '.join(paper.keywords)}"""

    if full_text:
        paper_context += f"\n\n**全文内容**:\n{full_text[:15000]}"  # Truncate for API limits

    if user_research_interest:
        paper_context += f"\n\n**用户研究方向**: {user_research_interest}"

    user_prompt = paper_context + """

请提供：
1. **问题定义**：论文解决什么问题
2. **方法框架**：逐段解释算法流程
3. **关键公式与解释**：每个公式的直觉(Intuition) + 关键推导步骤（非照抄LaTeX）
4. **实验设置**：Dataset, Metrics, Baselines
5. **关键结果**：最优指标 + 与 baseline 对比
6. **Ablation Study**：消融实验的关键发现
7. **批判性分析**：
   - 优点（3-5条）
   - 局限与强假设（什么条件下失效）
   - 可改进方向（对用户研究的启发）
   - 与用户当前工作的关联"""

    try:
        content = _call_deepseek(system_prompt, user_prompt, temperature=0.4)
        data = _extract_json(content)

        return DeepReadResult(
            problem_definition=data.get("problem_definition", ""),
            method_framework=data.get("method_framework", ""),
            key_formulas=data.get("key_formulas", []),
            experiment_setup=data.get("experiment_setup", ""),
            key_results=data.get("key_results", ""),
            ablation_study=data.get("ablation_study", ""),
            strengths=data.get("strengths", []),
            limitations=data.get("limitations", []),
            improvement_directions=data.get("improvement_directions", []),
            relevance_to_own_work=data.get("relevance_to_own_work", ""),
            follow_up_papers=data.get("follow_up_papers", []),
            open_source_code=data.get("open_source_code", ""),
        )
    except Exception as e:
        return DeepReadResult(
            problem_definition=f"[分析失败: {e}]",
            method_framework="API 调用失败",
        )


def run_reading_pipeline(
    paper: Paper,
    user_research_interest: str = "",
    skip_to_level: int = 1,
    full_text: str = "",
) -> ReadingNote:
    """Run the full 3-level reading pipeline for a single paper."""
    note = ReadingNote(paper=paper)

    if skip_to_level <= 1:
        print("  [Level 1] 扫描中...")
        scan = scan_paper(paper, user_research_interest)
        note.scan = scan
        note.one_sentence_summary = scan.one_sentence_summary
        note.relevance_score = scan.relevance_score
        if not scan.should_continue:
            return note

    if skip_to_level <= 2:
        print("  [Level 2] 速读中...")
        skim = skim_paper(paper, user_research_interest)
        note.skim = skim

    if skip_to_level <= 3:
        print("  [Level 3] 精读中...")
        deep = deep_read_paper(paper, full_text, user_research_interest)
        note.deep = deep
        note.level = "deep"

    return note
