import os
import time
import asyncio
import threading
import sys
import re
import json
import subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image
from flask import Flask
import nest_asyncio

nest_asyncio.apply()

# ====================== ENV VARS ======================
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = Client("animebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Ensure directories exist with absolute paths
BASE_DIR = os.getcwd()
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
THUMB_DIR = os.path.join(BASE_DIR, "thumbnails")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)

process_semaphore = asyncio.Semaphore(1) 
user_settings = {}
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
    await message.reply("🔥 **HardSub Bot (Original Format Fix)**\n\n1. Video bhejo → /hsub\n2. .ass file bhejo → /encode")

@app.on_message(filters.photo & filters.private)
async def save_photo(_, message):
    user_id = message.from_user.id
    logo = os.path.join(DOWNLOAD_DIR, f"{user_id}_logo.png")
    await message.download(file_name=logo)  
    
    btn = InlineKeyboardMarkup([  
        [InlineKeyboardButton("↖️ Top Left", callback_data="wm_topleft"),  
         InlineKeyboardButton("↗️ Top Right", callback_data="wm_topright")],  
        [InlineKeyboardButton("❌ No Watermark", callback_data="wm_none")]  
    ]) 
    await message.reply("✅ Logo Saved!", reply_markup=btn)

@app.on_callback_query(filters.regex("^wm_"))
async def wm_callback(_, query):
    pos = query.data.replace("wm_", "")
    user_settings[query.from_user.id] = {"wm_pos": pos}
    await query.message.edit(f"✅ Position: **{pos}**")

@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(_, message):
    if not message.reply_to_message:
        return await message.reply("❌ Video par reply karke /hsub likho.")
    
    user_id = message.from_user.id
    video = message.reply_to_message.video or message.reply_to_message.document
    if not video: return await message.reply("❌ Video nahi hai.")

    # Get original extension (mp4, mkv, etc.)
    original_ext = (video.file_name or "video.mp4").split(".")[-1].lower()

    path = os.path.join(DOWNLOAD_DIR, f"{user_id}_input.{original_ext}")
    msg = await message.reply("⏳ Downloading Video...")
    await message.reply_to_message.download(file_name=path)
    
    # Save path and extension
    users_data[user_id] = {"video": path, "ext": original_ext}
    await msg.edit(f"✅ Video Saved! (Format: {original_ext.upper()})\nAb .ass file par /encode reply karein.")

# ====================== CORE ENCODER ======================

@app.on_message(filters.command("encode") & filters.private)
async def handle_encode(client, message):
    user_id = message.from_user.id
    
    if user_id not in users_data:
        return await message.reply("❌ Pehle /hsub use karein.")
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("❌ .ass file par reply karein.")

    original_ext = users_data[user_id].get("ext", "mp4")
    
    # Paths Setup
    sub_file = os.path.join(DOWNLOAD_DIR, f"{user_id}.ass")
    video_file = users_data[user_id]["video"]
    logo_file = os.path.join(DOWNLOAD_DIR, f"{user_id}_logo.png")
    output = os.path.join(DOWNLOAD_DIR, f"{user_id}_final.{original_ext}") # Keeps original format
    
    await message.reply_to_message.download(file_name=sub_file)
    msg = await message.reply("⚙️ Encoding Start (Original Quality)...")

    async with process_semaphore:
        duration = get_duration(video_file)
        wm_pos = user_settings.get(user_id, {}).get("wm_pos", "none")
        
        clean_sub_path = sub_file.replace("\\", "/").replace(":", "\\:")

        # Filter Logic
        if wm_pos != "none" and os.path.exists(logo_file):
            pos = "15:15" if wm_pos == "topleft" else "main_w-overlay_w-15:15"
            vf = f"[1:v]scale=120:-1[wm];[0:v][wm]overlay={pos}[bg];[bg]ass='{clean_sub_path}'"
        else:
            vf = f"ass='{clean_sub_path}'"

        # FFmpeg Command with Black Screen Fix (-pix_fmt yuv420p)
        cmd = [
            "ffmpeg", "-y", "-i", video_file,
            "-i", logo_file if os.path.exists(logo_file) else video_file,
            "-filter_complex" if "overlay" in vf else "-vf", vf,
            "-c:v", "libx264", 
            "-pix_fmt", "yuv420p", # FIX FOR BLACK SCREEN IN TELEGRAM
            "-preset", "fast",     # Better quality retention
            "-crf", "23",          # Visual lossless
            "-c:a", "copy",        # Keep original audio
            "-map", "0:a?", 
            "-threads", "1", 
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
                    
                    if time.time() - last_update > 8:
                        await msg.edit(f"🎬 **Encoding In Progress**\n\n{progress_bar(p)}")
                        last_update = time.time()
                except: pass

        await process.wait()
        
        if os.path.exists(output) and os.path.getsize(output) > 5000:
            await msg.edit("📤 Uploading...")
            await client.send_document(message.chat.id, document=output, caption=f"✅ HardSub Success! (Format: {original_ext.upper()})")
            await msg.delete()
        else:
            _, stderr = await process.communicate()
            error_log = stderr.decode()[-200:]
            await msg.edit(f"❌ **Encoding Failed!**\n\nReason: Font missing or filter error.\n`Log: {error_log}`")

        # Cleanup
        for f in [video_file, sub_file, output]:
            if os.path.exists(f): os.remove(f)
        users_data.pop(user_id, None)

# ====================== WEB SERVER ======================
web_app = Flask(__name__)
@web_app.route("/")
def home(): return "Bot Running"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    app.run()
