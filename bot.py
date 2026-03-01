import os
import time
import asyncio
import threading
import subprocess
import json
from pyrogram import Client, filters
from flask import Flask

# ====================== CONFIG ======================
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = Client("animebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

BASE_DIR = os.getcwd()
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Ek baar mein ek hi encode hoga taaki RAM crash na ho
process_semaphore = asyncio.Semaphore(1) 
users_data = {}

# ====================== WEB SERVER (For Render Health Check) ======================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is Running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

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
    await message.reply("🔥 **HardSub Bot Fixed V3**\n\n1. Video bhejo -> /hsub\n2. .ass file bhejo -> /encode")

@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(_, message):
    target = message.reply_to_message
    video = target.video or target.document if target else None
    if not video:
        return await message.reply("❌ Video/File par reply karke /hsub likho.")

    user_id = message.from_user.id
    ext = (video.file_name or "video.mp4").split(".")[-1].lower()
    path = os.path.join(DOWNLOAD_DIR, f"{user_id}_input.{ext}")
    
    msg = await message.reply("⏳ Downloading Video...")
    await target.download(file_name=path)
    
    users_data[user_id] = {"video": path, "ext": ext}
    await msg.edit(f"✅ Video Saved! Ab .ass file par /encode reply karein.")

@app.on_message(filters.command("encode") & filters.private)
async def handle_encode(client, message):
    user_id = message.from_user.id
    if user_id not in users_data:
        return await message.reply("❌ Pehle /hsub use karein.")
    
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("❌ .ass file par reply karein.")

    input_data = users_data[user_id]
    video_file = input_data["video"]
    original_ext = input_data["ext"]
    sub_file = os.path.join(DOWNLOAD_DIR, f"{user_id}.ass")
    output = os.path.join(DOWNLOAD_DIR, f"{user_id}_final.{original_ext}")
    
    await message.reply_to_message.download(file_name=sub_file)
    msg = await message.reply("⚙️ Encoding... (Isme time lagta hai, sabar rakhein)")

    async with process_semaphore:
        # Fonts directory setup for Render
        font_dir = os.path.join(BASE_DIR, ".fonts")
        clean_sub_path = sub_file.replace("\\", "/").replace(":", "\\:")
        
        # FFmpeg Command - Fixed for Black Screen and Low RAM
        cmd = [
            "ffmpeg", "-y", "-i", video_file,
            "-vf", f"ass='{clean_sub_path}':fontsdir='{font_dir}'",
            "-c:v", "libx264", 
            "-pix_fmt", "yuv420p",    # Black Screen Fix
            "-preset", "ultrafast",   # CPU saving
            "-crf", "28",             # RAM saving
            "-c:a", "copy",           # Audio original
            "-threads", "1",          # Crash prevention
            output
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )
        
        # Logs read karna zaroori hai taaki buffer full na ho
        await process.communicate()
        
        if os.path.exists(output) and os.path.getsize(output) > 1000:
            await msg.edit("📤 Uploading...")
            await client.send_document(message.chat.id, document=output, caption="✅ HardSub Done!")
            await msg.delete()
        else:
            await msg.edit("❌ Encoding Failed! Check file quality or size.")

        # Clean up
        for f in [video_file, sub_file, output]:
            if os.path.exists(f): os.remove(f)
        users_data.pop(user_id, None)

# ====================== MAIN EXECUTION ======================

if __name__ == "__main__":
    # 1. Flask ko background thread mein start karo (Render Timeout fix)
    threading.Thread(target=run_flask, daemon=True).start()
    
    # 2. Pyrogram Bot ko main thread mein start karo
    print("🤖 Bot Starting...")
    app.run()
