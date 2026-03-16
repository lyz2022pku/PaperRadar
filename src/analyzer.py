"""
论文分析模块
- 使用 Kimi API 独立分析每篇论文
- 三维评分：直接相关性(A) / 创新性(B) / 视野拓展性(C)
- 支持分析缓存，避免重复消耗token
"""

import logging
import time
import re
import math
from datetime import datetime
from typing import Dict, List, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """你是Taylor的学术论文筛选助手。Taylor是半导体器件与集成电路方向的博士生。

核心关键词（命中即高度相关，A分可达4-5）：{core_keywords}
扩展关键词（仅作辅助参考，单独命中时A分上限3分）：{broad_keywords}

⚠️ 铁律：所有分析内容必须严格来自所提供的摘要原文，禁止推断、补全或引用摘要未提及的数据、结论和方法细节。
如摘要未提供足够信息，用"摘要未详述"代替，不得编造。

严格按以下格式输出，不添加任何额外内容：
【研究背景】（≤60字，仅基于摘要）
【科学问题】（≤50字，仅基于摘要）
【主要方法】（≤60字，仅基于摘要）
【关键创新】（≤80字，数字/指标须与摘要原文一致，无原文数字则不引用数字）
【主要结论】（≤60字，数字/指标须与摘要原文一致，无原文数字则不引用数字）
【A直接相关性】X分：一句话理由
【B创新性】X分：一句话理由
【C视野拓展性】X分：一句话理由

评分标准（1-5分整数）：

A 直接相关性（严格依据关键词等级判断）：
5分：论文主要贡献直接涉及核心关键词，且与Taylor的研究高度吻合
4分：论文研究内容涉及核心关键词，但非主要贡献，或方向略有偏差
3分：仅涉及扩展关键词，或核心关键词仅在背景/对比中被提及
2分：与半导体/集成电路领域相关，但不涉及任何关键词
1分：与Taylor研究领域几乎无关

B 创新性：
5分：提出全新方法/器件/架构，突破现有范式
4分：在已有方向上有显著改进或新颖结合
3分：渐进式改进，有一定新意
2分：工程优化为主，创新有限
1分：综述或重复已知工作

C 视野拓展性：
5分：来自相邻领域，方法/结论可直接启发Taylor的研究思路
4分：提供了新视角或跨领域联系，有间接参考价值
3分：拓宽了对领域整体进展的了解
2分：信息量有限，参考价值较小
1分：与Taylor研究背景差距过大，无参考意义

注意：同一篇论文A≥4且C≥4的情况极少，请仔细甄别。"""

USER_PROMPT_TEMPLATE = """标题：{title}
期刊/会议：{venue}
摘要（你的所有分析只能来自以下文字）：
{abstract}"""

def build_system_prompt(core_keywords: List[str], broad_keywords: List[str]) -> str:
    core_str = "、".join(core_keywords)
    broad_str = "、".join(broad_keywords)
    return SYSTEM_PROMPT_TEMPLATE.format(core_keywords=core_str, broad_keywords=broad_str)


def compute_weights(day: int) -> Tuple[float, float, float]:
    t = (day - 1) / 29.0
    w_a = 0.45 + 0.20 * math.cos(2 * math.pi * t)
    w_b = 0.30 + 0.15 * math.cos(2 * math.pi * t - 2 * math.pi / 3)
    w_c = 0.25 + 0.15 * math.cos(2 * math.pi * t - 4 * math.pi / 3)
    total = w_a + w_b + w_c
    return round(w_a / total, 3), round(w_b / total, 3), round(w_c / total, 3)


def compute_score(score_a: int, score_b: int, score_c: int,
                  w_a: float, w_b: float, w_c: float) -> float:
    return round(w_a * score_a + w_b * score_b + w_c * score_c, 3)


def _parse_scores(text: str) -> Tuple[int, int, int]:
    def extract(tag: str) -> int:
        m = re.search(rf'【{tag}】\s*(\d)', text)
        if m:
            return max(1, min(5, int(m.group(1))))
        return 3
    return extract("A直接相关性"), extract("B创新性"), extract("C视野拓展性")


def analyze_papers_with_kimi(papers: List[Dict],
                              api_key: str,
                              model: str,
                              core_keywords: List[str],
                              broad_keywords: List[str],
                              max_tokens: int = 500) -> List[Dict]:
    if not papers:
        return []

    client = OpenAI(api_key=api_key, base_url="https://api.moonshot.cn/v1")
    system_prompt = build_system_prompt(core_keywords, broad_keywords)
    analyzed = []
    total = len(papers)

    for i, paper in enumerate(papers):
        logger.info(f"Kimi分析 [{i+1}/{total}]: {paper['title'][:55]}...")
        user_prompt = USER_PROMPT_TEMPLATE.format(
            title=paper["title"],
            venue=paper["venue"],
            abstract=paper["abstract"][:1500],
        )

        max_retries = 6
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.2,
                )
                analysis_text = response.choices[0].message.content.strip()
                score_a, score_b, score_c = _parse_scores(analysis_text)

                paper.update({
                    "analysis":  analysis_text,
                    "score_a":   score_a,
                    "score_b":   score_b,
                    "score_c":   score_c,
                    "filtered":  (score_a <= 1 and score_b <= 1 and score_c <= 1),
                })
                analyzed.append(paper)
                time.sleep(1)
                break

            except Exception as e:
                is_rate_limit = "429" in str(e) or "overloaded" in str(e).lower() or "rate" in str(e).lower()
                if is_rate_limit and attempt < max_retries - 1:
                    wait = 10 * (2 ** attempt)  # 10, 20, 40, 80, 160s
                    logger.warning(f"限流，{wait}s 后重试 [{attempt+1}/{max_retries}]: {paper['title'][:45]}")
                    time.sleep(wait)
                else:
                    logger.error(f"分析失败: {paper['title'][:45]} | {e}")
                    time.sleep(5)
                    break

    logger.info(f"Kimi分析完成：{len(analyzed)}/{total} 篇")
    return analyzed
