import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient, events

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")

# connection_retries=None заставляет Telethon бесконечно переподключаться при сбросе NAT-сессии
client = TelegramClient(
    "sessions/telethon_session", 
    API_ID, 
    API_HASH,
    connection_retries=None,
    retry_delay=2
)

@client.on(events.NewMessage)
async def handler(event):
    chat = await event.get_chat()
    sender = await event.get_sender()
    sender_name = getattr(sender, 'first_name', 'Unknown')
    print(f"\n[TELETHON MSG] Chat: {event.chat_id} | From: {sender_name} | Text: '{event.raw_text}'", flush=True)

async def main():
    await client.start()
    me = await client.get_me()
    print("==================================================")
    print("  Telethon Авторизация OK")
    print(f"  ID:       {me.id}")
    print(f"  Имя:      {me.first_name}")
    print(f"  Username: @{me.username}")
    print("==================================================")
    print("Отправь сообщение в любой чат или Saved Messages...\n")
    
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())