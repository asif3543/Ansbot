import os
import time
import asyncio
import threading
import sys
import traceback

print("🚀 Bot Starting...")

# =============================
# ENV CONFIG SAFE READ
# =============================
try:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    if not API_HASH or not BOT_TOKEN:
        raise Exception("Missing credentials")

except Exception:
    traceback.print_exc()
    exit(1)

# =============================
# IMPORTS
# =============================
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image
from flask import Flask
import nest_asyncio

nest_asyncio.apply()

# =============================
# BOT INIT
# =============================
app = Client(
    "animebot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# =============================
# FOLDERS
# =============================
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

process_semaphore = asyncio.Semaphore(2)
user_settings = {}

# =============================
# START
# =============================
@app.on_message(filters.command("start") & filters.private)
async def start(_, message):
    await message.reply(
        "🔥 Anime HardSub Bot Ready!\n\n"
        "Send Video → Reply /hsub\n"
        "Send Subtitle → Reply /encode\n"
        "Send Photo → Set Thumbnail + Watermark"
    )

# =============================
# PHOTO
# =============================
@app.on_message(filters.photo & filters.private)
async def save_photo(_, message):

    user_id = message.from_user.id

    logo_path = f"downloads/{user_id}_logo.png"
    thumb_path = f"thumbnails/{user_id}.jpg"

    msg = await message.reply("⏳ Saving Image...")

    await message.download(logo_path)

    try:
        img = Image.open(logo_path)
        img.thumbnail((320, 320))
        img.save(thumb_path, "JPEG")
    except:
        pass

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("↖️ Left", callback_data="wm_topleft"),
            InlineKeyboardButton("↗️ Right", callback_data="wm_topright")
        ],
        [InlineKeyboardButton("❌ No Watermark", callback_data="wm_none")]
    ])

    await msg.edit("✅ Image Saved", reply_markup=buttons)

# =============================
# WATERMARK CALLBACK
# =============================
@app.on_callback_query(filters.regex("wm_"))
async def wm_callback(_, query):

    uid = query.from_user.id

    if uid not in user_settings:
        user_settings[uid] = {}

    if query.data == "wm_topleft":
        user_settings[uid]["wm_pos"] = "topleft"
        txt = "Top Left Selected"

    elif query.data == "wm_topright":
        user_settings[uid]["wm_pos"] = "topright"
        txt = "Top Right Selected"

    else:
        user_settings[uid]["wm_pos"] = "none"
        txt = "Watermark Disabled"

    await query.message.edit("✅ " + txt)

# =============================
# HSUB
# =============================
@app.on_message(filters.command("hsub") & filters.private)
async def hsub(_, message):

    if not message.reply_to_message:
        return await message.reply("❌ Reply to Video")

    video = message.reply_to_message.video or message.reply_to_message.document

    if not video:
        return await message.reply("❌ Invalid Video")

    user_id = message.from_user.id

    ext = "mp4"
    path = f"downloads/{user_id}.{ext}"

    msg = await message.reply("⏳ Downloading Video...")
    await message.reply_to_message.download(path)

    await msg.edit("✅ Video Saved\nNow send .ass subtitle")

# =============================
# ENCODE
# =============================
@app.on_message(filters.command("encode") & filters.private)
async def encode(_, message):

    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("❌ Reply .ass file")

    doc = message.reply_to_message.document

    if not doc.file_name.lower().endswith(".ass"):
        return await message.reply("❌ Only .ass")

    user_id = message.from_user.id

    video_file = None
    for ext in ["mp4","mkv","avi","webm"]:
        p = f"downloads/{user_id}.{ext}"
        if os.path.exists(p):
            video_file = p
            break

    if not video_file:
        return await message.reply("❌ Video not found")

    sub_file = f"downloads/{user_id}.ass"
    logo_file = f"downloads/{user_id}_logo.png"
    thumb_file = f"thumbnails/{user_id}.jpg"
    output_file = f"downloads/{user_id}_out.mp4"

    await message.reply("⏳ Processing...")

    await message.reply_to_message.download(sub_file)

    async with process_semaphore:

        wm_pos = user_settings.get(user_id, {}).get("wm_pos","topright")

        abs_sub = os.path.abspath(sub_file).replace("\\","/")

        escaped_sub = abs_sub.replace(":", "\\:")

        if wm_pos in ["topleft","topright"] and os.path.exists(logo_file):

            overlay_coords = "15:15" if wm_pos=="topleft" else "main_w-overlay_w-15:15"

            cmd = (
                f'ffmpeg -y -i "{video_file}" -i "{logo_file}" '
                f'-filter_complex "[1:v]scale=120:-1[wm];'
                f'[0:v][wm]overlay={overlay_coords}[bg];'
                f'[bg]ass=\'{escaped_sub}\'[out]" '
                f'-map "[out]" -map 0:a '
                f'-c:v libx264 -preset ultrafast -threads 2 -crf 28 '
                f'-c:a copy "{output_file}"'
            )

        else:

            cmd = (
                f'ffmpeg -y -i "{video_file}" '
                f'-vf "ass=\'{escaped_sub}\'" '
                f'-c:v libx264 -preset ultrafast -threads 2 -crf 28 '
                f'-c:a copy "{output_file}"'
            )

        process = await asyncio.create_subprocess_shell(cmd)
        await process.communicate()

        if os.path.exists(output_file):

            await message.reply("📤 Uploading...")

            await message.reply_video(
                output_file,
                thumb=thumb_file if os.path.exists(thumb_file) else None,
                caption="✅ Done"
            )

# =============================
# RUN
# =============================
if __name__ == "__main__":
    app.run()
