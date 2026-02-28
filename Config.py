# config.py
import os

API_ID = int(os.getenv("API_ID") or "0")
API_HASH = os.getenv("API_HASH") or ""
BOT_TOKEN = os.getenv("BOT_TOKEN") or ""

# Safety check (logs mein dikhega agar missing)
if API_ID == 0 or not API_HASH or not BOT_TOKEN:
    raise ValueError("Missing Telegram credentials! Set API_ID, API_HASH, BOT_TOKEN in Render Environment Variables.")
