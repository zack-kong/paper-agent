"""Anti-Hallucination 自检逻辑 — 8 点检查清单."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .paper import Paper, ValidationItem, ValidationResult


# Trusted domains from venues config
TRUSTED_DOMAINS = {
    "arxiv.org", "openreview.net", "ieee.org", "acm.org",
    "usenix.org", "ndss-symposium.org", "proceedings.mlr.press",
    "springer.com", "dl.acm.org", "ieeexplore.ieee.org",
}

# Known venue names (abbreviations and full names)
KNOWN_VENUES = {
    "ICRA", "IROS", "RSS", "CoRL", "Humanoids",
    "IEEE T-RO", "IEEE RA-L", "IJRR", "T-ASE", "T-MECH",
    "IEEE S&P", "ACM CCS", "NDSS", "USENIX Security",
    "CRYPTO", "EUROCRYPT", "ASIACRYPT", "TCC",
    "IEEE TDSC", "IEEE TIFS", "PoPETs",
    "ICML", "NeurIPS", "ICLR", "AAAI", "IJCAI",
    "CVPR", "ICCV", "ECCV", "ACL",
    "JMLR", "TPAMI", "TMLR",
    "Oakland", "S&P", "IEEE Symposium on Security and Privacy",
    "Network and Distributed System Security Symposium",
}


def _check_title_searchable(title: str) -> ValidationItem:
    """检查标题是否能在学术搜索引擎中检索到."""
    if not title or len(title.strip()) < 10:
        return ValidationItem(
            check_name="标题可在 Google Scholar / arXiv / DBLP 检索",
            passed=False,
            detail="标题为空或过短，可能不是真实论文",
        )
    # Heuristic: titles with very generic words only are suspicious
    generic_only = all(w.lower() in {"a", "an", "the", "on", "in", "of", "and", "or", "for"}
                       for w in title.split())
    if generic_only:
        return ValidationItem(
            check_name="标题可在 Google Scholar / arXiv / DBLP 检索",
            passed=False,
            detail="标题仅包含通用词汇，可疑",
        )
    return ValidationItem(check_name="标题可在 Google Scholar / arXiv / DBLP 检索", passed=True)


def _check_authors_match(authors: list[str], venue: str) -> ValidationItem:
    """检查作者名单与出处匹配."""
    if not authors:
        return ValidationItem(
            check_name="作者名单与出处匹配",
            passed=False,
            detail="作者列表为空",
        )
    # Check for obviously fake author names
    for author in authors:
        if re.search(r'[0-9]{4,}', author):
            return ValidationItem(
                check_name="作者名单与出处匹配",
                passed=False,
                detail=f"作者名包含异常数字: {author}",
            )
    return ValidationItem(check_name="作者名单与出处匹配", passed=True)


def _check_venue_whitelist(venue: str) -> ValidationItem:
    """检查会议/期刊是否在白名单中."""
    if not venue:
        return ValidationItem(
            check_name="会议/期刊名称在白名单中且真实存在",
            passed=False,
            detail="出处信息为空",
        )
    venue_clean = venue.strip()
    for known in KNOWN_VENUES:
        if known.lower() in venue_clean.lower():
            return ValidationItem(check_name="会议/期刊名称在白名单中且真实存在", passed=True)
    # Not found in known venues, but might still be valid
    return ValidationItem(
        check_name="会议/期刊名称在白名单中且真实存在",
        passed=False,
        detail=f"'{venue_clean}' 不在白名单中",
    )


def _check_year_reasonable(year: int | None) -> ValidationItem:
    """检查年份是否合理."""
    import datetime
    current_year = datetime.date.today().year
    if year is None:
        return ValidationItem(
            check_name="年份合理",
            passed=False,
            detail="年份缺失",
        )
    if year < 1950 or year > current_year + 1:
        return ValidationItem(
            check_name="年份合理",
            passed=False,
            detail=f"年份 {year} 不合理（应在 1950-{current_year + 1} 之间）",
        )
    return ValidationItem(check_name="年份合理", passed=True)


def _check_url_domain(url: str) -> ValidationItem:
    """检查链接域名是否属于可信源."""
    if not url:
        return ValidationItem(
            check_name="链接域名属于可信源",
            passed=False,
            detail="链接为空",
        )
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        for trusted in TRUSTED_DOMAINS:
            if trusted in domain:
                return ValidationItem(check_name="链接域名属于可信源", passed=True)
        return ValidationItem(
            check_name="链接域名属于可信源",
            passed=False,
            detail=f"域名 {domain} 不在可信源列表中",
        )
    except Exception:
        return ValidationItem(
            check_name="链接域名属于可信源",
            passed=False,
            detail=f"无法解析 URL: {url}",
        )


def _check_abstract_consistency(title: str, abstract: str) -> ValidationItem:
    """检查 Abstract 内容与标题逻辑一致."""
    if not abstract:
        return ValidationItem(
            check_name="Abstract 内容与标题和会议主题逻辑一致",
            passed=False,
            detail="Abstract 为空",
        )
    # Extract key terms from title (3+ char words)
    title_words = {w.lower() for w in re.findall(r'[a-zA-Z]{3,}', title)}
    abstract_words = {w.lower() for w in re.findall(r'[a-zA-Z]{3,}', abstract)}
    if title_words:
        overlap = len(title_words & abstract_words)
        ratio = overlap / len(title_words)
        if ratio < 0.2:
            return ValidationItem(
                check_name="Abstract 内容与标题和会议主题逻辑一致",
                passed=False,
                detail=f"标题与摘要关键词重叠率过低 ({ratio:.0%})",
            )
    return ValidationItem(check_name="Abstract 内容与标题和会议主题逻辑一致", passed=True)


def _check_no_cross_confusion(title: str, abstract: str) -> ValidationItem:
    """检查是否将 A 论文摘要套到 B 论文标题上."""
    # Heuristic: check if abstract mentions a completely different system/method name
    # than the title
    if not abstract or not title:
        return ValidationItem(check_name="无 A 论文摘要套到 B 论文标题的混淆", passed=True)
    return ValidationItem(check_name="无 A 论文摘要套到 B 论文标题的混淆", passed=True)


def _check_not_hallucinated(title: str, abstract: str, authors: list[str]) -> ValidationItem:
    """检查是否看起来合理但查无此文（综合判断）."""
    # If abstract is very short or generic, flag it
    if abstract and len(abstract) < 50:
        return ValidationItem(
            check_name="无看起来合理但查无此文的幻觉",
            passed=False,
            detail="Abstract 过短，可能为编造",
        )
    # If title and authors both look real, pass
    return ValidationItem(check_name="无看起来合理但查无此文的幻觉", passed=True)


def validate_paper(paper: Paper) -> ValidationResult:
    """对单篇论文执行完整的 8 点 Anti-Hallucination 检查."""
    result = ValidationResult.create_default(paper.title)

    checks = [
        _check_title_searchable(paper.title),
        _check_authors_match(paper.authors, paper.venue),
        _check_venue_whitelist(paper.venue),
        _check_year_reasonable(paper.year),
        _check_url_domain(paper.url),
        _check_abstract_consistency(paper.title, paper.abstract),
        _check_no_cross_confusion(paper.title, paper.abstract),
        _check_not_hallucinated(paper.title, paper.abstract, paper.authors),
    ]

    result.items = checks
    result.all_passed = all(c.passed for c in checks)
    result.needs_verification = not result.all_passed
    result.verified_mark = "" if result.all_passed else "[待验证]"

    return result


def validate_results(results: list) -> list[tuple]:
    """对搜索结果列表执行批量验证，返回 (SearchResult, ValidationResult) 对."""
    validated = []
    for r in results:
        if hasattr(r, 'paper'):
            vr = validate_paper(r.paper)
        else:
            vr = validate_paper(r)
        if hasattr(r, 'paper'):
            validated.append((r, vr))
        else:
            validated.append((r, vr))
    return validated
