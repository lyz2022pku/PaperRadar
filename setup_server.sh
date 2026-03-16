#!/bin/bash
# ============================================================
#  一键部署脚本 - 在云服务器上运行
#  前提：已通过 git clone 将代码下载到 ~/paperradar/
#  用法: cd ~/paperradar && bash setup_server.sh
# ============================================================

set -e  # 任何命令失败则退出

echo "================================================"
echo "  PaperRadar - 服务器一键部署脚本"
echo "================================================"

INSTALL_DIR="$HOME/paperradar"

# 步骤1：安装 Python3 和 pip
echo ""
echo "▶ 步骤1/4: 检查并安装 Python3..."
if ! command -v python3 &>/dev/null; then
    echo "  Python3 未安装，正在安装..."
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-pip python3-venv
else
    PYTHON_VER=$(python3 --version)
    echo "  ✅ Python3 已安装: $PYTHON_VER"
fi

# 步骤2：检查配置文件
echo ""
echo "▶ 步骤2/4: 检查配置文件..."
if [ ! -f "$INSTALL_DIR/config/config.yaml" ]; then
    echo "  ⚠️  未找到 config/config.yaml，正在从模板复制..."
    cp "$INSTALL_DIR/config/config.yaml.example" "$INSTALL_DIR/config/config.yaml"
    echo "  ✅ 已复制模板到 config/config.yaml"
    echo ""
    echo "  ⚠️  请先填写配置文件再继续："
    echo "     nano $INSTALL_DIR/config/config.yaml"
    echo ""
    echo "  填写完成后，重新运行此脚本：bash setup_server.sh"
    exit 0
else
    echo "  ✅ 配置文件已存在"
fi

# 步骤3：创建虚拟环境并安装依赖
echo ""
echo "▶ 步骤3/4: 安装 Python 依赖..."
cd "$INSTALL_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  虚拟环境创建完成"
fi

source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  ✅ 依赖安装完成"

# 确保模块可导入
touch "$INSTALL_DIR/src/__init__.py"

# 步骤4：设置定时任务 (cron)
echo ""
echo "▶ 步骤4/4: 配置定时任务..."

# 从 config.yaml 读取时间和时区配置
SCHEDULE=$(source "$INSTALL_DIR/venv/bin/activate" && python3 - <<'EOF'
import yaml, sys
try:
    with open("config/config.yaml") as f:
        c = yaml.safe_load(f)
    s = c.get("settings", {})
    print(s.get("timezone", "UTC"))
    print(s.get("schedule_hour", 8))
    print(s.get("schedule_minute", 0))
except Exception as e:
    print("UTC"); print(8); print(0)
EOF
)

TIMEZONE=$(echo "$SCHEDULE" | sed -n '1p')
HOUR=$(echo "$SCHEDULE"     | sed -n '2p')
MINUTE=$(echo "$SCHEDULE"   | sed -n '3p')

CRON_JOB="$MINUTE $HOUR * * * cd $INSTALL_DIR && TZ=$TIMEZONE $INSTALL_DIR/venv/bin/python main.py >> $INSTALL_DIR/logs/cron.log 2>&1"
CRONTAB_TMP=$(mktemp)

# 移除旧的 paperradar 定时任务（如有）
crontab -l 2>/dev/null | grep -v "paperradar" > "$CRONTAB_TMP" || true

# 写入时区环境变量 + 定时任务
echo "# paperradar"                 >> "$CRONTAB_TMP"
echo "CRON_TZ=$TIMEZONE"            >> "$CRONTAB_TMP"
echo "$CRON_JOB"                    >> "$CRONTAB_TMP"
crontab "$CRONTAB_TMP"
rm "$CRONTAB_TMP"

echo "  ✅ 定时任务已设置：每天 ${HOUR}:$(printf '%02d' $MINUTE)（$TIMEZONE 时间）运行"

# 完成
echo ""
echo "================================================"
echo "  ✅ 部署完成！"
echo "================================================"
echo ""
echo "  接下来请验证配置："
echo ""
echo "  1. 发送测试邮件验证 SMTP 配置："
echo "     cd $INSTALL_DIR && source venv/bin/activate"
echo "     python main.py --send-test"
echo ""
echo "  2. 手动运行一次完整流程（测试模式）："
echo "     python main.py --test"
echo ""
echo "  之后程序会在每天 ${HOUR}:$(printf '%02d' $MINUTE)（$TIMEZONE 时间）自动运行 ✅"
echo ""
