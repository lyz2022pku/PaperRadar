# PaperRadar

PaperRadar 是一个全自动的每日学术论文推送系统，从 arXiv 和 Semantic Scholar 抓取论文，通过 LLM 三维评分后，将精选结果以 HTML 邮件形式每日推送到你的邮箱。

## 设计亮点

**1. 两级关键词体系**
核心关键词（core）直接映射研究主线，命中即高度相关；扩展关键词（broad）覆盖周边领域，用于期刊粗筛但不参与 arXiv 查询。这种分层设计在保持聚焦的同时，不错过有启发价值的边缘工作。

**2. 三维评分系统**
每篇论文从直接相关性（A）、创新性（B）、视野拓展性（C）三个维度独立评分（1–5分），避免单一指标下"相关但不创新"或"创新但不相关"的论文互相掩盖。

**3. 动态权重调整**
三个维度的合成权重随月份日期按正弦曲线平滑变化，每月自然形成"聚焦→开拓→聚焦"的推送节奏。既防止推送风格固化，又帮助科研人员在深耕主线与开阔视野之间保持平衡。

**4. 个性化研究背景配置**
在 `config.yaml` 中填写自己的研究背景描述，系统会将其注入 LLM 的 system prompt，使相关性和视野评分真正以你的研究视角为基准，而非泛化判断。无需修改任何代码。

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

需要填写/修改的关键内容：

**① 用户研究背景（影响 LLM 评分视角，建议认真填写）**
```yaml
user:
  name: "你的名字"          # 可留空
  profile: "your research background"
  # 例如 "a PhD student focusing on 3D IC integration and oxide semiconductor devices"
```

**② LLM API**
```yaml
llm:
  api_key: "sk-你的API Key"
  model: "your-model-name"    # 例如 gpt-4o、kimi-k2-0905-preview、deepseek-chat
  base_url: ""                # 留空使用 OpenAI 官方；Kimi 填 https://api.moonshot.cn/v1
```

**③ 关键词（直接决定抓什么论文、怎么打分，务必替换为自己的方向）**
```yaml
keywords:
  core:                       # 核心关键词：命中即高度相关，A 分可达 4-5
    - "your core keyword 1"
    - "your core keyword 2"
  broad:                      # 扩展关键词：覆盖周边领域，A 分上限 3 分
    - "your broad keyword 1"
    - "your broad keyword 2"
```

**④ 目标期刊/会议（Semantic Scholar 来源，替换为你关注的刊物）**
```yaml
semantic_scholar:
  api_key: ""                 # 可留空，但留空可能导致检索不到 IEEE 相关论文
                              # 建议免费申请：https://www.semanticscholar.org/product/api
  target_venues:
    - "Nature Electronics"
    - "IEEE Transactions on Electron Devices"
    - "IEDM"
    # ... 替换/补充为你关注的期刊或会议全名
```

**⑤ arXiv 订阅类别（替换为与你方向相关的分类）**
```yaml
arxiv:
  categories:
    - "cs.AR"     # 完整列表见 https://arxiv.org/category_taxonomy
    - "cs.ET"
```

**⑥ 邮件与时间**
```yaml
email:
  smtp_server: "smtp.qq.com"   # QQ:smtp.qq.com 465 | Gmail:smtp.gmail.com 587
  smtp_port: 465
  sender: "你的发件邮箱"
  password: "邮箱授权码/应用密码"
  recipient: "收件人邮箱"

settings:
  timezone: "Asia/Shanghai"
  schedule_hour: 8
  schedule_minute: 0
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
