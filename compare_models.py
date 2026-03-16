"""
模型横向对比脚本
从 output/analysis_cache.json 或最新的 digest JSON 中取10篇论文，
分别用两个模型分析，结果保存到 output/model_compare.json
"""

import json, time, sys
from pathlib import Path
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from src.analyzer import build_system_prompt, USER_PROMPT_TEMPLATE, _parse_scores
import yaml

# ── 配置 ──────────────────────────────────────────────────────
MODELS = [
    "moonshot-v1-8k",
    "kimi-k2-0905-preview",
]
N_PAPERS = 10  # 每个模型分析多少篇

# ── 加载配置和论文 ─────────────────────────────────────────────
with open("config/config.yaml") as f:
    cfg = yaml.safe_load(f)

api_key  = cfg["llm"]["api_key"]
keywords = cfg["keywords"]
system_prompt = build_system_prompt(keywords)

# 从最新的digest JSON取论文（有标题+摘要）
digest_files = sorted(Path("output").glob("digest_*.json"), reverse=True)
if not digest_files:
    print("没有找到已抓取的论文，请先运行 python main.py --test")
    sys.exit(1)

with open(digest_files[0]) as f:
    papers = json.load(f)

papers = [p for p in papers if p.get("abstract")][:N_PAPERS]
print(f"使用 {digest_files[0].name} 中的 {len(papers)} 篇论文进行对比")

# ── 逐模型分析 ─────────────────────────────────────────────────
client = OpenAI(api_key=api_key, base_url="https://api.moonshot.cn/v1")
results = []

for paper in papers:
    entry = {
        "title":   paper["title"],
        "venue":   paper["venue"],
        "published": paper["published"],
        "models":  {}
    }
    for model in MODELS:
        print(f"\n[{model}] {paper['title'][:55]}...")
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": USER_PROMPT_TEMPLATE.format(
                        title=paper["title"],
                        venue=paper["venue"],
                        abstract=paper["abstract"][:1500],
                    )},
                ],
                max_tokens=500,
                temperature=0.2,
            )
            text = resp.choices[0].message.content.strip()
            score_a, score_b, score_c = _parse_scores(text)
            entry["models"][model] = {
                "analysis": text,
                "score_a":  score_a,
                "score_b":  score_b,
                "score_c":  score_c,
            }
            print(f"  A={score_a} B={score_b} C={score_c}")
        except Exception as e:
            print(f"  ERROR: {e}")
            entry["models"][model] = {"error": str(e)}
        time.sleep(3)
    results.append(entry)

# ── 保存结果 ───────────────────────────────────────────────────
out = Path("output/model_compare.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n对比结果已保存到 {out}")

# ── 打印评分摘要 ───────────────────────────────────────────────
print("\n" + "="*60)
print("评分对比摘要")
print("="*60)
for entry in results:
    print(f"\n{entry['title'][:55]}")
    for model in MODELS:
        m = entry["models"].get(model, {})
        if "error" in m:
            print(f"  {model:30s} ERROR")
        else:
            print(f"  {model:30s} A={m['score_a']} B={m['score_b']} C={m['score_c']}")
