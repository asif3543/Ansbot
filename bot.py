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

# Initialize nest_asyncio
nest_asyncio.apply()

# ====================== ENV VARS ======================
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = Client("animebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Directories Create Karein
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

process_semaphore = asyncio.Semaphore(1) 
user_settings = {}
users_data = {}

# ====================== UTILS ======================

def progress_bar(percent):
    done = "█" * (percent // 5)
    left = "░" * (20 - percent // 5)
    return done + left

def get_duration(file):
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(json.loads(result.stdout)["format"]["duration"])
    except:
        return 100.0

# ====================== HANDLERS ======================

@app.on_message(filters.command("start") & filters.private)
async def start(_, message):
    await message.reply("🔥 **HardSub Bot (ASS Only)**\n\n1. Video bhejo → /hsub\n2. .ass file bhejo → /encode")

@app.on_message(filters.photo & filters.private)
async def save_photo(_, message):
    user_id = message.from_user.id
    logo = f"downloads/{user_id}_logo.png"
    await message.download(file_name=logo)  
    
    btn = InlineKeyboardMarkup([  
        [InlineKeyboardButton("↖️ Top Left", callback_data="wm_topleft"),  
         InlineKeyboardButton("↗️ Top Right", callback_data="wm_topright")],  
        [InlineKeyboardButton("❌ No Watermark", callback_data="wm_none")]  
    ])  
    await message.reply("✅ Logo Saved! Position select karein:", reply_markup=btn)

@app.on_callback_query(filters.regex("^wm_"))
async def wm_callback(_, query):
    pos = query.data.replace("wm_", "")
    user_settings[query.from_user.id] = {"wm_pos": pos}
    await query.message.edit(f"✅ Position Set: **{pos}**")

@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(_, message):
    if not message.reply_to_message or not (message.reply_to_message.video or message.reply_to_message.document):
        return await message.reply("❌ Video file par reply karke /hsub likhein.")
    
    user_id = message.from_user.id
    video = message.reply_to_message.video or message.reply_to_message.document
    path = f"downloads/{user_id}_input.mp4"
    
    msg = await message.reply("⏳ Video download ho raha hai...")
    await message.reply_to_message.download(file_name=path)
    users_data[user_id] = {"video": path}
    await msg.edit("✅ Video Saved! Ab **.ass** file bhejein aur uspar `/encode` reply karein.")

@app.on_message(filters.command("encode") & filters.private)
async def handle_encode(client, message):
    user_id = message.from_user.id
    
    if user_id not in users_data:
        return await message.reply("❌ Pehle video save karein (/hsub).")

    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("❌ .ass file par reply karke /encode likhein.")

    sub_file = f"downloads/{user_id}.ass"
    video_file = users_data[user_id]["video"]
    logo_file = f"downloads/{user_id}_logo.png"
    output = f"downloads/{user_id}_final.mp4"
    
    await message.reply_to_message.download(file_name=sub_file)
    msg = await message.reply("⚙️ Encoding Start...")

    async with process_semaphore:
        duration = get_duration(video_file)
        wm_pos = user_settings.get(user_id, {}).get("wm_pos", "none")
        
        # FFmpeg Subtitle Path Fix (Important for Linux/VPS)
        clean_sub_path = os.path.abspath(sub_file).replace("\\", "/").replace(":", "\\:")

        if wm_pos != "none" and os.path.exists(logo_file):
            pos = "15:15" if wm_pos == "topleft" else "main_w-overlay_w-15:15"
            # Complex filter for Watermark + ASS
            filter_complex = f"[1:v]scale=120:-1[wm];[0:v][wm]overlay={pos}[bg];[bg]ass='{clean_sub_path}'"
            cmd = [
                "ffmpeg", "-y", "-i", video_file, "-i", logo_file,
                "-filter_complex", filter_complex,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy", output
            ]
        else:
            # Simple filter for only ASS
            cmd = [
                "ffmpeg", "-y", "-i", video_file,
                "-vf", f"ass='{clean_sub_path}'",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy", output
            ]

        process = await asyncio.create_subprocess_exec(*cmd, stderr=asyncio.subprocess.PIPE)
        
        last_time = time.time()
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
                    
                    if time.time() - last_time > 5: # 5 second update interval
                        await msg.edit(f"🎬 **Encoding: {p}%**\n{progress_bar(p)}")
                        last_time = time.time()
                except: pass

        await process.wait()
        
        if os.path.exists(output) and os.path.getsize(output) > 1000:
            await msg.edit("📤 Uploading...")
            await client.send_video(
                message.chat.id, 
                video=output, 
                caption="✅ **HardSub Successful!**",
                supports_streaming=True
            )
            await msg.delete()
        else:
            await msg.edit("❌ Encoding Failed! Check if the .ass file is valid and FFmpeg has libass support.")

        # Cleanup Files
        for f in [video_file, sub_file, output]:
            if os.path.exists(f): os.remove(f)
        users_data.pop(user_id, None)

# ====================== WEB SERVER (Keep Alive) ======================
web_app = Flask(__name__)
@web_app.route("/")
def home(): return "Bot is Running"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    print("🚀 Bot Started!")
    app.run()
