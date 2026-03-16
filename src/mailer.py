"""
邮件发送模块
显示三维评分（A/B/C）、当日权重、加权综合得分
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
          background:#f5f6fa; margin:0; padding:20px; color:#333; }}
  .container {{ max-width:820px; margin:0 auto; }}
  .header {{ background:linear-gradient(135deg,#1a1a2e,#0f3460);
             color:white; padding:28px 30px; border-radius:12px 12px 0 0; }}
  .header h1 {{ margin:0; font-size:21px; }}
  .header .meta {{ margin-top:6px; opacity:.8; font-size:13px; }}
  .weight-bar {{ background:white; padding:14px 20px; border-bottom:1px solid #eee;
                 display:flex; align-items:center; gap:18px; flex-wrap:wrap; }}
  .weight-bar .label {{ font-size:12px; color:#666; margin-right:4px; }}
  .weight-pill {{ padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }}
  .pill-a {{ background:#e8f4fd; color:#1a6ca8; }}
  .pill-b {{ background:#fef3e8; color:#c0731a; }}
  .pill-c {{ background:#eafaf1; color:#1a7a4a; }}
  .stats {{ background:white; display:flex; border-bottom:1px solid #eee; }}
  .stat-item {{ flex:1; padding:14px 20px; text-align:center; border-right:1px solid #eee; }}
  .stat-item:last-child {{ border-right:none; }}
  .stat-num {{ font-size:22px; font-weight:bold; color:#0f3460; }}
  .stat-label {{ font-size:11px; color:#999; margin-top:3px; }}
  .section-title {{ padding:14px 4px 6px; font-size:12px; color:#999;
                    font-weight:600; border-bottom:1px solid #eee; margin-bottom:4px;
                    text-transform:uppercase; letter-spacing:.5px; }}
  .paper-card {{ background:white; margin:10px 0; border-radius:10px;
                 box-shadow:0 2px 8px rgba(0,0,0,.06); overflow:hidden;
                 border-left:4px solid #ccc; }}
  .paper-card.top    {{ border-left-color:#e74c3c; }}
  .paper-card.high   {{ border-left-color:#e67e22; }}
  .paper-card.normal {{ border-left-color:#3498db; }}
  .paper-header {{ padding:15px 20px 10px; }}
  .paper-title {{ font-size:14px; font-weight:bold; color:#1a1a2e; line-height:1.5;
                  text-decoration:none; }}
  .paper-title:hover {{ color:#0f3460; }}
  .paper-meta {{ margin-top:7px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
  .badge {{ display:inline-block; padding:2px 9px; border-radius:20px; font-size:11px; }}
  .badge-venue {{ background:#e8f4fd; color:#2980b9; }}
  .badge-arxiv {{ background:#fef9e7; color:#d68910; }}
  .badge-date  {{ background:#f0f0f0; color:#666; }}
  .scores {{ display:flex; gap:8px; margin-top:8px; flex-wrap:wrap; }}
  .score-chip {{ padding:3px 10px; border-radius:8px; font-size:12px; font-weight:500; }}
  .score-a {{ background:#e8f4fd; color:#1a6ca8; }}
  .score-b {{ background:#fef3e8; color:#c0731a; }}
  .score-c {{ background:#eafaf1; color:#1a7a4a; }}
  .score-total {{ background:#f0f0f0; color:#333; font-weight:700; }}
  .authors {{ font-size:11px; color:#aaa; margin-top:5px; line-height:1.6; }}
  .analysis {{ padding:0 20px 15px; }}
  .analysis-content {{ background:#f8f9fb; border-radius:8px; padding:13px;
                        font-size:12.5px; line-height:1.85; color:#444;
                        white-space:pre-line; }}
  .tag {{ font-weight:bold; color:#0f3460; }}
  .footer {{ text-align:center; padding:18px; color:#999; font-size:11px;
             background:white; border-radius:0 0 12px 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📡 PaperRadar · 每日论文精选</h1>
    <div class="meta">{date} &nbsp;·&nbsp; arXiv + Semantic Scholar &nbsp;·&nbsp; AI 分析</div>
  </div>
  <div class="weight-bar">
    <span class="label">今日推送权重：</span>
    <span class="weight-pill pill-a">🎯 直接相关性 {w_a}</span>
    <span class="weight-pill pill-b">💡 创新性 {w_b}</span>
    <span class="weight-pill pill-c">🌐 视野拓展 {w_c}</span>
    <span class="label" style="font-size:11px;">（随月份日期平滑变化）</span>
  </div>
  <div class="stats">
    <div class="stat-item">
      <div class="stat-num">{total}</div>
      <div class="stat-label">今日推送</div>
    </div>
    <div class="stat-item">
      <div class="stat-num">{arxiv_count}</div>
      <div class="stat-label">来自 arXiv</div>
    </div>
    <div class="stat-item">
      <div class="stat-num">{journal_count}</div>
      <div class="stat-label">来自期刊</div>
    </div>
    <div class="stat-item">
      <div class="stat-num">{top_count}</div>
      <div class="stat-label">综合得分 ≥ 4.0</div>
    </div>
  </div>
  {papers_html}
  <div class="footer">
    arXiv + Semantic Scholar 抓取 · LLM AI 分析 · 每日自动推送<br>
    权重曲线：直接相关性峰值月初/月末 · 创新性峰值第10天 · 视野拓展峰值第20天
  </div>
</div>
</body>
</html>"""

PAPER_TEMPLATE = """
<div class="paper-card {card_class}">
  <div class="paper-header">
    <a href="{url}" class="paper-title" target="_blank">{title}</a>
    <div class="paper-meta">
      <span class="badge {venue_cls}">{venue}</span>
      <span class="badge badge-date">{published}</span>
    </div>
    <div class="scores">
      <span class="score-chip score-a">🎯 相关 {score_a}/5</span>
      <span class="score-chip score-b">💡 创新 {score_b}/5</span>
      <span class="score-chip score-c">🌐 视野 {score_c}/5</span>
      <span class="score-chip score-total">综合 {weighted_score}</span>
    </div>
    <div class="authors">👥 {authors}</div>
  </div>
  <div class="analysis">
    <div class="analysis-content">{analysis}</div>
  </div>
</div>"""


def _render_card(paper: Dict) -> str:
    score = paper.get("weighted_score", 0)
    card_class = "top" if score >= 4.0 else ("high" if score >= 3.0 else "normal")
    is_arxiv = paper.get("source") == "arXiv"
    venue_cls = "badge-arxiv" if is_arxiv else "badge-venue"

    analysis = paper.get("analysis", "暂无分析")
    for tag in ["【研究背景】","【科学问题】","【主要方法】","【关键创新】",
                "【主要结论】","【A直接相关性】","【B创新性】","【C视野拓展性】"]:
        analysis = analysis.replace(tag, f'<span class="tag">{tag}</span>')

    authors = paper.get("authors", [])
    authors_str = "、".join(authors) if authors else "—"

    return PAPER_TEMPLATE.format(
        card_class=card_class,
        url=paper.get("url", "#"),
        title=paper.get("title", ""),
        venue=paper.get("venue", "")[:55],
        venue_cls=venue_cls,
        published=paper.get("published", ""),
        score_a=paper.get("score_a", "-"),
        score_b=paper.get("score_b", "-"),
        score_c=paper.get("score_c", "-"),
        weighted_score=f"{paper.get('weighted_score', 0):.2f}",
        authors=authors_str,
        analysis=analysis,
    )


def send_email(papers: List[Dict], email_cfg: Dict,
               w_a: float, w_b: float, w_c: float) -> bool:
    if not papers:
        logger.info("无论文，跳过发送")
        return True

    date_str = datetime.now().strftime("%Y年%m月%d日")
    top_count = sum(1 for p in papers if p.get("weighted_score", 0) >= 4.0)
    arxiv_count = sum(1 for p in papers if p.get("source") == "arXiv")

    top_papers   = [p for p in papers if p.get("weighted_score", 0) >= 4.0]
    other_papers = [p for p in papers if p.get("weighted_score", 0) < 4.0]

    papers_html = ""
    if top_papers:
        papers_html += '<div class="section-title">🔥 重点推荐（综合得分 ≥ 4.0）</div>'
        for p in top_papers:
            papers_html += _render_card(p)
    if other_papers:
        papers_html += '<div class="section-title">📑 更多论文</div>'
        for p in other_papers:
            papers_html += _render_card(p)

    html = HTML_TEMPLATE.format(
        date=date_str,
        w_a=f"{w_a:.0%}", w_b=f"{w_b:.0%}", w_c=f"{w_c:.0%}",
        total=len(papers),
        arxiv_count=arxiv_count,
        journal_count=len(papers) - arxiv_count,
        top_count=top_count,
        papers_html=papers_html,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{email_cfg['subject_prefix']} {date_str}（{len(papers)}篇）"
    msg["From"]    = email_cfg["sender"]
    msg["To"]      = email_cfg["recipient"]
    msg.attach(MIMEText(f"今日论文精选 {date_str}，共{len(papers)}篇，请用HTML邮件客户端查看。", "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(email_cfg["smtp_server"], email_cfg["smtp_port"]) as s:
            s.login(email_cfg["sender"], email_cfg["password"])
            s.sendmail(email_cfg["sender"], email_cfg["recipient"], msg.as_string())
        logger.info(f"邮件发送成功 → {email_cfg['recipient']}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False
