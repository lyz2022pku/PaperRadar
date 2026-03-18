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

# 步骤1：检查 Python3 版本（需要 3.7+）
echo ""
echo "▶ 步骤1/4: 检查并安装 Python3..."

# 优先选用较新版本
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3.9 python3.8 python3.7 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(sys.version_info[:2])")
        if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "  ❌ 未找到 Python 3.7+，正在尝试安装 Python3.10..."
    sudo apt-get update -qq
    sudo apt-get install -y software-properties-common
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update -qq
    sudo apt-get install -y python3.10 python3.10-venv python3.10-distutils
    PYTHON_BIN="python3.10"
fi

echo "  ✅ 使用 Python: $PYTHON_BIN ($($PYTHON_BIN --version))"

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
    $PYTHON_BIN -m venv venv
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

# 从 config.yaml 读取时间和时区配置，并转换为 UTC 时间写入 cron
SCHEDULE=$(source "$INSTALL_DIR/venv/bin/activate" && python3 - <<'EOF'
import yaml, sys
from datetime import datetime, timezone, timedelta
try:
    with open("config/config.yaml") as f:
        c = yaml.safe_load(f)
    s = c.get("settings", {})
    tz_name = s.get("timezone", "UTC")
    hour    = int(s.get("schedule_hour", 8))
    minute  = int(s.get("schedule_minute", 0))

    # 将本地时间转换为 UTC（不依赖 pytz/zoneinfo，使用 Python 标准库）
    try:
        from zoneinfo import ZoneInfo          # Python 3.9+
        tz = ZoneInfo(tz_name)
    except ImportError:
        import zoneinfo                        # fallback: same module different path
        tz = zoneinfo.ZoneInfo(tz_name)

    local_dt = datetime(2024, 1, 15, hour, minute, tzinfo=tz)
    utc_dt   = local_dt.astimezone(timezone.utc)
    print(tz_name)
    print(hour)
    print(minute)
    print(utc_dt.hour)
    print(utc_dt.minute)
except Exception as e:
    print("UTC"); print(8); print(0); print(8); print(0)
EOF
)

TIMEZONE=$(echo "$SCHEDULE"  | sed -n '1p')
HOUR=$(echo "$SCHEDULE"      | sed -n '2p')
MINUTE=$(echo "$SCHEDULE"    | sed -n '3p')
UTC_HOUR=$(echo "$SCHEDULE"  | sed -n '4p')
UTC_MINUTE=$(echo "$SCHEDULE"| sed -n '5p')

mkdir -p "$INSTALL_DIR/logs"
# 使用 UTC 时间写入 cron（避免 CRON_TZ 在部分系统上不生效的问题）
CRON_JOB="$UTC_MINUTE $UTC_HOUR * * * mkdir -p $INSTALL_DIR/logs && cd $INSTALL_DIR && TZ=$TIMEZONE $INSTALL_DIR/venv/bin/python main.py >> $INSTALL_DIR/logs/cron.log 2>&1"
CRONTAB_TMP=$(mktemp)

# 移除旧的 paperradar 定时任务（如有）
crontab -l 2>/dev/null | grep -v "paperradar" > "$CRONTAB_TMP" || true

# 写入定时任务（用 UTC 时间，不依赖 CRON_TZ）
echo "# paperradar"  >> "$CRONTAB_TMP"
echo "$CRON_JOB"     >> "$CRONTAB_TMP"
crontab "$CRONTAB_TMP"
rm "$CRONTAB_TMP"

echo "  ✅ 定时任务已设置：每天 ${HOUR}:$(printf '%02d' $MINUTE)（$TIMEZONE / UTC ${UTC_HOUR}:$(printf '%02d' $UTC_MINUTE)）运行"

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
echo "  对应 UTC 时间：${UTC_HOUR}:$(printf '%02d' $UTC_MINUTE)"
echo ""
