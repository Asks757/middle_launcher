#!/usr/bin/env bash
# 中键启动器 —— Linux 安装脚本
# 用法：bash install.sh
set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR" || exit 1

say()  { printf "\033[36m▸ %s\033[0m\n" "$*"; }
warn() { printf "\033[33m! %s\033[0m\n" "$*"; }
die()  { printf "\033[31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 1. 找 Python
pick_python() {
    local c
    for c in python3.12 python3.11 python3.10 python3.9 /usr/local/bin/python3 python3; do
        command -v "$c" >/dev/null 2>&1 || continue
        case "$c" in /*) [ -x "$c" ] || continue ;; esac
        if "$c" -c 'import sys,venv,ensurepip; sys.exit(0 if sys.version_info>=(3,9) else 1)' 2>/dev/null; then
            echo "$c"; return 0
        fi
    done
    return 1
}

if [ -x .venv/bin/python ] && .venv/bin/python -c "import PySide6, pynput" 2>/dev/null; then
    say "已存在可用的运行环境，跳过依赖安装"
else
    PY="$(pick_python)" || die "找不到 Python ≥ 3.9（需要自带 venv/ensurepip）。Debian/Ubuntu: sudo apt install python3 python3-venv"
    say "使用 Python: $($PY -V 2>&1) ($PY)"
    [ -d .venv ] || "$PY" -m venv .venv || die "创建虚拟环境失败"
    say "安装依赖（PySide6 约 100MB，请稍候）…"
    .venv/bin/python -m pip install --upgrade pip -q
    .venv/bin/python -m pip install -r requirements.txt -q \
        || .venv/bin/python -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple \
        || die "依赖安装失败，请检查网络后重试"
fi

# ---------------------------------------------------------------- 2. 图标
if [ ! -f assets/icon.png ]; then
    say "生成图标…"
    QT_QPA_PLATFORM=offscreen .venv/bin/python tools/make_assets.py >/dev/null 2>&1 || warn "图标生成失败，不影响使用"
fi

# ---------------------------------------------------------------- 3. 自检
say "自检 Qt 运行环境…"
if ! QT_QPA_PLATFORM=offscreen .venv/bin/python -c "from PySide6.QtWidgets import QApplication; QApplication([])" >/dev/null 2>&1; then
    warn "Qt 无法启动。若提示 libxcb-util.so.1 缺失，可执行：sudo apt install libxcb-util1"
    warn "（本目录 libs/ 已内置该库，若仍失败请把上面的报错发给开发者）"
else
    say "自检通过"
fi

# ---------------------------------------------------------------- 4. 桌面图标
PYBIN="$APP_DIR/.venv/bin/python"
APPPY="$APP_DIR/app.py"
ICON="$APP_DIR/assets/icon.png"

# make_desktop_file <路径> <名称> <中文说明> <英文说明> [参数...]
make_desktop_file() {
    local path="$1" name="$2" cn="$3" en="$4"; shift 4
    local extra="$*"
    cat > "$path" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$name
Name[en]=$name
Comment=$cn
Comment[en]=$en
Exec="$PYBIN" "$APPPY"${extra:+ $extra}
Path=$APP_DIR
Icon=$ICON
Terminal=false
Categories=Utility;Accessories;
StartupNotify=false
StartupWMClass=middle_launcher
EOF
    chmod +x "$path"
}

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[ -n "${DESKTOP_DIR:-}" ] && [ -d "$DESKTOP_DIR" ] || DESKTOP_DIR="$HOME/Desktop"
[ -d "$DESKTOP_DIR" ] || DESKTOP_DIR="$HOME/桌面"

if [ -d "$DESKTOP_DIR" ]; then
    make_desktop_file "$DESKTOP_DIR/中键启动器.desktop" "中键启动器" \
        "按鼠标中键唤出环形启动菜单" "Radial launcher on middle mouse button"
    make_desktop_file "$DESKTOP_DIR/中键启动器-设置.desktop" "中键启动器 设置" \
        "可视化配置启动项与外观" "Configure items and appearance" --settings
    gio set "$DESKTOP_DIR/中键启动器.desktop" metadata::trusted true 2>/dev/null || true
    gio set "$DESKTOP_DIR/中键启动器-设置.desktop" metadata::trusted true 2>/dev/null || true
    say "桌面图标已创建：中键启动器 / 中键启动器-设置"
else
    warn "没找到桌面目录，跳过桌面图标"
fi

# 应用菜单里也放一份
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
make_desktop_file "$APPS_DIR/middle_launcher.desktop" "中键启动器" \
    "按鼠标中键唤出环形启动菜单" "Radial launcher on middle mouse button"
make_desktop_file "$APPS_DIR/middle_launcher-settings.desktop" "中键启动器 设置" \
    "可视化配置启动项与外观" "Configure items and appearance" --settings
say "应用菜单已注册：middle_launcher / middle_launcher-settings"

# ---------------------------------------------------------------- 5. 开机自启
"$PYBIN" "$APPPY" --autostart-on >/dev/null 2>&1 \
    && say "已加入开机自启（托盘菜单里可随时取消）" \
    || warn "开机自启设置失败，可从托盘菜单手动开启"

# ---------------------------------------------------------------- 6. 启动
if pgrep -f "$APPPY" >/dev/null 2>&1; then
    say "程序已在运行，正在重新加载配置…"
    "$PYBIN" "$APPPY" --reload >/dev/null 2>&1 || true
else
    say "启动程序…"
    setsid nohup "$PYBIN" "$APPPY" >/dev/null 2>&1 < /dev/null &
    sleep 1
fi

cat <<EOF

完成！现在可以：
  · 按住鼠标中键 0.3 秒 → 弹出环形菜单，朝目标方向松开即打开
  · Ctrl+Alt+Space → 同样弹出菜单（可点击选择）
  · 托盘图标 → 打开菜单 / 设置… / 开机自启 / 退出
  · 桌面「中键启动器-设置」图标 → 可视化调整启动项、外观、触发方式

配置文件：$APP_DIR/config.json
日志文件：$APP_DIR/launcher.log

EOF
