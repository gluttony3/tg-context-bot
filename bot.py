"""
Telegram AI Summary Bot — кэширование сообщений из группы + AI-команды.

Запуск:  uv run bot.py
"""

import asyncio
import datetime as dt
import logging
import os
import struct
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import User

import sqlite3

from google import genai
from google.genai import types as genai_types

# ---------------------------------------------------------------------------
#  Конфигурация
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).with_name(".env"))

API_ID: int = int(os.getenv("API_ID", "0"))
API_HASH: str = os.getenv("API_HASH", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
_chat_id_raw: str = os.getenv("TARGET_CHAT_ID", "").strip()
TARGET_CHAT_ID: int = int(_chat_id_raw) if _chat_id_raw else 0

ME_ID: int | None = None
ME_USERNAME: str | None = None

DB_PATH: Path = Path(__file__).with_name("data").with_suffix(".db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SUMMARY_WINDOW_HOURS: int = 48
EMBEDDING_MODEL: str = "models/gemini-embedding-001"
GEMINI_MODEL: str = "gemini-3.6-flash"
SYSTEM_INSTRUCTION: str = (
    "Ты — локальный Telegram-бот-ассистент, у тебя есть доступ к локальной базе данных сообщений группы. "
    "Отвечай коротко, по делу и строго от первого лица. "
    "НЕ ПИШИ приветствия с вопросом о скидывании контекста (например, 'скинь мне сообщения'). Ты САМ выгружаешь их из БД. "
    "Если в предоставленных источниках нет ответа на вопрос, просто ответь: "
    "'В найденных сообщениях базы нет информации по этому поводу.' Без лишних рассуждений."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger("summary-bot")

# ---------------------------------------------------------------------------
#  Telethon — клиент
# ---------------------------------------------------------------------------

client = TelegramClient(
    "sessions/telethon_session",
    API_ID,
    API_HASH,
    connection_retries=None,
    retry_delay=2,
)

# ---------------------------------------------------------------------------
#  Gemini — клиент + хелпер
# ---------------------------------------------------------------------------

_gemini_client = genai.Client(api_key=GEMINI_API_KEY)


async def ask_gemini(contents, **kwargs) -> str:
    system = kwargs.pop("system_instruction", SYSTEM_INSTRUCTION)
    temp = kwargs.pop("temperature", 0.3)
    max_tok = kwargs.pop("max_output_tokens", 2048)
    response = await asyncio.to_thread(
        _gemini_client.models.generate_content,
        model=GEMINI_MODEL,
        contents=contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            temperature=temp,
            max_output_tokens=max_tok,
        ),
    )
    return response.text or "(пустой ответ от Gemini)"

# ---------------------------------------------------------------------------
#  SQLite — инициализация, запись, чтение, очистка
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _get_db()
    try:
        conn.executescript(
            """
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
        log.info("БД инициализирована: %s", DB_PATH)
    finally:
        conn.close()


def _date_to_utc_ts(date) -> int:
    if hasattr(date, "replace"):
        return int(date.replace(tzinfo=None).timestamp())
    if hasattr(date, "timestamp"):
        return int(date.timestamp())
    return int(date)


def save_message_to_db(
    *, msg_id, chat_id, topic_id, user_id, username, first_name, text, date,
    quiet: bool = False,
) -> None:
    timestamp = _date_to_utc_ts(date)
    sender_name = first_name or username or str(user_id)
    conn = _get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO messages"
            " (message_id,chat_id,topic_id,sender_id,sender_name,text,timestamp)"
            " VALUES (?,?,?,?,?,?,?)",
            (msg_id, chat_id, topic_id, user_id, sender_name, text, timestamp),
        )
        conn.commit()
        if not quiet:
            print(f"[DB] Saved: msg_id={msg_id} from={sender_name}", flush=True)
    except sqlite3.Error as exc:
        log.error("Ошибка записи в БД: %s", exc)
    finally:
        conn.close()


def fetch_messages_for_summary(chat_id, *, topic_id=None, hours=SUMMARY_WINDOW_HOURS):
    cutoff = int(dt.datetime.now(dt.timezone.utc).timestamp()) - hours * 3600
    conn = _get_db()
    try:
        if topic_id is not None:
            rows = conn.execute(
                "SELECT sender_name,text,timestamp,topic_id FROM messages "
                "WHERE chat_id=? AND topic_id=? AND timestamp>=? ORDER BY timestamp ASC",
                (chat_id, topic_id, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT sender_name,text,timestamp,topic_id FROM messages "
                "WHERE chat_id=? AND topic_id IS NOT NULL AND timestamp>=? "
                "ORDER BY timestamp ASC",
                (chat_id, cutoff),
            ).fetchall()
        return list(rows)
    except sqlite3.Error as exc:
        log.error("Ошибка чтения БД: %s", exc)
        return []
    finally:
        conn.close()


def fetch_mentions(chat_id: int, name: str) -> list[sqlite3.Row]:
    conn = _get_db()
    try:
        pattern = f"%{name}%"
        rows = conn.execute(
            "SELECT message_id,sender_name,text,timestamp,topic_id FROM messages "
            "WHERE chat_id=? AND (text LIKE ? OR sender_name LIKE ?) "
            "ORDER BY timestamp DESC LIMIT 50",
            (chat_id, pattern, pattern),
        ).fetchall()
        return list(rows)
    except sqlite3.Error as exc:
        log.error("Ошибка поиска упоминаний: %s", exc)
        return []
    finally:
        conn.close()


def get_topic_name(chat_id: int, topic_id: int) -> str:
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT text FROM messages WHERE chat_id=? AND message_id=?",
            (chat_id, topic_id),
        ).fetchone()
        if row and row["text"]:
            name = row["text"][:60]
            return name + ("…" if len(row["text"]) > 60 else "")
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return f"topic {topic_id}"


def cleanup_old_messages() -> int:
    conn = _get_db()
    try:
        cur = conn.execute(
            "DELETE FROM messages WHERE timestamp < "
            "CAST(strftime('%s', datetime('now', '-7 days')) AS INTEGER)"
        )
        conn.commit()
        deleted = cur.rowcount
        if deleted:
            log.info("Очищено %d старых сообщений", deleted)
        return deleted
    except sqlite3.Error as exc:
        log.error("Ошибка очистки БД: %s", exc)
        return 0
    finally:
        conn.close()

# ---------------------------------------------------------------------------
#  Embeddings — генерация, сохранение, поиск (RAG)
# ---------------------------------------------------------------------------


def _embedding_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _blob_to_embedding(blob: bytes) -> np.ndarray:
    n = len(blob) // 4
    return np.array(struct.unpack(f"<{n}f", blob), dtype=np.float32)


async def get_embedding(text: str, task_type: str = "retrieval_document") -> list[float]:
    if not text or not text.strip():
        return []
    try:
        response = await asyncio.to_thread(
            _gemini_client.models.embed_content,
            model=EMBEDDING_MODEL,
            contents=text,
            config=genai_types.EmbedContentConfig(task_type=task_type),
        )
        return list(response.embeddings[0].values)
    except Exception as exc:
        log.error("Ошибка get_embedding: %s", exc)
        return []


def save_embedding_to_db(*, msg_id: int, chat_id: int, embedding: list[float]) -> None:
    blob = _embedding_to_blob(embedding)
    conn = _get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO embeddings (msg_id,chat_id,embedding) VALUES (?,?,?)",
            (msg_id, chat_id, blob),
        )
        conn.commit()
    except sqlite3.Error as exc:
        log.error("Ошибка сохранения эмбеддинга: %s", exc)
    finally:
        conn.close()


def search_similar_messages(query_embedding: list[float], chat_id: int, limit: int = 10) -> list[dict]:
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT msg_id,embedding FROM embeddings WHERE chat_id=? AND embedding IS NOT NULL",
            (chat_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    q_vec = np.array(query_embedding, dtype=np.float32)
    q_norm = np.linalg.norm(q_vec)
    if q_norm == 0:
        return []

    scored: list[tuple[int, float]] = []
    for row in rows:
        e_vec = _blob_to_embedding(row["embedding"])
        e_norm = np.linalg.norm(e_vec)
        if e_norm == 0:
            continue
        cos_sim = float(np.dot(q_vec, e_vec) / (q_norm * e_norm))
        scored.append((row["msg_id"], cos_sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_ids = [m for m, _ in scored[:limit]]
    if not top_ids:
        return []

    placeholders = ",".join("?" * len(top_ids))
    conn = _get_db()
    try:
        msg_rows = conn.execute(
            f"SELECT message_id,sender_name,text,timestamp,topic_id "
            f"FROM messages WHERE chat_id=? AND message_id IN ({placeholders})",
            [chat_id, *top_ids],
        ).fetchall()
    finally:
        conn.close()

    msg_map = {r["message_id"]: r for r in msg_rows}
    return [
        {
            "message_id": r["message_id"],
            "sender_name": r["sender_name"],
            "text": r["text"],
            "timestamp": r["timestamp"],
            "topic_id": r["topic_id"],
            "score": cos,
        }
        for mid, cos in scored[:limit]
        if (r := msg_map.get(mid))
    ]

# ---------------------------------------------------------------------------
#  Фоновая индексация эмбеддингов
# ---------------------------------------------------------------------------


async def background_index_embeddings(tg_client, target_chat: int) -> None:
    print("[INDEX] Запуск фоновой индексации…", flush=True)
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT m.message_id,m.text FROM messages m "
            "LEFT JOIN embeddings e ON m.message_id=e.msg_id AND m.chat_id=e.chat_id "
            "WHERE m.chat_id=? AND e.msg_id IS NULL AND m.text!='' "
            "ORDER BY m.message_id ASC",
            (target_chat,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("[INDEX] Всё уже проиндексировано", flush=True)
        return

    print(f"[INDEX] {len(rows)} сообщений без эмбеддингов", flush=True)
    indexed = 0
    for row in rows:
        emb = await get_embedding(row["text"], task_type="retrieval_document")
        if emb:
            save_embedding_to_db(msg_id=row["message_id"], chat_id=target_chat, embedding=emb)
            indexed += 1
        await asyncio.sleep(0.5)

    print(f"[INDEX] Готово: {indexed}/{len(rows)}", flush=True)

# ---------------------------------------------------------------------------
#  Smart catch-up при старте
# ---------------------------------------------------------------------------


def get_max_msg_id(chat_id: int) -> int | None:
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT MAX(message_id) FROM messages WHERE chat_id=?", (chat_id,)
        ).fetchone()
        return row[0] if row and row[0] is not None else None
    finally:
        conn.close()


async def catchup_history(tg_client, target_chat: int) -> int:
    max_id = get_max_msg_id(target_chat)

    if max_id is not None:
        print(f"[CATCHUP] Догружаю новые (max_id={max_id})…", flush=True)
        saved = 0
        async for msg in tg_client.iter_messages(target_chat, min_id=max_id):
            _save_catchup_message(msg, target_chat)
            saved += 1
        print(f"[CATCHUP] Догружено {saved}", flush=True)
        return saved

    print("[CATCHUP] БД пуста, загружаю последние 100…", flush=True)
    saved = 0
    async for msg in tg_client.iter_messages(target_chat, limit=100):
        _save_catchup_message(msg, target_chat)
        saved += 1
    print(f"[CATCHUP] Загружено {saved}", flush=True)
    return saved


def _save_catchup_message(message, target_chat: int) -> None:
    text = (message.text or "").strip()
    if not text:
        return

    topic_id = None
    if message.reply_to:
        top_id = getattr(message.reply_to, "top_msg_id", None)
        if top_id is not None:
            topic_id = top_id

    from_name = username = ""
    user_id = getattr(message, "sender_id", 0) or 0

    save_message_to_db(
        msg_id=message.id, chat_id=target_chat, topic_id=topic_id,
        user_id=user_id, username=username, first_name=from_name,
        text=text, date=message.date, quiet=True,
    )

# ---------------------------------------------------------------------------
#  Фоновая очистка БД раз в 24 часа
# ---------------------------------------------------------------------------


async def periodic_cleanup() -> None:
    while True:
        await asyncio.sleep(86400)
        try:
            await asyncio.to_thread(cleanup_old_messages)
        except Exception as exc:
            log.error("Ошибка фоновой очистки: %s", exc)

# ---------------------------------------------------------------------------
#  Промпты
# ---------------------------------------------------------------------------


def build_summary_prompt(messages: list[sqlite3.Row], topic_id: int | None) -> str:
    lines: list[str] = []
    for row in messages:
        ts = dt.datetime.fromtimestamp(row["timestamp"], tz=dt.timezone.utc)
        tag = f"[topic {row['topic_id']}]" if row["topic_id"] is not None else ""
        lines.append(f"[{ts.strftime('%d.%m %H:%M')}] {tag} {row['sender_name']}: {row['text']}")

    scope = f"топика №{topic_id}" if topic_id is not None else "всех активных топиков"
    return (
        f"Ниже сообщения из {scope} за последние {SUMMARY_WINDOW_HOURS} часов.\n\n"
        "Составь краткое структурированное саммари на русском:\n"
        "1) Ключевые события / решения / новости.\n"
        "2) Важные нерешённые вопросы.\n"
        "3) Активные участники.\n"
        "Формат: Markdown. Объём — до 1500 символов.\n\n"
        "--- ЛОГ ---\n" + "\n".join(lines) + "\n--- КОНЕЦ ---"
    )

# ---------------------------------------------------------------------------
#  Flood-фильтр для сообщений из группы
# ---------------------------------------------------------------------------


def _is_flood(event, text: str, me_id: int) -> bool:
    if event.is_reply:
        return False
    if ME_USERNAME and f"@{ME_USERNAME}".lower() in text.lower():
        return False
    if str(me_id) in text:
        return False
    if event.message.mentions:
        for u in event.message.mentions:
            if hasattr(u, "id") and u.id == me_id:
                return False
    if not text.strip():
        return True
    if len(text.strip()) < 3:
        return True
    return False

# ---------------------------------------------------------------------------
#  Хэндлер: обработка входящих сообщений
# ---------------------------------------------------------------------------


@client.on(events.NewMessage)
async def handle_new_message(event) -> None:
    text = event.raw_text or ""
    chat_id = event.chat_id
    sender_id = event.sender_id

    # --- 1. Сохранение сообщений из целевой группы ---
    if chat_id == TARGET_CHAT_ID:
        try:
            topic_id: int | None = None
            if event.message.reply_to:
                top_id = getattr(event.message.reply_to, "top_msg_id", None)
                if top_id is not None:
                    topic_id = top_id

            if _is_flood(event, text, ME_ID or 0):
                return

            sender = await event.get_sender()
            from_name = username = ""
            if isinstance(sender, User):
                from_name = getattr(sender, "first_name", "") or ""
                username = getattr(sender, "username", "") or ""

            save_message_to_db(
                msg_id=event.id, chat_id=chat_id, topic_id=topic_id,
                user_id=sender_id or 0, username=username, first_name=from_name,
                text=text.strip(), date=event.date,
            )

            try:
                emb = await get_embedding(text.strip(), task_type="retrieval_document")
                if emb:
                    save_embedding_to_db(msg_id=event.id, chat_id=chat_id, embedding=emb)
            except Exception as exc:
                log.warning("Эмбеддинг не сгенерирован: %s", exc)
        except Exception as exc:
            log.exception("Ошибка обработки сообщения из группы: %s", exc)
        return

    # --- 2. Команды из Saved Messages ---
    is_self = chat_id == ME_ID if ME_ID else False
    if not is_self:
        return

    if not text.startswith("/"):
        await event.reply(
            "ℹ️ Available commands:\n"
            "• /summary — summary for the last 48h\n"
            "• /ask <question> — search the entire database\n"
            "• /mentions [name] — search mentions\n"
            "• /id — get chat ID (forward a message)"
        )
        return

    parts = text.split()
    cmd = parts[0].lower()
    log.info("Команда: %s (chat=%s)", cmd, chat_id)

    # --- /id ---
    if cmd == "/id":
        try:
            target_chat_id = chat_id
            target_chat_title = "Личные сообщения"
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                if reply_msg:
                    target_chat_id = reply_msg.chat_id
                    reply_chat = await reply_msg.get_chat()
                    target_chat_title = (
                        getattr(reply_chat, "title", None)
                        or getattr(reply_chat, "first_name", "Личные сообщения")
                    )
            await event.reply(
                f"**Chat ID:** `{target_chat_id}`\n**Название:** {target_chat_title}"
            )
        except Exception as exc:
            log.exception("Ошибка /id: %s", exc)
            await event.reply(f"❌ Ошибка: {exc}")

    # --- /summary ---
    elif cmd == "/summary":
        try:
            topic_id: int | None = None
            if len(parts) > 1:
                try:
                    topic_id = int(parts[1])
                except ValueError:
                    await event.reply("⚠️ Формат: /summary или /summary <topic_id>")
                    return

            conn_check = _get_db()
            try:
                total = conn_check.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            finally:
                conn_check.close()

            if total == 0:
                await event.reply("📭 В базе нет сообщений. Начните писать в группу.")
                return

            await event.reply("⏳ Собираю сообщения…")
            rows = fetch_messages_for_summary(TARGET_CHAT_ID, topic_id=topic_id)

            if not rows:
                desc = f"за последние {SUMMARY_WINDOW_HOURS}ч"
                if topic_id is not None:
                    desc += f" из топика {topic_id}"
                await event.reply(f"📭 Нет сообщений {desc}.")
                return

            summary = await generate_summary(rows, topic_id)
            for i in range(0, len(summary), 4000):
                await event.reply(summary[i : i + 4000])
            log.info("Саммари: topic=%s, msgs=%d", topic_id, len(rows))

        except Exception as exc:
            log.exception("Ошибка /summary: %s", exc)
            await event.reply(f"❌ Ошибка: {exc}")

    # --- /mentions ---
    elif cmd == "/mentions":
        try:
            if len(parts) < 2 or not parts[1].strip():
                await event.reply("⚠️ Использование: /mentions <имя или @username>")
                return

            query = parts[1].strip()
            rows = fetch_mentions(TARGET_CHAT_ID, query)
            if not rows:
                await event.reply(f"🔍 Упоминаний «{query}» не найдено.")
                return

            lines: list[str] = []
            for row in rows:
                ts = dt.datetime.fromtimestamp(row["timestamp"], tz=dt.timezone.utc)
                tag = f" [topic {row['topic_id']}]" if row["topic_id"] is not None else ""
                txt = row["text"][:120] + ("…" if len(row["text"]) > 120 else "")
                lines.append(f"• [{ts.strftime('%d.%m %H:%M')}]{tag} {row['sender_name']}: {txt}")

            result = f"🔍 Найдено {len(lines)} сообщений по «{query}»:\n\n" + "\n".join(lines)
            if len(result) > 4000:
                result = result[:4000] + "\n… (обрезано)"
            await event.reply(result)
            log.info("Mentions: query=%s, found=%d", query, len(rows))

        except Exception as exc:
            log.exception("Ошибка /mentions: %s", exc)
            await event.reply(f"❌ Ошибка: {exc}")

    # --- /ask ---
    elif cmd == "/ask":
        try:
            if len(parts) < 2 or not " ".join(parts[1:]).strip():
                await event.reply("⚠️ Использование: /ask <вопрос>")
                return

            query = " ".join(parts[1:]).strip()
            await event.reply(f"🔍 Ищу по запросу: «{query}»…")

            q_emb = await get_embedding(query, task_type="retrieval_query")
            if not q_emb:
                await event.reply("❌ Не удалось сгенерировать эмбеддинг.")
                return

            similar = search_similar_messages(q_emb, TARGET_CHAT_ID, limit=10)
            if not similar:
                await event.reply("📭 Релевантных сообщений не найдено.")
                return

            similar.sort(key=lambda m: m["timestamp"], reverse=True)

            ctx_lines: list[str] = []
            for m in similar:
                ts = dt.datetime.fromtimestamp(m["timestamp"], tz=dt.timezone.utc)
                tag = f" [topic {m['topic_id']}]" if m["topic_id"] is not None else ""
                ctx_lines.append(f"[{ts.strftime('%d.%m %H:%M')}] {m['sender_name']}: {m['text']}")
            context = "\n".join(ctx_lines)

            prompt = (
                "--- КОНТЕКСТ ИЗ ПЕРЕПИСКИ ---\n"
                f"{context}\n"
                "--- КОНЕЦ КОНТЕКСТА ---\n\n"
                f"Вопрос: {query}\n\n"
                "Ответь, опираясь на контекст. Если информации мало — подскажи логически. "
                "Формат: Markdown. До 1500 символов."
            )
            answer = await ask_gemini(prompt)

            src_lines = []
            for s in similar[:5]:
                ts = dt.datetime.fromtimestamp(s["timestamp"], tz=dt.timezone.utc)
                topic = get_topic_name(TARGET_CHAT_ID, s["topic_id"])
                txt = s["text"][:80] + ("…" if len(s["text"]) > 80 else "")
                src_lines.append(f"• {s['sender_name']} ({ts.strftime('%d.%m %H:%M')}) [{topic}]: {txt}")
            sources = "\n".join(src_lines)

            final = f"**Ответ:**\n{answer}\n\n---\n**Источники ({len(similar)}):**\n{sources}"
            for i in range(0, len(final), 4000):
                await event.reply(final[i : i + 4000])
            log.info("Ask: query=%s, found=%d", query, len(similar))

        except Exception as exc:
            log.exception("Ошибка /ask: %s", exc)
            await event.reply(f"❌ Ошибка: {exc}")

# ---------------------------------------------------------------------------
#  Точка входа
# ---------------------------------------------------------------------------


async def generate_summary(messages, topic_id):
    if not messages:
        return "Нет сообщений за выбранный период."
    return await ask_gemini(build_summary_prompt(messages, topic_id))


async def main() -> None:
    global ME_ID, ME_USERNAME

    missing: list[str] = []
    if not API_ID:
        missing.append("API_ID")
    if not API_HASH:
        missing.append("API_HASH")
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        missing.append("GEMINI_API_KEY")
    if not TARGET_CHAT_ID:
        missing.append("TARGET_CHAT_ID")
    if missing:
        log.error("Не заданы: %s", ", ".join(missing))
        sys.exit(1)

    init_db()
    await asyncio.to_thread(cleanup_old_messages)
    cleanup_task = asyncio.create_task(periodic_cleanup())

    await client.start()
    me = await client.get_me()
    ME_ID = me.id
    ME_USERNAME = me.username
    print(f"[STARTUP] @{me.username} (ID: {me.id})", flush=True)
    print(f"[STARTUP] TARGET_CHAT_ID = {TARGET_CHAT_ID}", flush=True)

    await catchup_history(client, TARGET_CHAT_ID)
    index_task = asyncio.create_task(background_index_embeddings(client, TARGET_CHAT_ID))

    await client.run_until_disconnected()
    cleanup_task.cancel()
    index_task.cancel()
    log.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
