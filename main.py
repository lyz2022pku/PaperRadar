#!/usr/bin/env python3
"""
PaperRadar 主程序
用法:
  python main.py            # 正常运行
  python main.py --test     # 测试模式（只抓少量，跳过Kimi，不发邮件）
  python main.py --send-test  # 发送测试邮件验证配置
"""

import argparse
import logging
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from src.fetcher import fetch_arxiv_papers, fetch_semantic_scholar_papers, deduplicate_papers
from src.analyzer import analyze_papers_with_kimi, compute_weights, compute_score
from src.mailer import send_email

# ── 日志配置 ──────────────────────────────────────────────────────────────────
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"digest_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("main")

# ── 持久化文件路径 ─────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).parent / "output"
SENT_FILE  = OUTPUT_DIR / "sent_ids.json"
CACHE_FILE = OUTPUT_DIR / "analysis_cache.json"


def _load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def _save_json(path: Path, data):
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_sent_ids() -> set:
    return set(_load_json(SENT_FILE, []))

def save_sent_ids(ids: set):
    _save_json(SENT_FILE, list(ids))

def load_cache() -> dict:
    return _load_json(CACHE_FILE, {})

def save_cache(cache: dict):
    _save_json(CACHE_FILE, cache)

def load_config() -> dict:
    config_path = Path(__file__).parent / "config" / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(test_mode: bool = False, send_test: bool = False):
    logger.info("=" * 50)
    logger.info("PaperRadar 启动")
    logger.info("=" * 50)

    config        = load_config()
    core_keywords = config["keywords"]["core"]
    broad_keywords = config["keywords"]["broad"]
    kimi_cfg      = config["llm"]
    ss_cfg        = config.get("semantic_scholar", {})

    # ── 发送测试邮件 ───────────────────────────────────────────────────────────
    if send_test:
        w_a, w_b, w_c = compute_weights(datetime.now().day)
        test_papers = [{
            "source": "arXiv",
            "title": "测试论文：配置验证邮件",
            "authors": ["张三", "李四"],
            "published": datetime.now().strftime("%Y-%m-%d"),
            "venue": "arXiv:cs.AR",
            "url": "https://arxiv.org",
            "analysis": "【研究背景】测试\n【科学问题】验证邮件配置\n【主要方法】SMTP\n【关键创新】配置正确\n【主要结论】邮件系统正常\n【A直接相关性】4分：直接相关\n【B创新性】3分：一般\n【C视野拓展性】2分：有限",
            "score_a": 4, "score_b": 3, "score_c": 2,
            "weighted_score": compute_score(4, 3, 2, w_a, w_b, w_c),
            "filtered": False,
        }]
        ok = send_email(test_papers, config["email"], w_a, w_b, w_c)
        logger.info("✅ 测试邮件发送成功！" if ok else "❌ 测试邮件发送失败")
        return

    # ── 加载持久化数据 ─────────────────────────────────────────────────────────
    sent_ids = load_sent_ids()
    cache    = load_cache()
    logger.info(f"已推送记录：{len(sent_ids)} 篇 | 分析缓存：{len(cache)} 篇")

    # ── 计算当日权重 ───────────────────────────────────────────────────────────
    today = datetime.now()
    w_a, w_b, w_c = compute_weights(today.day)
    logger.info(f"当日权重 → 直接相关性:{w_a:.0%}  创新性:{w_b:.0%}  视野拓展:{w_c:.0%}")

    # ── 步骤1：抓取论文 ────────────────────────────────────────────────────────
    logger.info("步骤1: 抓取 arXiv 论文...")
    arxiv_papers = fetch_arxiv_papers(
        categories=config["arxiv"]["categories"],
        core_keywords=core_keywords,
        max_per_category=3 if test_mode else config["arxiv"]["max_results_per_category"],
    )

    logger.info("步骤2: 抓取 Semantic Scholar 期刊论文...")
    ss_papers = []
    if ss_cfg.get("enabled", True):
        ss_papers = fetch_semantic_scholar_papers(
            venues=ss_cfg.get("target_venues", []),
            core_keywords=core_keywords,
            broad_keywords=broad_keywords,
            max_results=ss_cfg.get("max_results", 50),
            api_key=ss_cfg.get("api_key", ""),
        )

    all_papers = deduplicate_papers(arxiv_papers + ss_papers)

    # ── 步骤2：过滤已推送 ──────────────────────────────────────────────────────
    new_papers = [p for p in all_papers if p["id"] not in sent_ids]
    logger.info(f"去除已推送后：{len(new_papers)} 篇待处理（共抓取 {len(all_papers)} 篇）")

    # ── 步骤3：命中缓存 vs 需要Kimi分析 ───────────────────────────────────────
    cached_papers = []
    need_kimi     = []
    for p in new_papers:
        if p["id"] in cache:
            p.update(cache[p["id"]])
            cached_papers.append(p)
        else:
            need_kimi.append(p)

    logger.info(f"命中缓存：{len(cached_papers)} 篇 | 需要LLM分析：{len(need_kimi)} 篇")

    # ── 步骤4：Kimi分析 ────────────────────────────────────────────────────────
    newly_analyzed = []
    if not test_mode and need_kimi:
        logger.info(f"步骤3: 调用 LLM API 分析 {len(need_kimi)} 篇论文...")
        newly_analyzed = analyze_papers_with_kimi(
            papers=need_kimi,
            api_key=kimi_cfg["api_key"],
            model=kimi_cfg["model"],
            core_keywords=core_keywords,
            broad_keywords=broad_keywords,
            max_tokens=kimi_cfg.get("max_tokens", 500),
            base_url=kimi_cfg.get("base_url") or None,
        )
        for p in newly_analyzed:
            cache[p["id"]] = {
                "analysis":      p.get("analysis", ""),
                "score_a":       p.get("score_a", 3),
                "score_b":       p.get("score_b", 3),
                "score_c":       p.get("score_c", 3),
                "filtered":      p.get("filtered", False),
                "analyzed_date": today.strftime("%Y-%m-%d"),
            }
        save_cache(cache)
        logger.info(f"分析缓存已更新：共 {len(cache)} 篇")
    elif test_mode:
        logger.info("测试模式：跳过 Kimi 分析")
        for p in need_kimi[:3]:
            p.update({"analysis": "【测试】跳过分析",
                      "score_a": 3, "score_b": 3, "score_c": 3, "filtered": False})
            newly_analyzed.append(p)

    # ── 步骤5：合并、加权排序 ──────────────────────────────────────────────────
    all_candidates = cached_papers + newly_analyzed
    sendable = [p for p in all_candidates if not p.get("filtered", False)]

    for p in sendable:
        p["weighted_score"] = compute_score(
            p.get("score_a", 3), p.get("score_b", 3), p.get("score_c", 3),
            w_a, w_b, w_c
        )

    sendable.sort(key=lambda x: x["weighted_score"], reverse=True)

    max_papers = config["settings"]["max_papers_per_email"]
    to_send = sendable[:max_papers]
    logger.info(f"本次推送：{len(to_send)} 篇（候选 {len(sendable)} 篇）")

    if not to_send:
        logger.info("今日无新论文，跳过发送")
        return

    # ── 步骤6：保存今日结果 ────────────────────────────────────────────────────
    result_file = OUTPUT_DIR / f"digest_{today.strftime('%Y%m%d')}.json"
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(to_send, f, ensure_ascii=False, indent=2)
    logger.info(f"结果已保存: {result_file}")

    # ── 步骤7：发送邮件 & 更新sent_ids ────────────────────────────────────────
    if not test_mode:
        ok = send_email(to_send, config["email"], w_a, w_b, w_c)
        if ok:
            sent_ids.update(p["id"] for p in to_send)
            save_sent_ids(sent_ids)
            logger.info(f"✅ 邮件发送成功！sent_ids 更新至 {len(sent_ids)} 篇")
        else:
            logger.error("❌ 邮件发送失败，sent_ids 未更新")
    else:
        logger.info(f"测试完成！候选 {len(sendable)} 篇，将推送前 {len(to_send)} 篇")

    logger.info("程序运行完毕")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",      action="store_true")
    parser.add_argument("--send-test", action="store_true")
    args = parser.parse_args()
    run(test_mode=args.test, send_test=args.send_test)
