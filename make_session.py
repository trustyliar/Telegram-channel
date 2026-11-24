"""Run ONCE on your own computer to log in and print a SESSION_STRING for the server.
Treat the string like a password: anyone with it controls your Telegram account."""
import os
from dotenv import load_dotenv
from telethon.sessions import StringSession
from telethon.sync import TelegramClient

load_dotenv("config.env")
load_dotenv()
api_id = int(os.getenv("API_ID") or input("API_ID: "))
api_hash = os.getenv("API_HASH") or input("API_HASH: ")
with TelegramClient(StringSession(), api_id, api_hash) as c:
    print("\nSESSION_STRING (copy everything on the next line):\n")
    print(c.session.save())
