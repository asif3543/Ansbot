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

# Read env vars
try:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH") or ""
    BOT_TOKEN = os.getenv("BOT_TOKEN") or ""

    if not API_ID or not API_HASH or not BOT_TOKEN:
        raise ValueError("Missing API_ID / API_HASH / BOT_TOKEN in environment variables!")
except Exception as e:
    print("CRITICAL ERROR in env vars:")
    traceback.print_exc()
    sys.exit(1)

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from PIL import Image
from flask import Flask

import nest_asyncio
nest_asyncio.apply()

# =========================
# BOT INITIALIZATION
# =========================
app = Client("animebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# =========================
# FOLDERS & VARIABLES
# =========================
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

process_semaphore = asyncio.Semaphore(2)
user_settings = {}
users_data = {}
active_process = {}

# =========================
# UTILITIES
# =========================
def progress_bar(percent):
    filled = int(percent / 5)
    return "█" * filled + "░" * (20 - filled)

def get_duration(file):
    try:
        result = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", file],
                                capture_output=True, text=True)
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
        "**Steps:**\n"
        "1. Video bhejo → reply with **/hsub**\n"
        "2. .ass file bhejo → reply with **/encode**\n\n"
        "📸 Photo bhejo for Watermark + Thumbnail"
    )

# =========================
# PHOTO → WATERMARK + THUMB
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
    except:
        pass

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("↖️ Top Left", callback_data="wm_topleft"),
         InlineKeyboardButton("↗️ Top Right", callback_data="wm_topright")],
        [InlineKeyboardButton("❌ No Watermark", callback_data="wm_none")]
    ])

    await msg.edit("✅ **Image Saved!**\nWatermark kaha chahiye?", reply_markup=buttons)

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
        txt = "Watermark Disabled"

    await callback_query.message.edit(f"✅ {txt}")

# =========================
# /HSUB - SAVE VIDEO
# =========================
@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(client, message):
    if not message.reply_to_message:
        return await message.reply("❌ Video pe reply karke **/hsub** likho")

    video = message.reply_to_message.video or message.reply_to_message.document
    if not video:
        return await message.reply("❌ Valid video bhejo (.mp4 / .mkv)")

    user_id = message.from_user.id
    ext = video.file_name.split(".")[-1].lower() if video.file_name else "mp4"
    file_path = f"downloads/{user_id}.{ext}"

    msg = await message.reply("⏳ Downloading Video...")
    await message.reply_to_message.download(file_name=file_path)

    if user_id not in users_data:
        users_data[user_id] = {}
    users_data[user_id]["video"] = file_path

    await msg.edit("✅ Video Saved!\nAb .ass file bhejo aur **/encode** reply karo")

# =========================
# /ENCODE - FIXED & RELIABLE (Dost ke tarike se)
# =========================
@app.on_message(filters.command("encode") & filters.private)
async def handle_encode(client, message):
    user_id = message.from_user.id

    if not message.reply_to_message or not message.reply_to_message.document or not message.reply_to_message.document.file_name.lower().endswith((".ass", ".srt", ".ssa", ".vtt")):
        return await message.reply("❌ .ass file pe reply karke **/encode** likho")

    if user_id not in users_data or "video" not in users_data[user_id]:
        return await message.reply("❌ Pehle video bhejo aur /hsub use karo")

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
            duration = 100

        wm_pos = user_settings.get(user_id, {}).get("wm_pos", "none")

        # Simple & Reliable FFmpeg Command
        if wm_pos in ["topleft", "topright"] and os.path.exists(logo_file):
            overlay = "15:15" if wm_pos == "topleft" else "main_w-overlay_w-15:15"
            cmd = [
                "ffmpeg", "-y",
                "-i", video_file,
                "-i", logo_file,
                "-filter_complex", f"[1:v]scale=120:-1[wm];[0:v][wm]overlay={overlay} print("DEBUG: Working dir:", os.getcwd())
print("DEBUG: sub_file exists?", os.path.exists(sub_file))
print("DEBUG: video_file exists?", os.path.exists(video_file))
                "-map", "[out]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy",
                output_file
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_file,
                sub_file_safe = os.path.basename(sub_file)  # sirf filename (Docker cwd /app hai)
                "-vf", f"subtitles='{sub_file_safe}'",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy",
                output_file
            ]

        print("DEBUG: FFmpeg Command →", " ".join(cmd))

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )

        active_process[user_id] = process

        last_percent = -1
        speed = "0x"
        last_update = time.time()

        while True:
            line = await process.stderr.readline()
            if not line:
                break
            line = line.decode(errors="ignore").strip()

            if "time=" in line:
                try:
                    tm = re.search(r"time=(\d+:\d+:\d+\.\d+)", line)
                    if tm:
                        h, m, s = tm.group(1).split(":")
                        curr = int(h)*3600 + int(m)*60 + float(s)
                        percent = min(int((curr / duration) * 100), 100)

                        now = time.time()
                        if percent != last_percent and now - last_update > 3:
                            bar = progress_bar(percent)
                            sp = re.search(r"speed=\s*([\d\.]+)x?", line)
                            if sp:
                                speed = sp.group(1) + "x"

                            await msg.edit(
                                f"🎬 **Encoding Video...**\n\n"
                                f"{bar} {percent}%\n\n"
                                f"⚡ Speed: {speed}"
                            )
                            last_percent = percent
                            last_update = now
                except:
                    pass

        return_code = await process.wait()
        if user_id in active_process:
            del active_process[user_id]

        if return_code != 0 or not os.path.exists(output_file):
            await msg.edit("❌ Encoding Failed! (Logs check karo)")
            return

        await msg.edit("📤 Uploading...")

        thumb_path = thumb_file if os.path.exists(thumb_file) else None

        last_up = time.time()
        async def upload_progress(current, total):
            nonlocal last_up
            percent = int((current / total) * 100)
            now = time.time()
            if now - last_up > 3:
                bar = progress_bar(percent)
                try:
                    await msg.edit(f"📤 **Uploading...**\n\n{bar} {percent}%")
                    last_up = now
                except:
                    pass

        await client.send_video(
            message.chat.id,
            video=output_file,
            thumb=thumb_path,
            caption="✅ **HardSub + Watermark Done!**",
            supports_streaming=True,
            progress=upload_progress
        )

        await msg.delete()

        # Cleanup
        for f in [video_file, sub_file, output_file]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass
        users_data.pop(user_id, None)

# =========================
# DUMMY FLASK FOR RENDER
# =========================
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "🚀 Bot is Running!"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# =========================
# MAIN RUN
# =========================
if __name__ == "__main__":
    print("🌐 Starting Dummy Server for Render...")
    threading.Thread(target=run_server, daemon=True).start()

    print("🚀 Starting Pyrogram Bot...")
    app.run()
