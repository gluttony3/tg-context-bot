"""
Изолированный тест MTProto-апдейтов через Pyrogram.

Запуск:  uv run test_bot.py

Что делает:
  1. Подключается к Telegram через MTProto (ваш аккаунт, не бот).
  2. Ловит ВСЕ raw-апдейты и печатает имя типа каждого события.
  3. Ловит все текстовые сообщения и печатает chat_id + текст.
  4. Выводит info о вашем аккаунте (get_me).
  5. Держит процесс через idle() до Ctrl+C.

Если вы видите [RAW UPDATE] — MTProto-подключение работает.
Если вы видите [MSG] — MessageHandler тоже получает события.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from pyrogram import Client, idle
from pyrogram.handlers import MessageHandler, RawUpdateHandler
from pyrogram.types import Message
from pyrogram.types import Update

# ---------------------------------------------------------------------------
#  Конфигурация
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).with_name(".env"))

api_id: int = int(os.getenv("TELEGRAM_API_ID", "0"))
api_hash: str = os.getenv("TELEGRAM_API_HASH", "")

if not api_id or not api_hash:
    raise SystemExit(
        "TELEGRAM_API_ID / TELEGRAM_API_HASH не заданы в .env — "
        "добавьте и запустите снова."
    )

# ---------------------------------------------------------------------------
#  Хэндлеры
# ---------------------------------------------------------------------------


async def on_raw_update(client: Client, update: Update, *args) -> None:
    """Печатает имя класса каждого raw-апдейта."""
    name = type(update).__name__
    print(f"[RAW UPDATE] {name}", flush=True)


async def on_message(client: Client, message: Message) -> None:
    """Печатает chat_id и текст каждого входящего сообщения."""
    text = (message.text or message.caption or "").strip()
    sender = message.from_user
    sender_id = sender.id if sender else "?"
    print(
        f"[MSG] chat_id={message.chat.id} "
        f"sender_id={sender_id} "
        f"text={text[:80]!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
#  Точка входа
# ---------------------------------------------------------------------------

app = Client(
    name="sessions/test_session",
    api_id=api_id,
    api_hash=api_hash,
)


async def main() -> None:
    # Регистрируем хэндлеры явно — без декораторов
    app.add_handler(RawUpdateHandler(on_raw_update))
    app.add_handler(MessageHandler(on_message))

    await app.start()

    me = await app.get_me()
    print(f"\n{'='*50}", flush=True)
    print(f"  Авторизация OK", flush=True)
    print(f"  ID:       {me.id}", flush=True)
    print(f"  Имя:      {me.first_name}", flush=True)
    print(f"  Username: @{me.username}", flush=True)
    print(f"{'='*50}\n", flush=True)

    # Слушаем апдейты до Ctrl+C
    await idle()

    await app.stop()
    print("Остановлен.", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
