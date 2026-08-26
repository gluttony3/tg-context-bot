"""
Telegram AI Summary Bot — Setup Wizard

Interactive CLI wizard for configuring and launching the bot.
Supports Ukrainian, English, and Russian interfaces.

Usage:
    python setup_wizard.py
    uv run setup_wizard.py
"""

import asyncio
import os
import re
import sys
from pathlib import Path

import questionary
import sqlite3
from dotenv import load_dotenv, set_key
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent
ENV_PATH = ROOT_DIR / ".env"
ENV_EXAMPLE_PATH = ROOT_DIR / ".env.example"
SESSION_DIR = ROOT_DIR / "sessions"
DB_PATH = ROOT_DIR / "data.db"

console = Console()

# ---------------------------------------------------------------------------
#  Multilingual strings
# ---------------------------------------------------------------------------

STRINGS = {
    "ua": {
        "title": "Telegram AI Summary Bot — Майстер налаштування",
        "lang_prompt": "Оберіть мову інтерфейсу:",
        "welcome": "Ласкаво просимо! Цей майстер допоможе налаштувати бота за кілька кроків.",
        "step1_title": "Крок 1/4 — API ключі Telegram",
        "api_id_prompt": "Введіть API_ID (отримати: https://my.telegram.org/apps):",
        "api_hash_prompt": "Введіть API_HASH:",
        "step2_title": "Крок 2/4 — API ключ Gemini",
        "gemini_prompt": "Введіть GEMINI_API_KEY (отримати: https://aistudio.google.com/apikey):",
        "step3_title": "Крок 3/4 — Авторизація Telegram",
        "auth_info": "Зараз бот попросить номер телефону та код підтвердження для входу у ваш акаунт.",
        "phone_prompt": "Введіть номер телефону (наприклад +380...):",
        "code_prompt": "Введіть код з SMS:",
        "password_prompt": "Введіть пароль 2FA (якщо увімкнений):",
        "auth_ok": "Авторизація успішна!",
        "auth_fail": "Помилка авторизації:",
        "me_id_saved": "ME_ID={me_id} збережено у .env",
        "chat_id_prompt": "Введіть ID цільової групи (негативне число, наприклад -1001234567890):",
        "chat_id_hint": "Підказка: перешліть повідомлення з групи боту @userinfobot або використовуйте /id після запуску.",
        "step4_title": "Крок 4/4 — Запуск",
        "config_saved": "Конфігурацію збережено у .env",
        "launch_prompt": "Запустити бота зараз?",
        "launch_yes": "Так, запустити",
        "launch_no": "Ні, пізніше",
        "launching": "Запуск бота...",
        "goodbye": "Налаштування завершено! Запустіть бота командою:\n  uv run bot.py",
        "invalid_input": "Невірний ввід, спробуйте ще раз.",
        "env_created": "Файл .env створено з .env.example",
        "env_exists": "Файл .env вже існує — пропускаємо створення.",
        "db_initialized": "Базу даних ініціалізовано.",
        "press_enter": "Натисніть Enter для продовження...",
        "error": "Помилка:",
    },
    "en": {
        "title": "Telegram AI Summary Bot — Setup Wizard",
        "lang_prompt": "Choose interface language:",
        "welcome": "Welcome! This wizard will help you set up the bot in a few steps.",
        "step1_title": "Step 1/4 — Telegram API Keys",
        "api_id_prompt": "Enter API_ID (get it at: https://my.telegram.org/apps):",
        "api_hash_prompt": "Enter API_HASH:",
        "step2_title": "Step 2/4 — Gemini API Key",
        "gemini_prompt": "Enter GEMINI_API_KEY (get it at: https://aistudio.google.com/apikey):",
        "step3_title": "Step 3/4 — Telegram Authorization",
        "auth_info": "The bot will now ask for your phone number and confirmation code to log into your account.",
        "phone_prompt": "Enter phone number (e.g. +1...):",
        "code_prompt": "Enter the SMS code:",
        "password_prompt": "Enter 2FA password (if enabled):",
        "auth_ok": "Authorization successful!",
        "auth_fail": "Authorization error:",
        "me_id_saved": "ME_ID={me_id} saved to .env",
        "chat_id_prompt": "Enter target group ID (negative number, e.g. -1001234567890):",
        "chat_id_hint": "Hint: forward a message from the group to @userinfobot or use /id after launch.",
        "step4_title": "Step 4/4 — Launch",
        "config_saved": "Configuration saved to .env",
        "launch_prompt": "Launch the bot now?",
        "launch_yes": "Yes, launch",
        "launch_no": "No, later",
        "launching": "Launching bot...",
        "goodbye": "Setup complete! Launch the bot with:\n  uv run bot.py",
        "invalid_input": "Invalid input, try again.",
        "env_created": "Created .env from .env.example",
        "env_exists": ".env already exists — skipping creation.",
        "db_initialized": "Database initialized.",
        "press_enter": "Press Enter to continue...",
        "error": "Error:",
    },
    "ru": {
        "title": "Telegram AI Summary Bot — Мастер настройки",
        "lang_prompt": "Выберите язык интерфейса:",
        "welcome": "Добро пожаловать! Этот мастер поможет настроить бота за несколько шагов.",
        "step1_title": "Шаг 1/4 — API ключи Telegram",
        "api_id_prompt": "Введите API_ID (получить: https://my.telegram.org/apps):",
        "api_hash_prompt": "Введите API_HASH:",
        "step2_title": "Шаг 2/4 — API ключ Gemini",
        "gemini_prompt": "Введите GEMINI_API_KEY (получить: https://aistudio.google.com/apikey):",
        "step3_title": "Шаг 3/4 — Авторизация Telegram",
        "auth_info": "Сейчас бот попросит номер телефона и код подтверждения для входа в ваш аккаунт.",
        "phone_prompt": "Введите номер телефона (например +7...):",
        "code_prompt": "Введите код из SMS:",
        "password_prompt": "Введите пароль 2FA (если включён):",
        "auth_ok": "Авторизация успешна!",
        "auth_fail": "Ошибка авторизации:",
        "me_id_saved": "ME_ID={me_id} сохранён в .env",
        "chat_id_prompt": "Введите ID целевой группы (отрицательное число, например -1001234567890):",
        "chat_id_hint": "Подсказка: перешлите сообщение из группы боту @userinfobot или используйте /id после запуска.",
        "step4_title": "Шаг 4/4 — Запуск",
        "config_saved": "Конфигурация сохранена в .env",
        "launch_prompt": "Запустить бота сейчас?",
        "launch_yes": "Да, запустить",
        "launch_no": "Нет, позже",
        "launching": "Запуск бота...",
        "goodbye": "Настройка завершена! Запустите бота командой:\n  uv run bot.py",
        "invalid_input": "Неверный ввод, попробуйте ещё раз.",
        "env_created": "Файл .env создан из .env.example",
        "env_exists": "Файл .env уже существует — пропускаем создание.",
        "db_initialized": "База данных инициализирована.",
        "press_enter": "Нажмите Enter для продолжения...",
        "error": "Ошибка:",
    },
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    """Get translated string with optional formatting."""
    s = STRINGS.get(lang, STRINGS["en"]).get(key, key)
    return s.format(**kwargs) if kwargs else s


# ---------------------------------------------------------------------------
#  Language selection
# ---------------------------------------------------------------------------


def choose_language() -> str:
    console.print(
        Panel(
            Text("Telegram AI Summary Bot", style="bold cyan", justify="center"),
            title="Setup Wizard",
            border_style="cyan",
        )
    )
    choice = questionary.select(
        "Choose language / Оберіть мову / Выберите язык:",
        choices=[
            questionary.Choice("🇺🇦 Українська", value="ua"),
            questionary.Choice("🇬🇧 English", value="en"),
            questionary.Choice("🇷🇺 Русский", value="ru"),
        ],
    ).ask()

    if choice is None:
        sys.exit(0)
    return choice


# ---------------------------------------------------------------------------
#  .env management
# ---------------------------------------------------------------------------


def ensure_env(lang: str) -> None:
    if ENV_PATH.exists():
        console.print(f"[yellow]{t('env_exists', lang)}[/yellow]")
        return

    if ENV_EXAMPLE_PATH.exists():
        ENV_EXAMPLE_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        console.print(f"[green]{t('env_created', lang)}[/green]")
    else:
        ENV_PATH.write_text(
            "API_ID=\nAPI_HASH=\nGEMINI_API_KEY=\nTARGET_CHAT_ID=\nME_ID=\n",
            encoding="utf-8",
        )
        console.print(f"[green]{t('env_created', lang)}[/green]")


def prompt_api_id(lang: str) -> str:
    while True:
        val = questionary.text(t("api_id_prompt", lang)).ask()
        if val is None:
            sys.exit(0)
        val = val.strip()
        if val.isdigit() and len(val) >= 5:
            return val
        console.print(f"[red]{t('invalid_input', lang)}[/red]")


def prompt_api_hash(lang: str) -> str:
    while True:
        val = questionary.text(t("api_hash_prompt", lang)).ask()
        if val is None:
            sys.exit(0)
        val = val.strip()
        if len(val) >= 10:
            return val
        console.print(f"[red]{t('invalid_input', lang)}[/red]")


def prompt_gemini_key(lang: str) -> str:
    while True:
        val = questionary.text(t("gemini_prompt", lang)).ask()
        if val is None:
            sys.exit(0)
        val = val.strip()
        if len(val) >= 10:
            return val
        console.print(f"[red]{t('invalid_input', lang)}[/red]")


def prompt_chat_id(lang: str) -> str:
    console.print(f"[dim]{t('chat_id_hint', lang)}[/dim]")
    while True:
        val = questionary.text(t("chat_id_prompt", lang)).ask()
        if val is None:
            sys.exit(0)
        val = val.strip()
        if re.match(r"^-\d{5,}$", val):
            return val
        console.print(f"[red]{t('invalid_input', lang)}[/red]")


def save_env_key(key: str, value: str) -> None:
    set_key(str(ENV_PATH), key, value)


# ---------------------------------------------------------------------------
#  Telethon authorization
# ---------------------------------------------------------------------------


async def authorize_telethon(lang: str) -> int:
    from telethon import TelegramClient

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_path = str(SESSION_DIR / "userbot_session")

    load_dotenv(ENV_PATH, override=True)
    api_id = int(os.getenv("API_ID", "0"))
    api_hash = os.getenv("API_HASH", "")

    client = TelegramClient(session_path, api_id, api_hash)

    console.print(f"\n[bold]{t('step3_title', lang)}[/bold]")
    console.print(f"[dim]{t('auth_info', lang)}[/dim]\n")

    try:
        await client.start()
        me = await client.get_me()
        console.print(f"\n[green]{t('auth_ok', lang)}[/green]")
        console.print(f"  ID:       {me.id}")
        console.print(f"  Name:     {me.first_name}")
        console.print(f"  Username: @{me.username or 'N/A'}\n")
    except Exception as exc:
        console.print(f"[red]{t('auth_fail', lang)} {exc}[/red]")
        await client.disconnect()
        sys.exit(1)

    await client.disconnect()
    return me.id


# ---------------------------------------------------------------------------
#  Database initialization
# ---------------------------------------------------------------------------


def init_db(lang: str) -> None:
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS messages (
                message_id   INTEGER,
                chat_id      INTEGER,
                topic_id     INTEGER,
                sender_id    INTEGER,
                sender_name  TEXT,
                text         TEXT,
                timestamp    INTEGER,
                PRIMARY KEY (chat_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_topic ON messages (topic_id);
            CREATE INDEX IF NOT EXISTS idx_messages_ts    ON messages (timestamp);

            CREATE TABLE IF NOT EXISTS embeddings (
                msg_id    INTEGER PRIMARY KEY,
                chat_id   INTEGER NOT NULL,
                embedding BLOB,
                FOREIGN KEY (chat_id, msg_id)
                    REFERENCES messages (chat_id, message_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_embeddings_chat ON embeddings (chat_id);
            """
        )
        conn.commit()
        console.print(f"[green]{t('db_initialized', lang)}[/green]")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
#  Bot launcher
# ---------------------------------------------------------------------------


def launch_bot() -> None:
    console.print(f"\n[cyan]{STRINGS['en']['launching']}[/cyan]\n")

    bot_path = ROOT_DIR / "bot.py"
    if not bot_path.exists():
        console.print(f"[red]bot.py not found at {bot_path}[/red]")
        return

    os.execv(
        sys.executable,
        [sys.executable, str(bot_path)],
    )


# ---------------------------------------------------------------------------
#  Main wizard flow
# ---------------------------------------------------------------------------


def main() -> None:
    lang = choose_language()

    console.print(f"\n[bold green]{t('title', lang)}[/bold green]")
    console.print(f"{t('welcome', lang)}\n")

    # --- Step 1: Telegram API ---
    console.print(f"[bold]{t('step1_title', lang)}[/bold]")
    ensure_env(lang)

    load_dotenv(ENV_PATH, override=True)
    existing_api_id = os.getenv("API_ID", "").strip()

    if existing_api_id:
        console.print(f"[dim]API_ID = {existing_api_id}[/dim]")
        use_existing = questionary.confirm("Use existing API_ID?", default=True).ask()
        if use_existing is None:
            sys.exit(0)
        if not use_existing:
            api_id = prompt_api_id(lang)
            save_env_key("API_ID", api_id)
    else:
        api_id = prompt_api_id(lang)
        save_env_key("API_ID", api_id)

    load_dotenv(ENV_PATH, override=True)
    existing_hash = os.getenv("API_HASH", "").strip()

    if existing_hash:
        console.print(f"[dim]API_HASH = {existing_hash[:6]}...[/dim]")
        use_existing = questionary.confirm("Use existing API_HASH?", default=True).ask()
        if use_existing is None:
            sys.exit(0)
        if not use_existing:
            api_hash = prompt_api_hash(lang)
            save_env_key("API_HASH", api_hash)
    else:
        api_hash = prompt_api_hash(lang)
        save_env_key("API_HASH", api_hash)

    # --- Step 2: Gemini API ---
    console.print(f"\n[bold]{t('step2_title', lang)}[/bold]")
    load_dotenv(ENV_PATH, override=True)
    existing_gemini = os.getenv("GEMINI_API_KEY", "").strip()

    if existing_gemini:
        console.print(f"[dim]GEMINI_API_KEY = {existing_gemini[:8]}...[/dim]")
        use_existing = questionary.confirm("Use existing GEMINI_API_KEY?", default=True).ask()
        if use_existing is None:
            sys.exit(0)
        if not use_existing:
            gemini_key = prompt_gemini_key(lang)
            save_env_key("GEMINI_API_KEY", gemini_key)
    else:
        gemini_key = prompt_gemini_key(lang)
        save_env_key("GEMINI_API_KEY", gemini_key)

    # --- Step 3: Telegram Auth ---
    me_id = asyncio.run(authorize_telethon(lang))
    save_env_key("ME_ID", str(me_id))
    console.print(f"[green]{t('me_id_saved', lang, me_id=me_id)}[/green]\n")

    # --- Step 3b: Target Chat ID ---
    load_dotenv(ENV_PATH, override=True)
    existing_chat = os.getenv("TARGET_CHAT_ID", "").strip()

    if existing_chat:
        console.print(f"[dim]TARGET_CHAT_ID = {existing_chat}[/dim]")
        use_existing = questionary.confirm("Use existing TARGET_CHAT_ID?", default=True).ask()
        if use_existing is None:
            sys.exit(0)
        if not use_existing:
            chat_id = prompt_chat_id(lang)
            save_env_key("TARGET_CHAT_ID", chat_id)
    else:
        chat_id = prompt_chat_id(lang)
        save_env_key("TARGET_CHAT_ID", chat_id)

    # --- Step 4: DB init + Launch ---
    console.print(f"\n[bold]{t('step4_title', lang)}[/bold]")
    console.print(f"[green]{t('config_saved', lang)}[/green]")
    init_db(lang)

    launch = questionary.select(
        t("launch_prompt", lang),
        choices=[
            questionary.Choice(t("launch_yes", lang), value="yes"),
            questionary.Choice(t("launch_no", lang), value="no"),
        ],
    ).ask()

    if launch is None or launch == "no":
        console.print(f"\n[bold green]{t('goodbye', lang)}[/bold green]")
        sys.exit(0)

    launch_bot()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(0)
