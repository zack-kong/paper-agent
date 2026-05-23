"""搜索引擎 — Kimi API 调用、去重、排序."""

from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from ruamel.yaml import YAML
from openai import OpenAI

from .paper import Paper, SearchResult, Venue, VenueType

_yaml = YAML(typ="safe")


def _load_venues(config_path: str | Path = "") -> dict:
    if not config_path:
        config_path = Path(__file__).parent.parent / "config" / "venues.yaml"
    with open(config_path) as f:
        return _yaml.load(f)


def _flatten_venues(venues_data: dict) -> list[Venue]:
    """Flatten the nested venue YAML into a flat list of Venue objects."""
    result: list[Venue] = []
    for domain_name, domain_data in venues_data.items():
        if domain_name == "trusted_domains":
            continue
        for category, entries in domain_data.items():
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict) and "name" in entry:
                        vt = VenueType.JOURNAL if "journal" in category.lower() else VenueType.CONFERENCE
                        result.append(Venue(
                            name=entry["name"],
                            full_name=entry.get("full_name", entry["name"]),
                            domain=domain_name,
                            venue_type=vt,
                            aliases=entry.get("aliases", []),
                        ))
    return result


def _get_kimi_client() -> OpenAI:
    api_key = os.environ.get("KIMI_API_KEY", os.environ.get("MOONSHOT_API_KEY", ""))
    base_url = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
    if not api_key:
        raise ValueError("KIMI_API_KEY 或 MOONSHOT_API_KEY 环境变量未设置")
    return OpenAI(api_key=api_key, base_url=base_url)


def recommend_venues(query: str, max_venues: int = 5) -> list[Venue]:
    """根据用户查询推荐 3-5 个最相关的会议/期刊."""
    venues_data = _load_venues()
    all_venues = _flatten_venues(venues_data)

    query_lower = query.lower()

    # Domain keyword matching
    robotics_kw = ["robot", "manipulator", "grasp", "motion", "locomotion",
                    "slam", "trajectory", "planning", "control", "autonomous",
                    "humanoid", "drone", "uav", "ros"]
    security_kw = ["adversarial", "attack", "defense", "security", "privacy",
                    "backdoor", "poison", "robustness", "crypto", "encrypt",
                    "anonym", "differential privacy", "federated", "trusted"]
    ai_kw = ["deep learning", "reinforcement learning", "transformer", "neural",
             "gradient", "optimization", "generative", "llm", "nlp", "vision",
             "classification", "segmentation", "detection"]

    domain_scores: dict[str, float] = {"robotics": 0.0, "ai_security": 0.0, "general_ai": 0.0}

    for kw in robotics_kw:
        if kw in query_lower:
            domain_scores["robotics"] += 1
    for kw in security_kw:
        if kw in query_lower:
            domain_scores["ai_security"] += 1
    for kw in ai_kw:
        if kw in query_lower:
            domain_scores["general_ai"] += 0.3  # AI is broad, lower weight

    primary_domain = max(domain_scores, key=domain_scores.get)

    # Sort venues: primary domain first, then by relevance
    scored = []
    for v in all_venues:
        score = 0.0
        if v.domain == primary_domain:
            score += 2
        elif domain_scores.get(v.domain, 0) > 0:
            score += 1
        # Bonus for name match in query
        if v.name.lower() in query_lower or any(a.lower() in query_lower for a in v.aliases):
            score += 3
        scored.append((score, v))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [v for _, v in scored[:max_venues]]


def build_search_batches(
    query: str,
    venues: list[Venue],
    years: tuple[int, int] | None = None,
) -> list[dict]:
    """Build 2-3 search batches with different keyword combinations."""
    import datetime
    current_year = datetime.date.today().year
    if years is None:
        years = (current_year - 3, current_year)

    venue_names = [v.name for v in venues]
    venue_filter = " OR ".join(f'"{v}"' for v in venue_names)

    # Extract core keywords
    core_keywords = query.strip()

    # Build synonym expansions
    synonym_map = {
        "adversarial": ["adversarial attack", "robustness", "adversarial example"],
        "reinforcement learning": ["RL", "reinforcement learning", "policy gradient"],
        "robot": ["robot", "robotics", "manipulator", "autonomous system"],
        "security": ["security", "adversarial", "robustness", "safe"],
        "privacy": ["privacy", "differential privacy", "data protection"],
        "federated": ["federated learning", "distributed learning", "collaborative learning"],
    }

    expanded_terms = []
    for key, synonyms in synonym_map.items():
        if key in query.lower():
            expanded_terms.extend(synonyms)

    batches = []

    # Batch 1: exact query with venue filter
    batches.append({
        "description": f"精确匹配：{core_keywords}",
        "query": f'site:arxiv.org OR site:openreview.net OR site:ieee.org OR site:acm.org '
                 f'{core_keywords} ({venue_filter}) {years[0]}-{years[1]}',
    })

    # Batch 2: expanded synonyms
    if expanded_terms:
        expanded_query = " OR ".join(f'"{t}"' for t in expanded_terms[:3])
        batches.append({
            "description": f"同义词扩展：{', '.join(expanded_terms[:3])}",
            "query": f'site:arxiv.org OR site:openreview.net OR site:ieee.org '
                     f'({expanded_query}) ({venue_filter}) {years[0]}-{years[1]}',
        })

    # Batch 3: broader search with domain keywords
    domain_keywords = []
    for v in venues[:3]:
        domain_keywords.append(v.name)
    broader = " OR ".join(f'"{kw}"' for kw in domain_keywords)
    batches.append({
        "description": f"宽泛搜索：{', '.join(domain_keywords)}",
        "query": f'site:arxiv.org OR site:openreview.net OR site:ieee.org '
                 f'{core_keywords} ({broader}) {years[0]}-{years[1]}',
    })

    return batches[:3]


def execute_search_batch(batch_description: str, search_query: str) -> list[Paper]:
    """Execute one search batch via Kimi API with web_search tool."""
    client = _get_kimi_client()

    system_prompt = (
        "你是一个学术文献检索助手。请使用 web_search 工具搜索学术论文。"
        "对每个搜索结果，提取以下信息并以 JSON 格式返回：\n"
        '{"papers": [{"title": "...", "authors": ["..."], "venue": "...", '
        '"year": 2024, "url": "...", "abstract": "...", "keywords": ["..."]}]}\n'
        "只返回 JSON，不要其他内容。最多返回 8 篇论文。"
    )

    try:
        response = client.chat.completions.create(
            model="kimi-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"搜索以下学术论文：{search_query}\n批次说明：{batch_description}"},
            ],
            tools=[{"type": "web_search"}],
            temperature=0.3,
            max_tokens=4096,
        )

        content = response.choices[0].message.content or ""

        # Try to extract JSON from response
        json_match = re.search(r'\{[\s\S]*"papers"[\s\S]*\}', content)
        if json_match:
            data = json.loads(json_match.group())
        else:
            # Try parsing the whole content
            data = json.loads(content)

        papers = []
        for item in data.get("papers", []):
            papers.append(Paper(
                title=item.get("title", ""),
                authors=item.get("authors", []),
                venue=item.get("venue", ""),
                year=item.get("year"),
                url=item.get("url", ""),
                abstract=item.get("abstract", ""),
                keywords=item.get("keywords", []),
                source=_detect_source(item.get("url", "")),
            ))
        return papers

    except (json.JSONDecodeError, KeyError) as e:
        # Fallback: try to parse papers from text manually
        return _parse_papers_from_text(content) if 'content' in dir() else []
    except Exception as e:
        print(f"[search_engine] Kimi API 调用失败: {e}")
        return []


def _detect_source(url: str) -> str:
    if "arxiv.org" in url:
        return "arxiv"
    if "openreview.net" in url:
        return "openreview"
    if "ieee.org" in url:
        return "ieee"
    if "acm.org" in url:
        return "acm"
    if "usenix.org" in url:
        return "usenix"
    return "unknown"


def _parse_papers_from_text(text: str) -> list[Paper]:
    """Fallback: parse papers from unstructured text."""
    papers = []
    # Simple pattern matching for common paper formats
    title_pattern = re.compile(r'(?:\d+\.?\s*)?["\']?(.+?)["\']?(?:\s*\(?\d{4}\)?)')
    # Return empty if we can't parse
    return papers


def _title_similarity(t1: str, t2: str) -> float:
    """Compute title similarity for deduplication."""
    # Normalize
    t1 = re.sub(r'[^a-z0-9\s]', '', t1.lower()).strip()
    t2 = re.sub(r'[^a-z0-9\s]', '', t2.lower()).strip()
    return SequenceMatcher(None, t1, t2).ratio()


def deduplicate(papers: list[Paper], threshold: float = 0.85) -> list[Paper]:
    """Remove duplicate papers (same paper from different sources)."""
    unique: list[Paper] = []
    for paper in papers:
        is_dup = False
        for existing in unique:
            if _title_similarity(paper.title, existing.title) >= threshold:
                # Keep the one with better metadata (prefer non-arxiv URLs)
                if "arxiv.org" in existing.url and "arxiv.org" not in paper.url:
                    unique.remove(existing)
                    unique.append(paper)
                is_dup = True
                break
        if not is_dup:
            unique.append(paper)
    return unique


def rank_results(papers: list[Paper], query: str) -> list[SearchResult]:
    """Rank papers by relevance to query and assign scores."""
    query_terms = set(query.lower().split())

    results = []
    for paper in papers:
        text = (paper.title + " " + paper.abstract + " " + " ".join(paper.keywords)).lower()
        text_words = set(text.split())

        # Simple term overlap scoring
        overlap = len(query_terms & text_words)
        # Bonus for title match
        title_match = sum(1 for t in query_terms if t in paper.title.lower())

        score = min(5, max(1, 2 + overlap // 3 + title_match))

        reason_parts = []
        if title_match >= 3:
            reason_parts.append("标题高度匹配")
        elif overlap > 5:
            reason_parts.append("内容相关度高")
        else:
            reason_parts.append("领域相关")

        if paper.venue:
            reason_parts.append(f"发表于 {paper.venue}")

        results.append(SearchResult(
            paper=paper,
            relevance_score=score,
            recommendation_reason="；".join(reason_parts),
        ))

    results.sort(key=lambda r: r.relevance_score, reverse=True)
    return results


def search_papers(
    query: str,
    venues: list[Venue] | None = None,
    years: tuple[int, int] | None = None,
    max_results: int = 15,
) -> list[SearchResult]:
    """完整的搜索流程：推荐会议 → 构建批次 → 执行搜索 → 去重 → 排序."""
    if venues is None:
        venues = recommend_venues(query)

    batches = build_search_batches(query, venues, years)

    all_papers: list[Paper] = []
    for i, batch in enumerate(batches):
        papers = execute_search_batch(batch["description"], batch["query"])
        for p in papers:
            p.keywords = p.keywords if p.keywords else []  # ensure list
        all_papers.extend(papers)

    all_papers = deduplicate(all_papers)
    results = rank_results(all_papers, query)

    # Assign batch numbers
    for i, r in enumerate(results):
        r.batch_number = (i // 8) + 1

    return results[:max_results]
