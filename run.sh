#!/usr/bin/env bash
# 手动启动（一般用桌面上的「中键启动器」图标即可）
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python app.py "$@"
