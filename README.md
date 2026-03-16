# PaperRadar - 部署指南

## 项目结构

```
paperradar/
├── config/
│   ├── config.yaml.example    ← 配置模板（上传到 GitHub）
│   └── config.yaml            ← 真实配置（本地填写，不上传）
├── src/
│   ├── fetcher.py             ← 论文抓取（arXiv + Semantic Scholar）
│   ├── analyzer.py            ← Kimi AI 分析
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
git clone https://github.com/你的用户名/paperradar.git ~/paperradar
```

### 第三步：填写配置文件

```bash
# 从模板复制一份配置文件
cp ~/paperradar/config/config.yaml.example ~/paperradar/config/config.yaml

# 编辑配置，填入 API Key 和邮箱信息
nano ~/paperradar/config/config.yaml
```

需要填写的三处内容：

```yaml
kimi:
  api_key: "sk-你的Kimi API Key"

email:
  sender: "你的QQ号@qq.com"
  password: "你的QQ邮箱授权码"    # 不是QQ密码，是邮箱授权码
  recipient: "收件人邮箱"

semantic_scholar:
  api_key: "你的Semantic Scholar API Key"   # 可选
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

# 手动运行一次完整流程（测试模式，不调用Kimi，不发邮件）
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

编辑 `config/config.yaml` 中的 `schedule_hour`，然后重新运行：

```bash
bash setup_server.sh
```

---

## 常见问题

**Q: 邮件没有收到？**
- 检查垃圾邮件文件夹
- 运行 `python main.py --send-test` 验证SMTP配置
- 查看日志文件确认是否有报错

**Q: Kimi API 报错？**
- 确认 API Key 是否正确
- 检查账户余额是否充足
- Kimi 免费层限制约3次/分钟，脚本已自动处理重试

**Q: 如何添加新的关键词？**
- 编辑 `config/config.yaml` 中的 `keywords` 列表，直接添加即可

**Q: 更新代码后如何生效？**

```bash
cd ~/paperradar
git pull
bash setup_server.sh   # 重新安装依赖（如果 requirements.txt 有变化）
```
