#!/bin/bash
# Telegram AI Summary Bot — запуск

set -e

cd "$(dirname "$0")"

# Установка uv если отсутствует
if ! command -v uv &>/dev/null; then
    echo "[*] Устанавливаю uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Синхронизация зависимостей
echo "[*] uv sync..."
uv sync

# Запуск бота
echo "[*] Запуск bot.py..."

# tmux, если есть
if command -v tmux &>/dev/null; then
    tmux has-session -t tgbot 2>/dev/null && tmux kill-session -t tgbot
    tmux new-session -d -s tgbot "uv run bot.py"
    echo "[+] Бот запущен в tmux-сессии 'tgbot'"
    echo "    Подключиться:  tmux attach -t tgbot"
    echo "    Отключиться:   Ctrl+B, затем D"
else
    nohup uv run bot.py > bot.log 2>&1 &
    echo "[+] Бот запущен в фоне (PID $!)"
    echo "    Логи: tail -f bot.log"
fi
