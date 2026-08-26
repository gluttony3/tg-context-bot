# Telegram AI Summary Bot

Telegram userbot that caches messages from a supergroup with forum topics into SQLite and provides AI summaries, RAG-based Q&A, and mention search via Gemini AI.

## Quick Start (3 steps)

### 1. Clone and install

```bash
git clone <repository-url>
cd telegram-ai-summary
pip install uv && uv sync
```

### 2. Run the setup wizard

```bash
uv run setup_wizard.py
```

The wizard will:
- Ask for your preferred language (UA / EN / RU)
- Guide you through getting API keys from [my.telegram.org](https://my.telegram.org/apps) and [Google AI Studio](https://aistudio.google.com/apikey)
- Log you in to Telegram and auto-detect your user ID
- Configure `.env` and initialize the database

### 3. Launch the bot

```bash
uv run bot.py
```

Or let the wizard launch it for you at the end.

---

## Commands

All commands are sent **from Saved Messages**:

| Command | Description |
|---------|-------------|
| `/id` | Get chat ID of a forwarded message |
| `/summary` | Summary for the last 48h |
| `/summary 123` | Summary for a specific topic |
| `/ask <question>` | RAG search + AI answer |
| `/mentions <name>` | Search mentions in the database |

---

## Building a standalone executable

```bash
uv sync --extra build
uv run python build.py
```

Output: `dist/Telegram-AI-Summary-Setup.exe` (Windows) or `dist/Telegram-AI-Summary-Setup` (Linux)

---

## Project Structure

```
telegram-ai-summary/
├── setup_wizard.py   # Interactive setup wizard
├── bot.py            # Main bot logic
├── pyproject.toml    # Dependencies
├── .env.example      # Environment template
├── sessions/         # Telethon sessions (auto-created)
├── tests/            # Test scripts
└── data.db           # SQLite database (auto-created)
```
