# PaperRadar

PaperRadar 是一个全自动的每日学术论文推送系统，从 arXiv 和 Semantic Scholar 抓取论文，通过 LLM 三维评分后，将精选结果以 HTML 邮件形式每日推送到你的邮箱。

## 设计亮点

**1. 两级关键词体系**
核心关键词（core）直接映射研究主线，命中即高度相关；扩展关键词（broad）覆盖周边领域，用于期刊粗筛但不参与 arXiv 查询。这种分层设计在保持聚焦的同时，不错过有启发价值的边缘工作。

**2. 三维评分系统**
每篇论文从直接相关性（A）、创新性（B）、视野拓展性（C）三个维度独立评分（1–5分），避免单一指标下"相关但不创新"或"创新但不相关"的论文互相掩盖。

**3. 动态权重调整**
三个维度的合成权重随月份日期按正弦曲线平滑变化，每月自然形成"聚焦→开拓→聚焦"的推送节奏。既防止推送风格固化，又帮助科研人员在深耕主线与开阔视野之间保持平衡。

---

# 部署指南

## 项目结构

```
paperradar/
├── config/
│   ├── config.yaml.example    ← 配置模板，含所有参数说明
│   └── config.yaml            ← 你的实际配置（从 example 复制后填写）
├── src/
│   ├── fetcher.py             ← 论文抓取（arXiv + Semantic Scholar）
│   ├── analyzer.py            ← LLM AI 分析
│   └── mailer.py              ← HTML 邮件发送
├── logs/                      ← 运行日志（自动生成）
├── output/                    ← 每日结果JSON（自动生成）
├── main.py                    ← 主程序
├── requirements.txt           ← Python依赖
└── setup_server.sh            ← 服务器一键部署脚本
```

---

## 部署到云服务器（Ubuntu）

### 第一步：SSH 登录服务器

```bash
ssh 你的用户名@你的服务器IP
```

### 第二步：克隆代码

```bash
git clone https://github.com/lyz2022pku/paperradar.git ~/paperradar
```

### 第三步：填写配置文件

```bash
# 从模板复制一份配置文件
cp ~/paperradar/config/config.yaml.example ~/paperradar/config/config.yaml

# 编辑配置，填入 API Key 和邮箱信息
nano ~/paperradar/config/config.yaml
```

需要填写的关键内容：

```yaml
# LLM API（兼容 OpenAI 格式，支持 OpenAI / Kimi / DeepSeek / 通义千问等）
llm:
  api_key: "sk-你的API Key"
  model: "your-model-name"    # 例如 gpt-4o、kimi-k2-0905-preview、deepseek-chat
  base_url: ""                # 留空使用 OpenAI 官方；Kimi 填 https://api.moonshot.cn/v1

# 邮件配置（支持 QQ / Gmail / 163 等 SMTP 服务）
# QQ 邮箱:  smtp.qq.com   端口 465  （使用邮箱授权码，非QQ密码）
# Gmail:    smtp.gmail.com 端口 587  （使用应用专用密码）
# 163 邮箱: smtp.163.com  端口 465
email:
  smtp_server: "smtp.qq.com"
  smtp_port: 465
  sender: "你的发件邮箱"
  password: "邮箱授权码/应用密码"
  recipient: "收件人邮箱"

# 时区与运行时间
settings:
  timezone: "Asia/Shanghai"    # 时区，北京时间填 Asia/Shanghai
  schedule_hour: 8             # 每天几点运行（本地时间，24小时制）
  schedule_minute: 0

# Semantic Scholar API Key（可留空，可能导致检索不到IEEE相关论文。该api免费申请，申请后足够个人使用）
# 申请地址：https://www.semanticscholar.org/product/api
semantic_scholar:
  api_key: ""
```

填写完成后，按 `Ctrl+O` 保存，`Ctrl+X` 退出。

### 第四步：运行一键部署脚本

```bash
cd ~/paperradar
bash setup_server.sh
```

脚本会自动：
- 安装 Python3（如果没有）
- 创建虚拟环境并安装依赖
- 设置每天早8点自动运行的定时任务

### 第五步：验证配置

```bash
cd ~/paperradar
source venv/bin/activate

# 发送测试邮件，验证 SMTP 配置
python main.py --send-test

# 手动运行一次完整流程（测试模式，不调用 LLM API，不发邮件）
python main.py --test
```

收到测试邮件则说明配置正确，部署完成。

---

## 日常维护

### 查看运行日志

```bash
# 查看今天的日志
cat ~/paperradar/logs/digest_$(date +%Y%m%d).log

# 查看定时任务日志
tail -50 ~/paperradar/logs/cron.log
```

### 修改关键词或订阅类别

```bash
nano ~/paperradar/config/config.yaml
```

修改后无需重启，下次运行自动生效。

### 手动触发（不等定时任务）

```bash
cd ~/paperradar
source venv/bin/activate
python main.py
```

### 修改推送时间

编辑 `config/config.yaml` 中的 `schedule_hour` 和 `schedule_minute`，然后重新运行：

```bash
bash setup_server.sh
```

---

## 常见问题

**Q: 邮件没有收到？**
- 检查垃圾邮件文件夹
- 运行 `python main.py --send-test` 验证SMTP配置
- 查看日志文件确认是否有报错

**Q: LLM API 报错？**
- 确认 `api_key` 和 `base_url` 是否填写正确
- 检查账户余额是否充足
- 遇到限流（429）时脚本会自动退避重试，无需手动处理

**Q: 如何添加新的关键词？**
- 编辑 `config/config.yaml` 中的 `keywords` 列表，直接添加即可

**Q: 更新代码后如何生效？**

```bash
cd ~/paperradar
git pull
bash setup_server.sh   # 重新安装依赖（如果 requirements.txt 有变化）
```
