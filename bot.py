"""Telegram deal mirror: watch ONE source channel, swap Amazon links to our tag, repost to our channel.
Phase 1 = Amazon only. Non-Amazon links are logged so we can add Flipkart/Myntra (via Cuelinks/EarnKaro) next.
Run: python bot.py   (first run asks for phone + login code)
"""
import asyncio
import logging
import os
import sqlite3
import time

import httpx
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import UserAlreadyParticipantError
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import ChatInviteAlready, MessageMediaPhoto

from links import rewrite_text

load_dotenv("config.env")
load_dotenv()
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SOURCE_INVITE = os.environ["SOURCE_INVITE"]  # hash part after t.me/+
TARGET_INVITE = os.environ["TARGET_INVITE"]  # hash part of OUR channel invite link
TAG = os.environ["AMAZON_TAG"]  # e.g. yourname-21
DRY_RUN = os.getenv("DRY_RUN", "1") == "1"  # 1 = log only, don't post
DEDUP_HOURS = float(os.getenv("DEDUP_HOURS", "12"))
SESSION_STRING = os.getenv("SESSION_STRING")  # set on the server; made once with make_session.py
DATA_DIR = os.getenv("DATA_DIR", ".")
FOOTER = os.getenv("FOOTER", "As an Amazon Associate I earn from qualifying purchases.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dealbot")

db = sqlite3.connect(os.path.join(DATA_DIR, "seen.db"))
db.execute("CREATE TABLE IF NOT EXISTS seen(asin TEXT PRIMARY KEY, ts REAL)")
db.execute("CREATE TABLE IF NOT EXISTS log(ts REAL, src_id INTEGER, original TEXT, rewritten TEXT, others TEXT)")


def is_dup(asins):
    cutoff = time.time() - DEDUP_HOURS * 3600
    return any(db.execute("SELECT 1 FROM seen WHERE asin=? AND ts>?", (a, cutoff)).fetchone() for a in asins)


def mark(asins):
    db.executemany("INSERT OR REPLACE INTO seen VALUES(?,?)", [(a, time.time()) for a in asins])
    db.commit()


async def get_chat(client, invite):
    try:
        res = await client(ImportChatInviteRequest(invite))
        return res.chats[0]
    except UserAlreadyParticipantError:
        info = await client(CheckChatInviteRequest(invite))
        if isinstance(info, ChatInviteAlready):
            return info.chat
        raise


async def main():
    if SESSION_STRING:  # server mode: no interactive login possible
        client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            raise SystemExit("SESSION_STRING is invalid or expired - run make_session.py again")
    else:  # local mode: asks for phone + code on first run
        client = TelegramClient(os.path.join(DATA_DIR, "session"), API_ID, API_HASH)
        await client.start()
    source = await get_chat(client, SOURCE_INVITE)
    target = await get_chat(client, TARGET_INVITE)
    log.info("Watching '%s' -> posting to '%s' (dry_run=%s)", source.title, target.title, DRY_RUN)
    http = httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"})

    @client.on(events.NewMessage(chats=source))
    async def handler(ev):
        m = ev.message
        text = m.text or ""  # Telethon returns markdown; hidden links appear as [text](url)
        new, asins, others = await rewrite_text(text, TAG, http)
        db.execute("INSERT INTO log VALUES(?,?,?,?,?)", (time.time(), m.id, text, new, ",".join(others)))
        db.commit()
        if not asins:
            log.info("msg %s: no Amazon link (others: %s) - skipped", m.id, others)
            return
        if others:  # never repost a rival's affiliate link we could not convert
            log.info("msg %s: unconverted links remain %s - skipped", m.id, others)
            return
        if is_dup(asins):
            log.info("msg %s: duplicate ASIN %s - skipped", m.id, asins)
            return
        out = f"{new}\n\n{FOOTER}"
        log.info("msg %s -> %s\n%s", m.id, asins, out)
        if DRY_RUN:
            return
        if m.media and isinstance(m.media, MessageMediaPhoto):
            await client.send_file(target, m.media, caption=out, parse_mode="md")
        else:
            await client.send_message(target, out, parse_mode="md", link_preview=True)
        mark(asins)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
