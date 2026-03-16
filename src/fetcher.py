"""
论文抓取模块
- arXiv：按类别+关键词抓取预印本（7天内）
- Semantic Scholar：用 bulk search 按venue直接拉取最新论文（30天内）
  - 专业期刊（TED/EDL/TCAD等）：全部送LLM分析
  - 综合期刊（APL/NC/NE）：先用关键词粗筛摘要，再送LLM分析
"""

import arxiv
import requests
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)


def fetch_arxiv_papers(categories: List[str], core_keywords: List[str],
                        max_per_category: int = 50) -> List[Dict]:
    """从 arXiv 抓取最新论文，仅用 core 关键词查询"""
    papers = []
    seen_ids = set()
    kw_query = " OR ".join([f'abs:"{kw}"' for kw in core_keywords])

    for category in categories:
        logger.info(f"正在抓取 arXiv 类别: {category}")
        try:
            query = f"cat:{category} AND ({kw_query})"
            search = arxiv.Search(
                query=query,
                max_results=max_per_category,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            for result in search.results():
                paper_id = result.entry_id
                if paper_id in seen_ids:
                    continue
                seen_ids.add(paper_id)

                published = result.published.replace(tzinfo=None)
                if published < datetime.now() - timedelta(days=7):
                    continue

                papers.append({
                    "source": "arXiv",
                    "id": paper_id,
                    "title": result.title.strip(),
                    "authors": [a.name for a in result.authors],
                    "abstract": result.summary.strip(),
                    "published": published.strftime("%Y-%m-%d"),
                    "url": result.entry_id,
                    "venue": f"arXiv:{category}",
                    "doi": result.doi or "",
                })
            time.sleep(1)
        except Exception as e:
            logger.error(f"抓取 arXiv {category} 失败: {e}")

    logger.info(f"arXiv 共抓取到 {len(papers)} 篇论文")
    return papers


# 专业期刊：本身就是目标领域，全部送LLM分析
SPECIALIST_VENUES = [
    "IEEE Transactions on Electron Devices",
    "IEEE Electron Device Letters",
    "IEEE Transactions on Computer-Aided Design of Integrated Circuits and Systems",
    "International Electron Devices Meeting",
    "International Memory Workshop",
    "International Reliability Physics Symposium",
]

# 综合期刊：覆盖面广，需要关键词粗筛后再送LLM分析
BROAD_VENUES = [
    "Nature Electronics",
    "Nature Communications",
    "Applied Physics Letters",
]


def _keyword_match(paper_item: dict, keywords: List[str]) -> bool:
    """检查论文标题或摘要是否包含任意关键词（大小写不敏感）"""
    title = (paper_item.get("title") or "").lower()
    abstract = (paper_item.get("abstract") or "").lower()
    text = title + " " + abstract
    return any(kw.lower() in text for kw in keywords)


def _parse_paper(item: dict) -> dict:
    """将Semantic Scholar返回的item转换为统一格式"""
    pub_date = item.get("publicationDate") or ""
    authors_data = item.get("authors", [])
    pdf_url = (item.get("openAccessPdf") or {}).get("url", "")
    doi = (item.get("externalIds") or {}).get("DOI", "")

    return {
        "source": "Semantic Scholar",
        "id": item.get("paperId", ""),
        "title": (item.get("title") or "").strip(),
        "authors": [a.get("name", "") for a in authors_data],
        "abstract": (item.get("abstract") or "").strip(),
        "published": pub_date[:10] if pub_date else str(item.get("year", "")),
        "url": pdf_url or f"https://www.semanticscholar.org/paper/{item.get('paperId','')}",
        "venue": item.get("venue", ""),
        "doi": doi,
    }


def _fetch_venue(venue: str, headers: dict, cutoff: datetime,
                 keywords: List[str] = None) -> List[Dict]:
    """
    抓取单个venue的近期论文。
    keywords不为None时，对每篇论文做关键词粗筛。
    """
    bulk_url = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
    fields = "paperId,title,authors,abstract,year,publicationDate,venue,externalIds,openAccessPdf"

    resp = None
    for attempt in range(3):
        try:
            resp = requests.get(bulk_url, params={
                "venue": venue,
                "fields": fields,
                "sort": "publicationDate:desc",
            }, headers=headers, timeout=15)
            if resp.status_code == 429:
                wait_time = 3 * (2 ** attempt)
                logger.warning(f"限速，等待 {wait_time}s 后重试...")
                time.sleep(wait_time)
                continue
            break
        except Exception as e:
            logger.error(f"请求异常: {e}")
            time.sleep(5)

    if resp is None or resp.status_code != 200:
        logger.warning(f"请求失败，跳过: {venue}")
        return []

    papers = []
    for item in resp.json().get("data", []):
        # 时间过滤（结果按日期降序，超期即停止）
        pub_date = item.get("publicationDate") or ""
        if pub_date:
            try:
                if datetime.strptime(pub_date[:10], "%Y-%m-%d") < cutoff:
                    break
            except Exception:
                pass
        elif item.get("year", 0) < datetime.now().year - 1:
            break

        if not item.get("abstract"):
            continue

        # 综合期刊：关键词粗筛
        if keywords and not _keyword_match(item, keywords):
            continue

        papers.append(_parse_paper(item))

    return papers


def fetch_semantic_scholar_papers(venues: List[str],
                                   core_keywords: List[str],
                                   broad_keywords: List[str],
                                   max_results: int = 50,
                                   api_key: str = "") -> List[Dict]:
    """
    用 bulk search API 按venue拉取最新论文（30天内）。
    专业期刊全部送LLM分析；综合期刊先用 core+broad 关键词粗筛再送LLM分析。
    """
    papers = []
    seen_ids = set()
    headers = {"x-api-key": api_key} if api_key else {}
    cutoff = datetime.now() - timedelta(days=30)
    all_keywords = core_keywords + broad_keywords

    # 专业期刊：全量拉取
    for venue in SPECIALIST_VENUES:
        logger.info(f"Semantic Scholar [专业期刊] {venue}")
        results = _fetch_venue(venue, headers, cutoff, keywords=None)
        new = [p for p in results if p["id"] not in seen_ids]
        seen_ids.update(p["id"] for p in new)
        papers.extend(new)
        logger.info(f"  -> 命中 {len(new)} 篇")
        time.sleep(1.5)

    # 综合期刊：core+broad 关键词粗筛
    for venue in BROAD_VENUES:
        logger.info(f"Semantic Scholar [综合期刊] {venue}")
        results = _fetch_venue(venue, headers, cutoff, keywords=all_keywords)
        new = [p for p in results if p["id"] not in seen_ids]
        seen_ids.update(p["id"] for p in new)
        papers.extend(new)
        logger.info(f"  -> 命中 {len(new)} 篇（关键词粗筛后）")
        time.sleep(1.5)

    logger.info(f"Semantic Scholar 共抓取到 {len(papers)} 篇论文")
    return papers


def deduplicate_papers(papers: List[Dict]) -> List[Dict]:
    """基于标题去重"""
    seen_titles = set()
    unique = []
    for p in papers:
        title_key = p["title"].lower().strip()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(p)
    logger.info(f"去重后剩余 {len(unique)} 篇论文")
    return unique