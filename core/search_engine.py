"""搜索引擎 — WebBridge 浏览器检索 + DeepSeek 查询优化与结果评估."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.parse
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from openai import OpenAI
from ruamel.yaml import YAML

from .paper import (
    EvaluationResult,
    Paper,
    PaperEval,
    QueryAnalysis,
    SearchResult,
    Venue,
    VenueType,
)

_yaml = YAML(typ="safe")
_WEBRIDGE_URL = "http://127.0.0.1:10086/command"
_SEARCH_SESSION = "paper-search"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_deepseek_client() -> OpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 环境变量未设置")
    return OpenAI(api_key=api_key, base_url=base_url)


def _call_deepseek(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
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
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _webbridge_call(action: str, args: dict | None = None, session: str = _SEARCH_SESSION) -> dict:
    body = {"action": action, "session": session}
    if args:
        body["args"] = args
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        _WEBRIDGE_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("ok"):
                return result.get("data", {})
            print(f"[webbridge] Error: {result}")
            return {}
    except Exception as e:
        print(f"[webbridge] Call failed: {e}")
        return {}


def _arxiv_search_url(query: str, start: int = 0) -> str:
    params = urllib.parse.urlencode({"query": query, "searchtype": "all", "start": start})
    return f"https://arxiv.org/search/?{params}"


def _extract_papers_js() -> str:
    return """
(() => {
  const results = [];
  document.querySelectorAll('li.arxiv-result').forEach(li => {
    const titleEl = li.querySelector('p.title');
    const title = titleEl ? titleEl.textContent.replace(/\\s+/g, ' ').trim() : '';
    const authors = Array.from(li.querySelectorAll('p.authors a')).map(a => a.textContent.trim());
    const abstractFull = li.querySelector('span.abstract-full');
    const abstractShort = li.querySelector('span.abstract-short');
    const abstract = (abstractFull || abstractShort || '').textContent.replace(/\\s+/g, ' ').trim();
    const urlEl = li.querySelector('p.list-title a');
    const url = urlEl ? urlEl.href : '';
    let year = null;
    const idMatch = url.match(/arxiv\\.org\\/abs\\/(\\d{2})\\d{2}\\./);
    if (idMatch) { year = 2000 + parseInt(idMatch[1]); }
    const subjectEl = li.querySelector('span.primary-subject');
    const venue = subjectEl ? subjectEl.textContent.trim() : '';
    results.push({title, authors, abstract, url, year, venue, keywords: []});
  });
  return JSON.stringify(results.slice(0, 12));
})()
"""


# ---------------------------------------------------------------------------
# Venue management
# ---------------------------------------------------------------------------

def _load_venues(config_path: str | Path = "") -> dict:
    if not config_path:
        config_path = Path(__file__).parent.parent / "config" / "venues.yaml"
    with open(config_path) as f:
        return _yaml.load(f)


def _flatten_venues(venues_data: dict) -> list[Venue]:
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


def recommend_venues(
    query: str,
    analysis: QueryAnalysis | None = None,
    max_venues: int = 5,
) -> list[Venue]:
    """Recommend venues based on the query, using AI analysis when available.

    When QueryAnalysis is provided (from analyze_query()), uses AI-suggested
    venues and domain. Falls back to keyword matching otherwise.
    """
    venues_data = _load_venues()
    all_venues = _flatten_venues(venues_data)

    # Build a lookup: normalized name → Venue
    venue_by_name: dict[str, Venue] = {}
    venue_by_name_lower: dict[str, Venue] = {}
    for v in all_venues:
        venue_by_name[v.name] = v
        venue_by_name_lower[v.name.lower()] = v
        for alias in v.aliases:
            venue_by_name_lower[alias.lower()] = v

    scored: list[tuple[float, Venue]] = []

    if analysis is not None and analysis.suggested_venues:
        # AI-powered: match AI-suggested venue names against our database
        ai_domain = analysis.domain
        ai_venues = analysis.suggested_venues

        for v in all_venues:
            score = 0.0
            # Exact or fuzzy match against AI-suggested venues
            for ai_v in ai_venues:
                ai_v_lower = ai_v.lower()
                if v.name.lower() == ai_v_lower or ai_v_lower in v.name.lower():
                    score += 5
                elif v.full_name.lower() == ai_v_lower or ai_v_lower in v.full_name.lower():
                    score += 4
                elif any(ai_v_lower in a.lower() for a in v.aliases):
                    score += 4
                # Partial word match (e.g. "S&P" vs "IEEE Symposium on Security")
                elif any(w in v.full_name.lower() for w in ai_v_lower.split() if len(w) > 2):
                    score += 2

            # Domain match bonus
            if v.domain == ai_domain:
                score += 3

            # Search term presence in venue name
            search_text = (analysis.translated_query or query).lower()
            if v.name.lower() in search_text or any(a.lower() in search_text for a in v.aliases):
                score += 3

            if score > 0:
                scored.append((score, v))
    else:
        # Fallback: keyword-based domain detection (unchanged from original)
        query_lower = query.lower()
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
                domain_scores["general_ai"] += 0.3

        primary_domain = max(domain_scores, key=domain_scores.get)
        for v in all_venues:
            score = 0.0
            if v.domain == primary_domain:
                score += 2
            elif domain_scores.get(v.domain, 0) > 0:
                score += 1
            if v.name.lower() in query_lower or any(a.lower() in query_lower for a in v.aliases):
                score += 3
            scored.append((score, v))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result = []
    for _, v in scored:
        if v.name not in seen:
            seen.add(v.name)
            result.append(v)

    return result[:max_venues] if result else all_venues[:max_venues]


# ---------------------------------------------------------------------------
# DeepSeek-powered query analysis (translation + concept extraction)
# ---------------------------------------------------------------------------

def analyze_query(query: str) -> QueryAnalysis:
    """Pre-search query analysis: detect language, translate, extract academic concepts,
    expand synonyms, and suggest search terms.

    This runs BEFORE venue recommendation and search batch building, so all
    downstream steps benefit from the translated/expanded query.
    """
    # Quick heuristic: detect if query contains Chinese characters
    has_chinese = bool(re.search(r'[一-鿿]', query))

    system_prompt = (
        "You are a research librarian expert specializing in academic literature search. "
        "Analyze the user's search query and prepare it for searching on arXiv.\n\n"
        "Steps:\n"
        "1. Detect language. If the query is in Chinese (or mixed), translate it to "
        "   precise English academic terminology. Be specific — use the terms that "
        "   researchers actually use in paper titles.\n"
        "2. Extract 3-5 key academic concepts from the query.\n"
        "3. For each key concept, provide 2-4 English synonyms or related terms that "
        "   appear in academic paper titles.\n"
        "4. Generate 3 arXiv-optimized search term combinations (different angles).\n"
        "5. Identify the most relevant research domain (robotics, ai_security, general_ai, "
        "   computer_vision, nlp, systems, etc.).\n"
        "6. Suggest 3-5 specific venue names (conferences/journals) where this topic "
        "   is commonly published.\n\n"
        "Return ONLY a JSON object:\n"
        '{"is_chinese": <bool>, "translated_query": "...", '
        '"key_concepts": ["...", "..."], '
        '"expanded_terms": {"concept1": ["synonym1", "synonym2"], ...}, '
        '"arxiv_search_terms": ["query1", "query2", "query3"], '
        '"domain": "...", "suggested_venues": ["...", "..."]}'
    )

    user_prompt = f'Search query: "{query}"'

    try:
        raw = _call_deepseek(system_prompt, user_prompt, temperature=0.3)
        data = _extract_json(raw)

        return QueryAnalysis(
            original_query=query,
            translated_query=data.get("translated_query", query),
            is_chinese=data.get("is_chinese", has_chinese),
            key_concepts=data.get("key_concepts", []),
            expanded_terms=data.get("expanded_terms", {}),
            arxiv_search_terms=data.get("arxiv_search_terms", []),
            domain=data.get("domain", ""),
            suggested_venues=data.get("suggested_venues", []),
        )
    except Exception as e:
        print(f"  Query analysis failed: {e}, using original query")
        return QueryAnalysis(
            original_query=query,
            translated_query=query,
            is_chinese=has_chinese,
            key_concepts=query.split(),
            arxiv_search_terms=[query],
        )


# ---------------------------------------------------------------------------
# DeepSeek-powered query optimization (search batch building)
# ---------------------------------------------------------------------------

def build_search_batches(
    query: str,
    venues: list[Venue],
    years: tuple[int, int] | None = None,
    analysis: QueryAnalysis | None = None,
) -> list[dict]:
    """Use DeepSeek (or cached analysis) to produce 3 tiers of arXiv search queries.

    When a QueryAnalysis from analyze_query() is provided, uses the pre-computed
    translation and search terms instead of calling DeepSeek again.

    Returns 3 batches:
      - tier 1: precise (AND-based)
      - tier 2: synonym expanded (OR-based)
      - tier 3: broad / fallback (fewer keywords)
    """
    import datetime
    current_year = datetime.date.today().year
    if years is None:
        years = (current_year - 3, current_year)

    venue_names = [v.name for v in venues]

    # If we already have AI analysis, use it directly (no extra API call)
    if analysis is not None and analysis.translated_query:
        translated = analysis.translated_query
        print(f"  Query: {query} → {translated}")

        # Build batches from analysis results
        batches = []
        search_terms = analysis.arxiv_search_terms if analysis.arxiv_search_terms else [translated]

        if len(search_terms) >= 3:
            batches = [
                {"description": f"精确匹配: {search_terms[0]}", "query": search_terms[0]},
                {"description": f"同义扩展: {search_terms[1]}", "query": search_terms[1]},
                {"description": f"宽泛搜索: {search_terms[2]}", "query": search_terms[2]},
            ]
        elif len(search_terms) == 2:
            batches = [
                {"description": f"精确匹配: {search_terms[0]}", "query": search_terms[0]},
                {"description": f"扩展搜索: {search_terms[1]}", "query": search_terms[1]},
                {"description": f"宽泛搜索: {translated}", "query": translated},
            ]
        else:
            batches = [
                {"description": f"精确匹配: {translated}", "query": translated},
                {
                    "description": f"同义扩展: {translated}",
                    "query": " OR ".join(f'"{v.name}"' for v in venues[:3]) + f" ({translated})",
                },
                {
                    "description": f"宽泛搜索: {', '.join(venue_names[:3])}",
                    "query": " OR ".join(translated.split()[:4]),
                },
            ]

        # Inject venue names into search queries for better targeting
        for batch in batches:
            if "query" in batch and venue_names:
                # Add top venue names to tier 1 for precision
                if "精确" in batch.get("description", ""):
                    batch["query"] = f'({batch["query"]}) AND ("{" OR ".join(venue_names[:2])}")'

        return batches[:3]

    # No analysis available — call DeepSeek for translation + batch building
    system_prompt = (
        "You are a research librarian expert. Your job is to take a user's search query "
        "(possibly in Chinese) and produce 3 tiers of arXiv search queries.\n\n"
        "Rules:\n"
        "- If the query is in Chinese, FIRST translate it to English academic terms.\n"
        "- arXiv uses AND, OR, and quotes for exact phrases.\n"
        "- Generate exactly 3 query tiers, from strictest to broadest.\n"
        "- Tier 1: precise match with AND between all key concepts.\n"
        "- Tier 2: synonym/related-term expansion using OR for each concept group.\n"
        "- Tier 3: broad search with only the 2-3 most essential keywords.\n"
        "- Keep each query under 150 characters.\n\n"
        "Return ONLY a JSON object with this structure:\n"
        '{"translated_query": "...", "batches": ['
        '  {"description": "...", "query": "..."},'
        '  {"description": "...", "query": "..."},'
        '  {"description": "...", "query": "..."}'
        ']}'
    )

    user_prompt = (
        f"User query: \"{query}\"\n"
        f"Related venues: {', '.join(venue_names)}\n"
        f"Years: {years[0]}-{years[1]}"
    )

    try:
        raw = _call_deepseek(system_prompt, user_prompt, temperature=0.3)
        data = _extract_json(raw)
        batches = data.get("batches", [])
        if batches and len(batches) >= 2:
            translated = data.get("translated_query", query)
            print(f"  DeepSeek 优化查询: {query} → {translated}")
            return batches[:3]
    except Exception as e:
        print(f"  DeepSeek 查询优化失败: {e}，使用原始查询")

    # Fallback: simple batches (using translated query if available)
    search_text = analysis.translated_query if analysis else query.strip()
    return [
        {"description": f"精确匹配: {search_text}", "query": search_text},
        {
            "description": f"同义扩展: {search_text}",
            "query": " OR ".join(f'"{v}"' for v in venue_names[:3]) + f" ({search_text})",
        },
        {
            "description": f"宽泛搜索: {', '.join(venue_names[:3])}",
            "query": " OR ".join(search_text.split()[:4] if search_text.split() else [search_text]),
        },
    ]


# ---------------------------------------------------------------------------
# WebBridge arXiv search
# ---------------------------------------------------------------------------

def _wait_for_arxiv_results(timeout_seconds: float = 10.0) -> bool:
    """Poll until arXiv search results appear on the page."""
    check_js = "document.querySelectorAll('li.arxiv-result').length"
    start = time.time()
    while time.time() - start < timeout_seconds:
        result = _webbridge_call("evaluate", {"code": check_js})
        count = result.get("value", 0)
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            # Brief extra wait for full render
            time.sleep(0.5)
            return True
        time.sleep(0.5)
    return False


def execute_search_batch(
    batch_description: str,
    search_query: str,
    max_retries: int = 2,
) -> list[Paper]:
    """Execute one search batch via WebBridge browser automation on arXiv.

    Retries on transient failures and waits for page content to load properly.
    """
    arxiv_url = _arxiv_search_url(search_query)

    for attempt in range(max_retries + 1):
        try:
            _webbridge_call("navigate", {"url": arxiv_url, "newTab": False})

            if not _wait_for_arxiv_results():
                if attempt < max_retries:
                    print(f"    页面加载超时，第 {attempt + 1} 次重试...")
                    continue
                print(f"    页面加载超时，已放弃")
                return []

            result = _webbridge_call("evaluate", {"code": _extract_papers_js()})
            raw = result.get("value", "[]")
            try:
                items = json.loads(raw)
            except json.JSONDecodeError:
                if attempt < max_retries:
                    print(f"    解析结果失败，第 {attempt + 1} 次重试...")
                    continue
                print(f"    解析结果失败，已放弃")
                return []

            papers: list[Paper] = []
            for item in items:
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

            print(f"    找到 {len(papers)} 篇候选")
            return papers

        except Exception as e:
            if attempt < max_retries:
                print(f"    WebBridge 调用失败 ({e})，第 {attempt + 1} 次重试...")
                time.sleep(1)
                continue
            print(f"    WebBridge 调用失败 ({e})，已放弃")
            return []

    return []


def _detect_source(url: str) -> str:
    for prefix in ["arxiv.org", "openreview.net", "ieee.org", "acm.org", "usenix.org"]:
        if prefix in url:
            return prefix.split(".")[0]
    return "unknown"


# ---------------------------------------------------------------------------
# AI Self-Evaluation
# ---------------------------------------------------------------------------

def evaluate_search_results(
    query: str,
    results: list[SearchResult],
) -> EvaluationResult:
    """Ask DeepSeek to evaluate whether the search results match the user's intent.

    Returns per-paper relevance scores, overall quality, diversity analysis,
    and alternative queries if results are poor.
    """
    if not results:
        return EvaluationResult(
            overall_quality=1,
            summary="No results found.",
            needs_retry=True,
            suggested_queries=_suggest_broader_queries(query),
        )

    # Compute diversity stats for the evaluation prompt
    venue_counts: dict[str, int] = {}
    first_author_counts: dict[str, int] = {}
    for r in results[:15]:
        v = r.paper.venue or "unknown"
        venue_counts[v] = venue_counts.get(v, 0) + 1
        fa = r.paper.authors[0] if r.paper.authors else "unknown"
        first_author_counts[fa] = first_author_counts.get(fa, 0) + 1

    dominant_venue = max(venue_counts, key=venue_counts.get)
    dominant_venue_ratio = venue_counts[dominant_venue] / min(len(results), 15)
    dominant_author = max(first_author_counts, key=first_author_counts.get)
    dominant_author_count = first_author_counts[dominant_author]

    diversity_note = ""
    if dominant_venue_ratio > 0.5:
        diversity_note += (
            f"WARNING: {dominant_venue_ratio:.0%} of results are from '{dominant_venue}'. "
            f"Consider this lack of venue diversity when scoring overall quality.\n"
        )
    if dominant_author_count >= 3:
        diversity_note += (
            f"WARNING: {dominant_author_count} papers share first author '{dominant_author}'. "
            f"Consider this lack of author diversity.\n"
        )

    paper_list = []
    for i, r in enumerate(results[:15]):
        paper_list.append(
            f"[{i+1}] Title: {r.paper.title}\n"
            f"    Authors: {', '.join(r.paper.authors[:3])}\n"
            f"    Venue: {r.paper.venue}, Year: {r.paper.year}\n"
            f"    Abstract: {(r.paper.abstract or '')[:200]}"
        )
    papers_text = "\n\n".join(paper_list)

    system_prompt = (
        "You are a research evaluator. You will be given a user's original search query "
        "and a list of search results. Your job is to evaluate whether each paper is "
        "relevant to the query.\n\n"
        "Rules:\n"
        "- Score each paper 1-5 (5=highly relevant, 1=completely irrelevant).\n"
        "- Flag papers that are clearly irrelevant (is_irrelevant=true).\n"
        "- Give an overall quality score 1-5 for the result set.\n"
        "- Consider result DIVERSITY: if many papers are from the same venue or same "
        "  first author, reduce the overall_quality score (the diversity warnings are "
        "  provided for this purpose).\n"
        "- If overall quality <= 2, suggest 2-3 alternative broader/shorter search queries "
        "  (English only, optimized for arXiv).\n"
        "- If the query language and paper language don't match, note that.\n"
        "- Write reasoning and summary in Chinese (the user reads Chinese).\n\n"
        "Return ONLY a JSON object:\n"
        '{"overall_quality": <1-5>, "summary": "...", '
        '"paper_evals": [{"title": "...", "relevance_score": <1-5>, '
        '"reasoning": "...", "is_irrelevant": <bool>}], '
        '"suggested_queries": [...], "needs_retry": <bool>}'
    )

    user_prompt = (
        f"User query: \"{query}\"\n\n"
        f"{diversity_note}"
        f"Search results:\n{papers_text}"
    )

    try:
        raw = _call_deepseek(system_prompt, user_prompt, temperature=0.2)
        data = _extract_json(raw)

        paper_evals = []
        for pe in data.get("paper_evals", []):
            paper_evals.append(PaperEval(
                title=pe.get("title", ""),
                relevance_score=pe.get("relevance_score", 3),
                reasoning=pe.get("reasoning", ""),
                is_irrelevant=pe.get("is_irrelevant", False),
            ))

        # Apply a small programmatic diversity penalty to overall quality
        quality = data.get("overall_quality", 3)
        if dominant_venue_ratio > 0.6:
            quality = max(1, quality - 1)

        return EvaluationResult(
            overall_quality=quality,
            summary=data.get("summary", ""),
            paper_evals=paper_evals,
            suggested_queries=data.get("suggested_queries", []),
            needs_retry=data.get("needs_retry", False),
        )
    except Exception as e:
        print(f"  AI 评估失败: {e}")
        return EvaluationResult(
            overall_quality=3,
            summary=f"Evaluation unavailable: {e}",
        )


def _suggest_broader_queries(query: str) -> list[str]:
    """Generate broader fallback queries using DeepSeek when search returns nothing.

    Falls back to mechanical keyword reduction if the API is unavailable.
    """
    system_prompt = (
        "You are a research librarian. The user's search query returned ZERO results "
        "on arXiv. Generate 2-3 broader/shorter alternative English search queries "
        "that are more likely to find relevant papers.\n\n"
        "Rules:\n"
        "- Use fewer, more general keywords.\n"
        "- Remove overly specific qualifiers.\n"
        "- Keep each query under 80 characters.\n"
        "- Return ONLY a JSON object: {\"queries\": [\"...\", \"...\"]}"
    )

    try:
        raw = _call_deepseek(system_prompt, f'Query that returned 0 results: "{query}"', temperature=0.2)
        data = _extract_json(raw)
        queries = data.get("queries", [])
        if queries:
            return queries[:3]
    except Exception:
        pass

    # Mechanical fallback
    cleaned = re.sub(r'[^\w\s]', ' ', query)
    words = cleaned.strip().split()
    if len(words) <= 2:
        return [query]
    mid = len(words) // 2
    return [
        " ".join(words[:mid]),
        " ".join(words[-mid:]),
        " ".join(words[:2]),
    ]


# ---------------------------------------------------------------------------
# Helpers: AI score application & broader query generation
# ---------------------------------------------------------------------------

def _apply_ai_scores(results: list[SearchResult], evaluation: EvaluationResult) -> list[SearchResult]:
    """Override keyword-based scores with AI evaluation scores and re-sort."""
    if not evaluation.paper_evals:
        return results

    eval_by_title: dict[str, PaperEval] = {}
    for pe in evaluation.paper_evals:
        key = re.sub(r'[^a-z0-9]', '', pe.title.lower())
        eval_by_title[key] = pe

    for r in results:
        key = re.sub(r'[^a-z0-9]', '', r.paper.title.lower())
        if key in eval_by_title:
            ai_eval = eval_by_title[key]
            r.relevance_score = ai_eval.relevance_score
            if ai_eval.reasoning:
                r.recommendation_reason = ai_eval.reasoning

    results.sort(key=lambda r: r.relevance_score, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Evaluation persistence (cache evaluations to disk for feedback loop)
# ---------------------------------------------------------------------------

_EVAL_CACHE_DIR = Path(__file__).parent.parent / "config" / "eval_cache"


def _eval_cache_path(query: str) -> Path:
    import hashlib
    _EVAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    qhash = hashlib.md5(query.strip().lower().encode()).hexdigest()[:12]
    return _EVAL_CACHE_DIR / f"eval_{qhash}.json"


def load_cached_evaluation(query: str) -> EvaluationResult | None:
    """Load a previously cached evaluation, if it exists and is recent."""
    cache_path = _eval_cache_path(query)
    if not cache_path.exists():
        return None
    try:
        with open(cache_path) as f:
            data = json.load(f)
        age_days = (time.time() - data.get("cached_at", 0)) / 86400
        if age_days > 30:
            return None
        return EvaluationResult(**data.get("evaluation", {}))
    except Exception:
        return None


def save_evaluation(query: str, evaluation: EvaluationResult) -> None:
    """Cache an evaluation result to disk for future reference."""
    cache_path = _eval_cache_path(query)
    try:
        with open(cache_path, "w") as f:
            json.dump({
                "query": query,
                "evaluation": evaluation.model_dump(mode="json"),
                "cached_at": time.time(),
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_user_preferences() -> dict:
    """Load user preferences for boosting ranking (preferred venues/keywords)."""
    pref_path = Path(__file__).parent.parent / "config" / "user_profile.json"
    if not pref_path.exists():
        return {}
    try:
        with open(pref_path) as f:
            return json.load(f).get("preferences", {})
    except Exception:
        return {}


def boost_by_user_preferences(
    results: list[SearchResult],
    preferences: dict,
) -> list[SearchResult]:
    """Apply small boosts based on user's previously adopted venues and keywords."""
    preferred_venues = set(preferences.get("preferred_venues", []))
    preferred_kw = set(k.lower() for k in preferences.get("preferred_keywords", []))

    if not preferred_venues and not preferred_kw:
        return results

    for r in results:
        boost = 0
        if r.paper.venue and any(pv.lower() in r.paper.venue.lower() for pv in preferred_venues):
            boost += 1
        paper_kw = set(k.lower() for k in r.paper.keywords)
        if paper_kw & preferred_kw:
            boost += 0.5
        if boost > 0:
            r.relevance_score = min(5, r.relevance_score + round(boost))

    results.sort(key=lambda r: r.relevance_score, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Dedup & Rank (keyword-based, then overridden by AI evaluation)
# ---------------------------------------------------------------------------

def _title_similarity(t1: str, t2: str) -> float:
    t1 = re.sub(r'[^a-z0-9\s]', '', t1.lower()).strip()
    t2 = re.sub(r'[^a-z0-9\s]', '', t2.lower()).strip()
    return SequenceMatcher(None, t1, t2).ratio()


def deduplicate(papers: list[Paper], threshold: float = 0.85) -> list[Paper]:
    unique: list[Paper] = []
    for paper in papers:
        is_dup = False
        for existing in unique:
            if _title_similarity(paper.title, existing.title) >= threshold:
                if "arxiv.org" in existing.url and "arxiv.org" not in paper.url:
                    unique.remove(existing)
                    unique.append(paper)
                is_dup = True
                break
        if not is_dup:
            unique.append(paper)
    return unique


# Venue prestige tiers (higher = more selective / prestigious)
_VENUE_PRESTIGE: dict[str, int] = {
    "ICRA": 4, "IROS": 4, "RSS": 5, "CoRL": 4, "Humanoids": 3,
    "IEEE T-RO": 5, "IEEE RA-L": 4, "IJRR": 5, "T-ASE": 4, "T-MECH": 3,
    "IEEE S&P": 5, "ACM CCS": 5, "NDSS": 5, "USENIX Security": 5,
    "CRYPTO": 5, "EUROCRYPT": 5, "ASIACRYPT": 4, "TCC": 4,
    "IEEE TDSC": 4, "IEEE TIFS": 4, "PoPETs": 4,
    "ICML": 5, "NeurIPS": 5, "ICLR": 5, "AAAI": 4, "IJCAI": 4,
    "CVPR": 5, "ICCV": 5, "ECCV": 4, "ACL": 4,
    "JMLR": 5, "TPAMI": 5, "TMLR": 4,
}


def _venue_prestige_bonus(venue_str: str) -> float:
    """Return a 0.0-1.0 bonus based on venue prestige."""
    if not venue_str:
        return 0.0
    for name, tier in _VENUE_PRESTIGE.items():
        if name.lower() in venue_str.lower():
            return tier / 5.0
    return 0.3  # unknown venue gets small baseline


def _year_recency_bonus(year: int | None) -> float:
    """Return a bonus for recent papers (0.0-0.3)."""
    import datetime
    if year is None:
        return 0.0
    current = datetime.date.today().year
    age = current - year
    if age <= 1:
        return 0.3
    elif age <= 3:
        return 0.2
    elif age <= 5:
        return 0.1
    return 0.0


def rank_results(papers: list[Paper], query: str) -> list[SearchResult]:
    """Rank papers by a weighted combination of keyword overlap, venue prestige,
    year recency, and abstract quality.

    Scores are normalized to the 1-5 integer range after ranking.
    """
    import datetime

    query_terms = set(query.lower().split())
    scored: list[tuple[float, Paper, str]] = []

    for paper in papers:
        title_lower = paper.title.lower()
        abstract_lower = (paper.abstract or "").lower()
        keywords_lower = " ".join(paper.keywords).lower()

        # Keyword overlap in different fields
        title_terms = set(title_lower.split())
        abstract_terms = set(abstract_lower.split())
        kw_terms = set(keywords_lower.split())

        title_overlap = len(query_terms & title_terms)
        abstract_overlap = len(query_terms & abstract_terms)
        kw_overlap = len(query_terms & kw_terms)

        # Phrase match bonus: check if multi-word query phrases appear
        phrase_bonus = 0.0
        query_bigrams = set()
        qwords = query.lower().split()
        for i in range(len(qwords) - 1):
            query_bigrams.add(f"{qwords[i]} {qwords[i+1]}")
        for bigram in query_bigrams:
            if bigram in title_lower:
                phrase_bonus += 0.5
            if bigram in abstract_lower:
                phrase_bonus += 0.2

        # Weighted score (raw, will be normalized later)
        raw = (
            title_overlap * 1.5          # title matches are strongest signal
            + abstract_overlap * 0.4     # abstract matches matter
            + kw_overlap * 0.8           # keyword matches
            + phrase_bonus               # phrase match bonus
            + _venue_prestige_bonus(paper.venue) * 2.0
            + _year_recency_bonus(paper.year) * 2.0
            + (0.3 if len(paper.abstract or "") > 200 else 0.0)  # substantial abstract
        )

        # Build reason
        reason_parts = []
        if title_overlap >= 3 or phrase_bonus >= 1.0:
            reason_parts.append("标题高度匹配")
        elif title_overlap >= 1:
            reason_parts.append("标题部分匹配")
        if abstract_overlap > 5:
            reason_parts.append("摘要高度相关")
        elif abstract_overlap > 2:
            reason_parts.append("摘要部分相关")
        if kw_overlap > 0:
            reason_parts.append(f"关键词匹配({kw_overlap}项)")
        if paper.venue:
            venue_prestige = _venue_prestige_bonus(paper.venue)
            if venue_prestige >= 0.8:
                reason_parts.append(f"顶会/{paper.venue}")
            elif venue_prestige >= 0.4:
                reason_parts.append(f"发表于 {paper.venue}")
        if paper.year:
            age = datetime.date.today().year - paper.year
            if age <= 1:
                reason_parts.append("最新论文")
            elif age <= 3:
                reason_parts.append("较新论文")
        if not reason_parts:
            reason_parts.append("领域相关")

        scored.append((raw, paper, "；".join(reason_parts)))

    # Normalize raw scores to 1-5 integer range
    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    raw_scores = [s[0] for s in scored]
    min_raw, max_raw = raw_scores[-1], raw_scores[0]

    results = []
    for raw, paper, reason in scored:
        if max_raw > min_raw:
            normalized = 1 + 4 * (raw - min_raw) / (max_raw - min_raw)
        else:
            normalized = 3.0
        score = max(1, min(5, round(normalized)))

        results.append(SearchResult(
            paper=paper,
            relevance_score=score,
            recommendation_reason=reason,
        ))

    return results


# ---------------------------------------------------------------------------
# Main search pipeline
# ---------------------------------------------------------------------------

def search_papers(
    query: str,
    venues: list[Venue] | None = None,
    years: tuple[int, int] | None = None,
    max_results: int = 15,
    max_retries: int = 2,
    analysis: QueryAnalysis | None = None,
) -> tuple[list[SearchResult], EvaluationResult]:
    """Complete search pipeline: analyze → venues → batches → search → evaluate → retry.

    1. analyze_query() translates Chinese→English, extracts concepts, expands terms
    2. recommend_venues() uses AI analysis to pick the right venues
    3. build_search_batches() uses the translated/expanded query
    4. execute_search_batch() runs the searches via WebBridge
    5. evaluate_search_results() scores and may trigger retries

    If `analysis` is provided (pre-computed by the caller for display), skip step 1.

    Returns (results, evaluation).
    """
    # Step 0: Pre-search query analysis (skip if caller already computed it)
    if analysis is None:
        print(f"\n  Query analysis...")
        analysis = analyze_query(query)

    # Step 1: Recommend venues using the analysis
    if venues is None:
        venues = recommend_venues(query, analysis=analysis)

    # Step 2: Build search batches using the analyzed query
    batches = build_search_batches(query, venues, years, analysis=analysis)

    all_papers: list[Paper] = []
    for i, batch in enumerate(batches):
        papers = execute_search_batch(batch["description"], batch["query"])
        for p in papers:
            p.keywords = p.keywords or []
        all_papers.extend(papers)

    # Use translated query for keyword matching against English paper content
    search_query = analysis.translated_query or query

    all_papers = deduplicate(all_papers)
    results = rank_results(all_papers, search_query)

    # AI self-evaluation (use cache if available and recent)
    cached = load_cached_evaluation(query)
    if cached is not None:
        print(f"\n  使用缓存的 AI 评估...")
        evaluation = cached
        results = _apply_ai_scores(results, evaluation)
    else:
        print(f"\n  AI 自评中...")
        evaluation = evaluate_search_results(query, results)
        results = _apply_ai_scores(results, evaluation)
        save_evaluation(query, evaluation)

    # Retry with suggested queries if evaluation says results are poor
    retry_count = 0
    while evaluation.needs_retry and evaluation.suggested_queries and retry_count < max_retries:
        retry_count += 1
        print(f"\n  AI 认为结果质量不足，尝试更宽泛的查询 (第 {retry_count} 次)...")
        for alt_query in evaluation.suggested_queries[:2]:
            print(f"    尝试: \"{alt_query}\"")
            papers = execute_search_batch(f"重试: {alt_query}", alt_query)
            for p in papers:
                p.keywords = p.keywords or []
            all_papers.extend(papers)

        all_papers = deduplicate(all_papers)
        results = rank_results(all_papers, search_query)

        # Re-evaluate
        evaluation = evaluate_search_results(query, results)
        results = _apply_ai_scores(results, evaluation)
        save_evaluation(query, evaluation)

    # Boost results based on learned user preferences
    preferences = load_user_preferences()
    if preferences:
        results = boost_by_user_preferences(results, preferences)

    for i, r in enumerate(results):
        r.batch_number = (i // 8) + 1

    return results[:max_results], evaluation
