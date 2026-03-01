import os
import time
import asyncio
import threading
import sys
import traceback
import re
import json
import subprocess

# Debug prints
print("DEBUG: bot.py started")
print("DEBUG: Python version:", sys.version)

# Read env vars with safety
try:
    API_ID_raw = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH") or ""
    BOT_TOKEN = os.getenv("BOT_TOKEN") or ""

    if not API_ID_raw:
        raise ValueError("API_ID is missing in environment variables!")
    API_ID = int(API_ID_raw)

    if not API_HASH or not BOT_TOKEN:
        raise ValueError("API_HASH or BOT_TOKEN missing!")
except Exception as e:
    print("CRITICAL ERROR in config/env vars:")
    traceback.print_exc()
    sys.exit(1)

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image
from flask import Flask

import nest_asyncio
nest_asyncio.apply()

# =========================
# BOT INITIALIZATION
# =========================
app = Client(
    "animebot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# =========================
# FOLDERS & VARIABLES
# =========================
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

process_semaphore = asyncio.Semaphore(2)
user_settings = {}
users_data = {} # To keep track of user files safely
active_process = {} # To cancel encoding if needed

# =========================
# UTILITIES (From Reference Code)
# =========================
def progress_bar(percent):
    filled = int(percent / 5)
    return "█" * filled + "░" * (20 - filled)

def get_duration(file):
    try:
        result = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", file],
            capture_output=True, text=True
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except:
        return 0.0

# =========================
# START COMMAND
# =========================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply(
        "🔥 **Anime HardSub & Watermark Bot Ready!**\n\n"
        "**Steps to use:**\n"
        "1️⃣ Forward/Send Video (.mp4 / .mkv) and reply with **/hsub**\n"
        "2️⃣ Forward/Send Subtitle (.ass) and reply with **/encode**\n\n"
        "📸 **Watermark & Thumbnail:** Just send any Photo to the bot!"
    )

# =========================
# PHOTO -> WATERMARK + THUMB
# =========================
@app.on_message(filters.photo & filters.private)
async def save_photo(client, message):
    user_id = message.from_user.id
    logo_path = f"downloads/{user_id}_logo.png"
    thumb_path = f"thumbnails/{user_id}.jpg"

    msg = await message.reply("⏳ Processing Image...")
    await message.download(file_name=logo_path)

    try:
        img = Image.open(logo_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail((320, 320))
        img.save(thumb_path, "JPEG")
    except Exception as e:
        print(f"Thumbnail resize error: {e}")

    buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("↖️ Top Left", callback_data="wm_topleft"),
            InlineKeyboardButton("↗️ Top Right", callback_data="wm_topright")
        ],[InlineKeyboardButton("❌ No Watermark", callback_data="wm_none")]
    ])

    await msg.edit("✅ **Image Saved!**\nWhere do you want Watermark?", reply_markup=buttons)

@app.on_callback_query(filters.regex("^wm_"))
async def wm_callback(client, callback_query):
    user_id = callback_query.from_user.id
    choice = callback_query.data

    if user_id not in user_settings:
        user_settings[user_id] = {}

    if choice == "wm_topleft":
        user_settings[user_id]["wm_pos"] = "topleft"
        txt = "Top Left Selected ↖️"
    elif choice == "wm_topright":
        user_settings[user_id]["wm_pos"] = "topright"
        txt = "Top Right Selected ↗️"
    else:
        user_settings[user_id]["wm_pos"] = "none"
        txt = "Watermark Disabled (Only Thumbnail)"

    await callback_query.message.edit(f"✅ {txt}")

# =========================
# /HSUB - SAVE VIDEO
# =========================
@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(client, message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a Video with **/hsub**")

    video = message.reply_to_message.video or message.reply_to_message.document
    if not video:
        return await message.reply("❌ Reply to a valid Video.")

    file_name = getattr(video, "file_name", "video.mp4")
    ext = file_name.split(".")[-1].lower() if "." in file_name else "mp4"

    if ext not in["mp4", "mkv", "avi", "webm"]:
        return await message.reply("❌ Please reply to a Video (.mp4 / .mkv)")

    user_id = message.from_user.id
    file_path = f"downloads/{user_id}.{ext}"

    msg = await message.reply("⏳ Downloading Video...")
    await message.reply_to_message.download(file_name=file_path)
    
    # Store in memory
    if user_id not in users_data:
        users_data[user_id] = {}
    users_data[user_id]["video"] = file_path

    await msg.edit("✅ Video Saved!\nNow send **.ass** file and reply to it with **/encode**")

# =========================
# /ENCODE - REAL PROGRESS BAR + FFMPEG
# =========================
@app.on_message(filters.command("encode") & filters.private)
async def handle_encode(client, message):
    user_id = message.from_user.id

    if not message.reply_to_message:
        return await message.reply("❌ Reply to a **.ass** file with **/encode**")

    doc = message.reply_to_message.document
    if not doc or not doc.file_name.lower().endswith(".ass"):
        return await message.reply("❌ Only .ass files supported!")

    if user_id not in users_data or "video" not in users_data[user_id]:
        return await message.reply("❌ No video found! Please use **/hsub** on a video first.")

    video_file = users_data[user_id]["video"]
    sub_file = f"downloads/{user_id}.ass"
    logo_file = f"downloads/{user_id}_logo.png"
    thumb_file = f"thumbnails/{user_id}.jpg"
    output_file = f"downloads/{user_id}_out.mp4"

    msg = await message.reply("⏳ Downloading Subtitle...")
    await message.reply_to_message.download(file_name=sub_file)

    await msg.edit("🔥 Starting Encoding...")

    async with process_semaphore:
        duration = get_duration(video_file)
        if duration == 0.0:
            duration = 100 # Fallback if duration fetch fails

        wm_pos = user_settings.get(user_id, {}).get("wm_pos", "none")
        
        # Absolute path for ASS file to prevent FFmpeg errors
        abs_sub = os.path.abspath(sub_file)
        escaped_sub = abs_sub.replace("\\", "/").replace(":", "\\:")
        
        # Build strict FFmpeg Command as List
        if wm_pos in ["topleft", "topright"] and os.path.exists(logo_file):
            overlay_coords = "15:15" if wm_pos == "topleft" else "main_w-overlay_w-15:15"
            cmd =[
                "ffmpeg", "-y", "-i", video_file, "-i", logo_file,
                "-filter_complex", f"[1:v]scale=120:-1[wm];[0:v][wm]overlay={overlay_coords}[bg];[bg]ass='{escaped_sub}'[out]",
                "-map", "[out]", "-map", "0:a",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy", output_file
            ]
        else:
            cmd =[
                "ffmpeg", "-y", "-i", video_file,
                "-vf", f"ass='{escaped_sub}'",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy", output_file
            ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        active_process[user_id] = process

        last_percent = -1
        speed = "0x"
        last_update_time = time.time()

        # Reading FFmpeg Output for Real Progress
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            line = line.decode(errors="ignore")

            if "time=" in line:
                try:
                    time_part = re.search(r"time=(\d+:\d+:\d+\.\d+)", line)
                    if time_part:
                        h, m, s = time_part.group(1).split(":")
                        current_time = int(h)*3600 + int(m)*60 + float(s)
                        percent = int((current_time / duration) * 100)
                        percent = min(percent, 100)

                        current_sys_time = time.time()
                        # Update every 3 seconds to avoid FloodWait Error from Telegram
                        if percent != last_percent and (current_sys_time - last_update_time) > 3.0:
                            bar = progress_bar(percent)
                            speed_match = re.search(r"speed=\s*([\d\.x]+)", line)
                            if speed_match:
                                speed = speed_match.group(1)

                            await msg.edit(
                                f"🎬 **Encoding Video...**\n\n"
                                f"{bar} {percent}%\n\n"
                                f"⚡ Speed: {speed}\n"
                            )
                            last_percent = percent
                            last_update_time = current_sys_time
                except:
                    pass

        return_code = await process.wait()

        if user_id in active_process:
            del active_process[user_id]

        if return_code != 0 or not os.path.exists(output_file):
            await msg.edit("❌ Encoding Failed! FFmpeg Error.")
            return

        await msg.edit("📤 Preparing to Upload...")
        thumb_path = thumb_file if os.path.exists(thumb_file) else None

        # UPLOAD PROGRESS FUNCTION
        last_upload_time = time.time()
        async def upload_progress(current, total):
            nonlocal last_upload_time
            percent = int((current / total) * 100)
            current_sys_time = time.time()
            if (current_sys_time - last_upload_time) > 3.0:
                bar = progress_bar(percent)
                try:
                    await msg.edit(f"📤 **Uploading...**\n\n{bar} {percent}%")
                    last_upload_time = current_sys_time
                except:
                    pass

        await client.send_video(
            message.chat.id,
            video=output_file,
            thumb=thumb_path,
            caption="✅ **HardSub & Watermark Done!**",
            supports_streaming=True,
            progress=upload_progress
        )
        
        await msg.delete()

        # Cleanup Memory & Files
        for file in [video_file, sub_file, output_file]:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except:
                    pass
        users_data.pop(user_id, None)

# =========================
# DUMMY FLASK SERVER FOR RENDER
# =========================
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "🚀 Anime HardSub Bot is Running!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# =========================
# MAIN RUN
# =========================
if __name__ == "__main__":
    print("🌐 Starting Dummy Web Server for Render...")
    threading.Thread(target=run_server, daemon=True).start()

    print("🚀 Starting Pyrogram Bot...")
    app.run()
