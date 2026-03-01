import os
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

def progress_bar(percent):
    done = "█" * (percent // 5)
    left = "░" * (20 - percent // 5)
    return f"|{done}{left}| {percent}%"

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
    await message.reply("🔥 **HardSub Bot PRO (Fixed V2)**\n\n1. Video bhejo → /hsub\n2. .ass file bhejo → /encode")

@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(_, message):
    if not message.reply_to_message:
        return await message.reply("❌ Video par reply karke /hsub likho.")
    
    video = message.reply_to_message.video or message.reply_to_message.document
    if not video: return await message.reply("❌ Video nahi mili.")

    user_id = message.from_user.id
    ext = (video.file_name or "video.mp4").split(".")[-1].lower()
    path = os.path.join(DOWNLOAD_DIR, f"{user_id}_input.{ext}")
    
    msg = await message.reply("⏳ Downloading Video...")
    await message.reply_to_message.download(file_name=path)
    
    users_data[user_id] = {"video": path, "ext": ext}
    await msg.edit(f"✅ Video Saved! (Format: {ext.upper()})\nAb .ass file par /encode reply karein.")

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
    msg = await message.reply("⚙️ Encoding Start... (Fixed Black Screen Mode)")

    async with process_semaphore:
        duration = get_duration(video_file)
        # Escape path for Linux FFmpeg
        clean_sub_path = sub_file.replace("\\", "/").replace(":", "\\:")
        
        # FFmpeg Command: Subtitles + Black Screen Fix + High Compatibility
        cmd = [
            "ffmpeg", "-y", "-i", video_file,
            "-vf", f"ass='{clean_sub_path}'",
            "-c:v", "libx264", 
            "-pix_fmt", "yuv420p",    # CRITICAL: Fixes Black Screen
            "-preset", "ultrafast",   # RAM saving for Render
            "-crf", "23",             # Quality Balance
            "-c:a", "aac",            # Fixes Audio compatibility
            "-strict", "experimental",
            "-map", "0:v:0",          # First video stream
            "-map", "0:a:0",          # First audio stream
            output
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )
        
        last_update = time.time()
        while True:
            line = await process.stderr.readline()
            if not line: break
            line = line.decode(errors="ignore").strip()
            
            if "time=" in line:
                try:
                    t = re.search(r"time=(\d+:\d+:\d+\.\d+)", line).group(1)
                    h, m, s = t.split(":")
                    curr = int(h)*3600 + int(m)*60 + float(s)
                    p = min(int((curr/duration)*100), 100)
                    
                    if time.time() - last_update > 10:
                        await msg.edit(f"🎬 **Encoding: {p}%**\n{progress_bar(p)}")
                        last_update = time.time()
                except: pass

        await process.wait()
        
        if os.path.exists(output) and os.path.getsize(output) > 10000:
            await msg.edit("📤 Uploading...")
            # Upload as document to keep original format/quality
            await client.send_document(
                message.chat.id, 
                document=output, 
                caption=f"✅ HardSub Success!\nFormat: {original_ext.upper()}"
            )
            await msg.delete()
        else:
            await msg.edit("❌ Encoding Failed! Check if your .ass file has errors.")

        # Cleanup
        for f in [video_file, sub_file, output]:
            if os.path.exists(f): os.remove(f)
        users_data.pop(user_id, None)

# ====================== WEB SERVER ======================
web_app = Flask(__name__)
@web_app.route("/")
def home(): return "Bot is Alive"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    app.run()
