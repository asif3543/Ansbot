import os

# Telegram API credentials from Render Environment Variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Optional: Safety check (deploy logs mein dikhega agar missing ho)
if not API_ID or not API_HASH or not BOT_TOKEN:
    raise ValueError("Missing required env vars: API_ID, API_HASH, or BOT_TOKEN. Set them in Render Dashboard > Environment.")
