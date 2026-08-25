# Telegram AI Summary Bot

A Telegram userbot that caches messages from a supergroup with forum topics into SQLite and provides AI summaries, RAG-based Q&A, and mention search via Gemini AI.

## Commands

All commands are sent **from Saved Messages**:

| Command | Description |
|---------|-------------|
| `/id` | Get the chat ID of a forwarded group |
| `/summary` | Summary for the last 48h (entire group) |
| `/summary 123` | Summary for the last 48h in a specific topic |
| `/mentions John` | Search user mentions in the database |
| `/ask question` | Q&A over group content (RAG) |

---

## Getting API Keys

### 1. Telegram API_ID and API_HASH

1. Go to [my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Click **API development tools**
4. Fill in the form (App title, Short name — anything)
5. Copy **App api_id** and **App api_hash**

### 2. Google Gemini API_KEY

1. Go to [aistudio.google.com](https://aistudio.google.com/apikey)
2. Sign in with a Google account
3. Click **Create API Key**
4. Copy the generated key

### 3. TARGET_CHAT_ID

1. Start the bot (instructions below)
2. Forward any message from the target group to **Saved Messages**
3. Send `/id`
4. The bot will reply with the group ID (a negative number, e.g. `-1001234567890`)
5. Put this ID into the `.env` file in the `TARGET_CHAT_ID` field
6. Restart the bot

---

## Setup

### Step 1 — Clone the project

```bash
git clone <repository-url>
cd telegram-ai-summary
```

### Step 2 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```
API_ID=12345678
API_HASH=abcdef1234567890abcdef
GEMINI_API_KEY=AIzaSy...
TARGET_CHAT_ID=-1001234567890
```

### Step 3 — Run

**Windows:**

```
start.bat
```

**Linux / macOS:**

```bash
chmod +x start.sh
./start.sh
```

**Termux (Android):**

```bash
chmod +x start.sh
./start.sh
```

On first launch Telethon will ask for your phone number and login code — this is normal.

---

## Dependencies

- Python 3.10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — installed automatically by `start.sh`

All Python packages are installed via `uv sync` (see `pyproject.toml`).

---

## How It Works

1. **Caching**: on startup the bot fetches new messages from the group (if DB is empty — last 100)
2. **Embeddings**: a background task indexes messages via `gemini-embedding-001` and stores them in SQLite
3. **Commands**: `/ask` performs RAG search over embeddings and sends context to Gemini; `/summary` summarizes raw texts
4. **Cleanup**: messages older than 7 days are automatically deleted once per day
