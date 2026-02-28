import os
import time
import asyncio
import threading
import sys
import traceback

# Debug prints at the very top to catch issues early
print("DEBUG: bot.py started")
print("DEBUG: Python version:", sys.version)
print("DEBUG: Current directory:", os.getcwd())
print("DEBUG: Files in dir:", os.listdir("."))

# Read env vars with safety
try:
    API_ID_raw = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH") or ""
    BOT_TOKEN = os.getenv("BOT_TOKEN") or ""

    print("DEBUG: API_ID from env:", API_ID_raw)
    print("DEBUG: API_HASH (partial):", API_HASH[:5] + "..." if API_HASH else "MISSING")
    print("DEBUG: BOT_TOKEN (partial):", BOT_TOKEN[:10] + "..." if BOT_TOKEN else "MISSING")

    if not API_ID_raw:
        raise ValueError("API_ID is missing in environment variables!")
    API_ID = int(API_ID_raw)

    if not API_HASH or not BOT_TOKEN:
        raise ValueError("API_HASH or BOT_TOKEN missing!")
except Exception as e:
    print("CRITICAL ERROR in config/env vars:")
    traceback.print_exc()
    sys.exit(1)

print("DEBUG: Credentials read OK")

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image
from flask import Flask

# Fix for event loop in threads (Render + Flask + asyncio)
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

# =========================
# START COMMAND
# =========================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply(
        "🔥 **Anime HardSub & Watermark Bot Ready!**\n\n"
        "**Steps to use:**\n"
        "1️⃣ Forward/Send Video (.mp4 / .mkv)\n"
        "2️⃣ Reply to that video with **/hsub**\n"
        "3️⃣ Forward/Send Subtitle (.ass)\n"
        "4️⃣ Reply to that subtitle with **/encode**\n\n"
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
        img.thumbnail((320, 320))  # EXACT SAME SIZE AS BEFORE
        img.save(thumb_path, "JPEG")
    except Exception as e:
        print(f"Thumbnail resize error: {e}")

    buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("↖️ Top Left", callback_data="wm_topleft"),
            InlineKeyboardButton("↗️ Top Right", callback_data="wm_topright")
        ],
        [InlineKeyboardButton("❌ No Watermark", callback_data="wm_none")]
    ])

    await msg.edit(
        "✅ **Image Saved!**\n\nWhere do you want to place this as a Watermark?",
        reply_markup=buttons
    )

# =========================
# WATERMARK POSITION CALLBACK
# =========================
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
# /HSUB - SAVE VIDEO (FIXED LOGIC)
# =========================
@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(client, message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a Video with **/hsub**")

    # FIX: Check if it's sent as a Video or as a Document (MKV format usually sent as document)
    video = message.reply_to_message.video or message.reply_to_message.document
    if not video:
        return await message.reply("❌ Reply to a valid Video (.mp4, .mkv) with **/hsub**")

    file_name = getattr(video, "file_name", "video.mp4")
    ext = file_name.split(".")[-1].lower() if "." in file_name else "mp4"

    # Block pure documents like .ass or .zip being saved as video
    if ext not in ["mp4", "mkv", "avi", "webm"]:
        return await message.reply(f"❌ This file is .{ext}. Please reply to a Video (.mp4 / .mkv) with **/hsub**")

    user_id = message.from_user.id
    file_path = f"downloads/{user_id}.{ext}"

    msg = await message.reply("⏳ Downloading Video...")
    await message.reply_to_message.download(file_name=file_path)

    await msg.edit("✅ Video Saved!\nNow send **.ass** file and reply to it with **/encode**")

# =========================
# /ENCODE - PROCESS VIDEO + SUB + WATERMARK (FIXED LOGIC)
# =========================
@app.on_message(filters.command("encode") & filters.private)
async def handle_encode(client, message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a **.ass** file with **/encode**")

    doc = message.reply_to_message.document
    video_check = message.reply_to_message.video

    # If user accidentally replies to the Video with /encode instead of the subtitle
    if video_check or (doc and getattr(doc, "file_name", "").lower().endswith((".mp4", ".mkv"))):
        return await message.reply("❌ You replied to a **Video**! Please reply to the **.ass (Subtitle)** file with **/encode**.")

    # Validate the .ass file properly
    if not doc or not getattr(doc, "file_name", None) or not doc.file_name.lower().endswith(".ass"):
        return await message.reply("❌ Only .ass files supported! Make sure you reply to the .ass subtitle document.")

    user_id = message.from_user.id

    video_file = None
    for ext in ["mp4", "mkv", "avi", "webm"]:
        path = f"downloads/{user_id}.{ext}"
        if os.path.exists(path):
            video_file = path
            break

    if not video_file:
        return await message.reply("❌ No video found! Please use **/hsub** on a video first.")

    sub_file = f"downloads/{user_id}.ass"
    logo_file = f"downloads/{user_id}_logo.png"
    thumb_file = f"thumbnails/{user_id}.jpg"
    output_file = f"downloads/{user_id}_out.mp4"

    msg = await message.reply("⏳ Downloading Subtitle...")
    await message.reply_to_message.download(file_name=sub_file)

    await msg.edit("⏳ Processing HardSub & Watermark...")

    async with process_semaphore:
        start_time = time.time()
        is_encoding = True

        async def update_timer():
            while is_encoding:
                elapsed = int(time.time() - start_time)
                try:
                    await msg.edit(f"🎬 Processing...\n⏱ **Time:** {elapsed}s")
                except:
                    pass
                await asyncio.sleep(5)

        timer_task = asyncio.create_task(update_timer())

        try:
            # EXTRA FIX: FFmpeg needs Absolute Path for Subtitles to work properly on Render/Linux
            abs_sub = os.path.abspath(sub_file)
            escaped_sub = abs_sub.replace("\\", "/").replace(":", "\\:")
            
            wm_pos = user_settings.get(user_id, {}).get("wm_pos", "topright")

            if wm_pos in ["topleft", "topright"] and os.path.exists(logo_file):
                # WATERMARK SCALE IS EXACTLY SAME
                overlay_coords = "15:15" if wm_pos == "topleft" else "main_w-overlay_w-15:15"
                cmd = (
                    f'ffmpeg -y -i "{video_file}" -i "{logo_file}" '
                    f'-filter_complex "[1:v]scale=120:-1[wm];[0:v][wm]overlay={overlay_coords}[bg];'
                    f'[bg]ass=\'{escaped_sub}\'[out]" '
                    f'-map "[out]" -map 0:a '
                    f'-c:v libx264 -preset ultrafast -c:a copy "{output_file}"'
                )
            else:
                cmd = (
                    f'ffmpeg -y -i "{video_file}" '
                    f'-vf "ass=\'{escaped_sub}\'" '
                    f'-c:v libx264 -preset ultrafast '
                    f'-c:a copy "{output_file}"'
                )

            process = await asyncio.create_subprocess_shell(cmd)
            await process.communicate()

            is_encoding = False
            timer_task.cancel()

            if not os.path.exists(output_file):
                return await msg.edit("❌ Encoding Failed! Please make sure FFmpeg is properly installed.")

            await msg.edit("📤 Uploading Processed Video...")

            thumb_path = thumb_file if os.path.exists(thumb_file) else None

            await client.send_video(
                message.chat.id,
                video=output_file,
                thumb=thumb_path,
                caption="✅ HardSub & Watermark Done!",
                supports_streaming=True
            )

            await msg.delete()

        except Exception as e:
            is_encoding = False
            timer_task.cancel()
            await msg.edit(f"❌ Error: {str(e)}")
        finally:
            # Cleanup files
            for file in [video_file, sub_file, output_file]:
                if file and os.path.exists(file):
                    try:
                        os.remove(file)
                    except:
                        pass

# =========================
# DUMMY FLASK SERVER FOR RENDER KEEP-ALIVE
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
    app.run()  # This handles the asyncio loop internally
