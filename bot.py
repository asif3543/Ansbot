import os
import time
import asyncio
import threading
import sys
import traceback
import re
import json
import subprocess

print("DEBUG: bot.py started")
print("DEBUG: Python version:", sys.version)

# ====================== ENV VARS ======================
try:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH") or ""
    BOT_TOKEN = os.getenv("BOT_TOKEN") or ""

    if not API_ID or not API_HASH or not BOT_TOKEN:
        raise ValueError("Missing API credentials!")
except Exception as e:
    print("CRITICAL ERROR:", e)
    sys.exit(1)

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image
from flask import Flask

import nest_asyncio
nest_asyncio.apply()

app = Client("animebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

process_semaphore = asyncio.Semaphore(2)
user_settings = {}
users_data = {}
active_process = {}

# ====================== UTILS ======================
def progress_bar(percent):
    return "█" * (percent // 5) + "░" * (20 - percent // 5)

def get_duration(file):
    try:
        result = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", file],
                                capture_output=True, text=True)
        return float(json.loads(result.stdout)["format"]["duration"])
    except:
        return 100.0

# ====================== START ======================
@app.on_message(filters.command("start") & filters.private)
async def start(_, message):
    await message.reply("🔥 **HardSub Bot Ready**\n\n1. Video bhejo → /hsub\n2. .ass bhejo → /encode\nPhoto bhejo for watermark")

# ====================== PHOTO ======================
@app.on_message(filters.photo & filters.private)
async def save_photo(_, message):
    user_id = message.from_user.id
    logo = f"downloads/{user_id}_logo.png"
    thumb = f"thumbnails/{user_id}.jpg"

    await message.download(file_name=logo)
    try:
        img = Image.open(logo).convert("RGB")
        img.thumbnail((320, 320))
        img.save(thumb, "JPEG")
    except:
        pass

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("↖️ Top Left", callback_data="wm_topleft"),
         InlineKeyboardButton("↗️ Top Right", callback_data="wm_topright")],
        [InlineKeyboardButton("❌ No Watermark", callback_data="wm_none")]
    ])
    await message.reply("✅ Image Saved!\nWatermark kaha chahiye?", reply_markup=btn)

@app.on_callback_query(filters.regex("^wm_"))
async def wm_callback(_, query):
    pos = "topleft" if query.data == "wm_topleft" else "topright" if query.data == "wm_topright" else "none"
    user_settings[query.from_user.id] = {"wm_pos": pos}
    await query.message.edit(f"✅ {'Top Left' if pos=='topleft' else 'Top Right' if pos=='topright' else 'No Watermark'} Selected")

# ====================== HSUB ======================
@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(_, message):
    if not message.reply_to_message:
        return await message.reply("❌ Video pe reply karke /hsub likho")
    video = message.reply_to_message.video or message.reply_to_message.document
    if not video:
        return await message.reply("❌ Video bhejo")

    user_id = message.from_user.id
    ext = (video.file_name or "video.mp4").split(".")[-1].lower()
    path = f"downloads/{user_id}.{ext}"

    await message.reply_to_message.download(file_name=path)
    users_data[user_id] = {"video": path}
    await message.reply("✅ Video Saved!\nAb .ass file bhejo aur /encode reply karo")

# ====================== ENCODE (FINAL FIXED) ======================
@app.on_message(filters.command("encode") & filters.private)
async def handle_encode(client, message):
    user_id = message.from_user.id

    if not message.reply_to_message or not message.reply_to_message.document or not message.reply_to_message.document.file_name.lower().endswith((".ass",".srt")):
        return await message.reply("❌ .ass file pe reply karke /encode likho")

    if user_id not in users_data or "video" not in users_data[user_id]:
        return await message.reply("❌ Pehle /hsub se video save karo")

    video_file = users_data[user_id]["video"]
    sub_file   = f"downloads/{user_id}.ass"
    logo_file  = f"downloads/{user_id}_logo.png"
    thumb_file = f"thumbnails/{user_id}.jpg"
    output     = f"downloads/{user_id}_out.mp4"

    await message.reply_to_message.download(file_name=sub_file)
    msg = await message.reply("🔥 Starting Encoding...")

    async with process_semaphore:
        duration = get_duration(video_file)
        wm_pos = user_settings.get(user_id, {}).get("wm_pos", "none")

        # === SAFE PATH FOR DOCKER ===
        sub_safe = os.path.basename(sub_file)

        if wm_pos in ["topleft", "topright"] and os.path.exists(logo_file):
            pos = "15:15" if wm_pos == "topleft" else "main_w-overlay_w-15:15"
            cmd = [
                "ffmpeg", "-y", "-i", video_file, "-i", logo_file,
                "-filter_complex", f"[1:v]scale=120:-1[wm];[0:v][wm]overlay={pos}[bg];[bg]ass='{sub_safe}'[out]",
                "-map", "[out]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy", output
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-i", video_file,
                "-vf", f"ass='{sub_safe}'",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy", output
            ]

        print("DEBUG: FFmpeg Command →", " ".join(cmd))
        print("DEBUG: sub_file exists?", os.path.exists(sub_file))

        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        active_process[user_id] = process

        last = -1
        last_time = time.time()

        while True:
            line = await process.stderr.readline()
            if not line: break
            line = line.decode(errors="ignore").strip()

            if "time=" in line:
                try:
                    t = re.search(r"time=(\d+:\d+:\d+\.\d+)", line).group(1)
                    h,m,s = t.split(":")
                    curr = int(h)*3600 + int(m)*60 + float(s)
                    percent = min(int((curr/duration)*100), 100)

                    if percent != last and time.time() - last_time > 3:
                        bar = progress_bar(percent)
                        speed = re.search(r"speed=\s*([\d\.]+)x?", line)
                        sp = speed.group(1)+"x" if speed else "0x"

                        await msg.edit(f"🎬 **Encoding...**\n\n{bar} {percent}%\n⚡ Speed: {sp}")
                        last = percent
                        last_time = time.time()
                except:
                    pass

        rc = await process.wait()
        active_process.pop(user_id, None)

        if rc != 0 or not os.path.exists(output) or os.path.getsize(output) < 1024:
            await msg.edit("❌ Encoding Failed! (Logs dekho)")
            return

        await msg.edit("📤 Uploading...")

        thumb = thumb_file if os.path.exists(thumb_file) else None

        async def up_prog(curr, total):
            p = int(curr/total*100)
            if time.time() - last_time > 3:
                await msg.edit(f"📤 Uploading...\n{progress_bar(p)} {p}%")

        await client.send_video(
            message.chat.id,
            video=output,
            thumb=thumb,
            caption="✅ **HardSub + Watermark Done!**",
            supports_streaming=True,
            progress=up_prog
        )

        await msg.delete()

        # Cleanup
        for f in [video_file, sub_file, output]:
            if os.path.exists(f):
                os.remove(f)
        users_data.pop(user_id, None)

# ====================== FLASK ======================
web_app = Flask(__name__)
@web_app.route("/")
def home(): return "🚀 Bot Running!"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    print("🚀 Starting Bot...")
    app.run()
