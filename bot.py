import os  # FIX 1: Chhota 'i' kar diya hai
import time
import asyncio
import threading
import re
import json
import subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import nest_asyncio

nest_asyncio.apply()

# ====================== CONFIG ======================
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = Client("animebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

BASE_DIR = os.getcwd()
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

process_semaphore = asyncio.Semaphore(1) 
users_data = {}

# ====================== UTILS ======================

def get_duration(file):
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(json.loads(result.stdout)["format"]["duration"])
    except:
        return 1.0

# ====================== HANDLERS ======================

@app.on_message(filters.command("start") & filters.private)
async def start(_, message):
    await message.reply("✅ **Bot Ready (Fixed Version)**\n\n1. Video bhejo -> /hsub\n2. .ass file bhejo -> /encode")

@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(_, message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a video.")
    
    video = message.reply_to_message.video or message.reply_to_message.document
    if not video: return await message.reply("❌ No video found.")

    user_id = message.from_user.id
    ext = (video.file_name or "video.mp4").split(".")[-1].lower()
    path = os.path.join(DOWNLOAD_DIR, f"{user_id}_input.{ext}")
    
    msg = await message.reply("⏳ Downloading...")
    await message.reply_to_message.download(file_name=path)
    
    users_data[user_id] = {"video": path, "ext": ext}
    await msg.edit(f"✅ Video Saved!\nAb .ass file par /encode reply karein.")

@app.on_message(filters.command("encode") & filters.private)
async def handle_encode(client, message):
    user_id = message.from_user.id
    if user_id not in users_data:
        return await message.reply("❌ Pehle /hsub use karein.")
    
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("❌ .ass file par reply karein.")

    input_data = users_data[user_id]
    original_ext = input_data["ext"]
    video_file = input_data["video"]
    sub_file = os.path.join(DOWNLOAD_DIR, f"{user_id}.ass")
    output = os.path.join(DOWNLOAD_DIR, f"{user_id}_final.{original_ext}")
    
    await message.reply_to_message.download(file_name=sub_file)
    msg = await message.reply("⚙️ Encoding... (Fixing Black Screen)")

    async with process_semaphore:
        duration = get_duration(video_file)
        font_dir = os.path.join(BASE_DIR, ".fonts")
        clean_sub_path = sub_file.replace("\\", "/").replace(":", "\\:")
        
        # FFmpeg Command with YUV420P Fix
        cmd = [
            "ffmpeg", "-y", "-i", video_file,
            "-vf", f"ass='{clean_sub_path}':fontsdir='{font_dir}'",
            "-c:v", "libx264", 
            "-pix_fmt", "yuv420p",    # ISSE VIDEO SHOW HOGI (NO BLACK SCREEN)
            "-preset", "ultrafast", 
            "-crf", "24", 
            "-c:a", "copy",           
            "-threads", "1",          
            output
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )
        
        # FIX 2: Deadlock hatane ke liye communicate() use kiya
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 10000:
            await msg.edit("📤 Uploading...")
            await client.send_document(message.chat.id, document=output, caption=f"✅ HardSub Success!")
            await msg.delete()
        else:
            error_log = stderr.decode()[-200:] if stderr else "Unknown Error"
            await msg.edit(f"❌ Encoding Failed!\nLog: `{error_log}`")

        # Cleanup
        for f in [video_file, sub_file, output]:
            if os.path.exists(f): os.remove(f)
        users_data.pop(user_id, None)

# ====================== WEB SERVER ======================
web_app = Flask(__name__)
@web_app.route("/")
def home(): return "Alive"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    app.run()
