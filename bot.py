import os
import time
import asyncio
import threading
import sys
import traceback

print("🚀 Bot Starting...")

# =========================
# ENV SAFE LOAD
# =========================
API_ID_raw = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not API_ID_raw or not API_HASH or not BOT_TOKEN:
    print("❌ Missing Environment Variables")
    sys.exit(1)

API_ID = int(API_ID_raw)

# =========================
# IMPORTS
# =========================
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image
from flask import Flask
import nest_asyncio

nest_asyncio.apply()

# =========================
# BOT INIT
# =========================
app = Client(
    "animebot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# =========================
# FOLDERS
# =========================
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

# Queue + Semaphore
process_semaphore = asyncio.Semaphore(1)

# User settings cache
user_settings = {}

# =========================
# START
# =========================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply(
        "🔥 Anime HardSub Bot Ready!\n\n"
        "Send Video → Reply /hsub\n"
        "Send Subtitle → Reply /encode\n"
        "Send Photo → Set Thumbnail + Watermark"
    )

# =========================
# PHOTO
# =========================
@app.on_message(filters.photo & filters.private)
async def save_photo(client, message):
    user_id = message.from_user.id

    msg = await message.reply("⏳ Saving Image...")

    logo_path = f"downloads/{user_id}_logo.png"
    thumb_path = f"thumbnails/{user_id}.jpg"

    await message.download(file_name=logo_path)

    try:
        img = Image.open(logo_path)
        if img.mode != "RGB":
            img = img.convert("RGB")

        img.thumbnail((320,320))
        img.save(thumb_path,"JPEG")

    except:
        pass

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("↖️ Top Left", callback_data="wm_topleft"),
            InlineKeyboardButton("↗️ Top Right", callback_data="wm_topright")
        ],
        [InlineKeyboardButton("❌ No Watermark", callback_data="wm_none")]
    ])

    await msg.edit("✅ Image Saved!\nSelect Watermark Position", reply_markup=buttons)

# =========================
# CALLBACK
# =========================
@app.on_callback_query(filters.regex("^wm_"))
async def wm_callback(client, callback):
    user_id = callback.from_user.id
    choice = callback.data

    if user_id not in user_settings:
        user_settings[user_id] = {}

    if choice == "wm_topleft":
        user_settings[user_id]["wm_pos"] = "topleft"
        txt = "Top Left Selected"

    elif choice == "wm_topright":
        user_settings[user_id]["wm_pos"] = "topright"
        txt = "Top Right Selected"

    else:
        user_settings[user_id]["wm_pos"] = "none"
        txt = "Watermark Disabled"

    await callback.message.edit("✅ "+txt)

# =========================
# HSUB
# =========================
@app.on_message(filters.command("hsub") & filters.private)
async def hsub(client, message):

    if not message.reply_to_message:
        return await message.reply("❌ Reply to Video with /hsub")

    video = message.reply_to_message.video or message.reply_to_message.document

    if not video:
        return await message.reply("❌ Invalid Video")

    user_id = message.from_user.id

    ext = "mp4"
    if video.file_name and "." in video.file_name:
        ext = video.file_name.split(".")[-1]

    file_path = f"downloads/{user_id}.{ext}"

    msg = await message.reply("⏳ Downloading Video...")
    await message.reply_to_message.download(file_name=file_path)

    await msg.edit("✅ Video Saved\nNow send .ass and reply /encode")

# =========================
# ENCODE
# =========================
@app.on_message(filters.command("encode") & filters.private)
async def encode(client, message):

    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("❌ Reply to .ass file")

    doc = message.reply_to_message.document

    if not doc.file_name.lower().endswith(".ass"):
        return await message.reply("❌ Only .ass supported")

    user_id = message.from_user.id

    video_file=None
    for ext in ["mp4","mkv","avi","webm"]:
        path=f"downloads/{user_id}.{ext}"
        if os.path.exists(path):
            video_file=path
            break

    if not video_file:
        return await message.reply("❌ No video found")

    sub_file=f"downloads/{user_id}.ass"
    logo_file=f"downloads/{user_id}_logo.png"
    thumb_file=f"thumbnails/{user_id}.jpg"
    output_file=f"downloads/{user_id}_out.mp4"

    msg=await message.reply("⏳ Downloading Subtitle...")
    await message.reply_to_message.download(file_name=sub_file)

    await msg.edit("⏳ Processing...")

    async with process_semaphore:

        try:
            abs_sub=os.path.abspath(sub_file)
            escaped_sub=abs_sub.replace("\\","/").replace(":","\\:")

            wm_pos=user_settings.get(user_id,{}).get("wm_pos","topright")

            if wm_pos in ["topleft","topright"] and os.path.exists(logo_file):

                overlay="15:15" if wm_pos=="topleft" else "main_w-overlay_w-15:15"

                cmd=f'''
ffmpeg -y -i "{video_file}" -i "{logo_file}"
-filter_complex "[1:v]scale=120:-1[wm];[0:v][wm]overlay={overlay}[bg];[bg]ass='{escaped_sub}'[out]"
-map "[out]" -map 0:a
-c:v libx264 -preset veryfast -c:a copy "{output_file}"
'''

            else:
                cmd=f'''
ffmpeg -y -i "{video_file}"
-vf "ass='{escaped_sub}'"
-c:v libx264 -preset veryfast
-c:a copy "{output_file}"
'''

            process=await asyncio.create_subprocess_shell(cmd)
            await process.communicate()

            if not os.path.exists(output_file):
                return await msg.edit("❌ Encoding Failed")

            await msg.edit("📤 Uploading...")

            thumb=thumb_file if os.path.exists(thumb_file) else None

            await client.send_video(
                message.chat.id,
                video=output_file,
                thumb=thumb,
                caption="✅ HardSub Done!",
                supports_streaming=True
            )

            await msg.delete()

        except Exception as e:
            await msg.edit(str(e))

        finally:
            for f in [video_file,sub_file,output_file]:
                if f and os.path.exists(f):
                    try: os.remove(f)
                    except: pass

# =========================
# CLEANUP BACKGROUND
# =========================
async def auto_cleanup():
    while True:
        try:
            for folder in ["downloads","thumbnails"]:
                if os.path.exists(folder):
                    for file in os.listdir(folder):
                        path=os.path.join(folder,file)
                        if time.time()-os.path.getmtime(path)>300:
                            os.remove(path)
        except:
            pass

        await asyncio.sleep(120)

@app.on_startup
async def startup(client):
    asyncio.create_task(auto_cleanup())

# =========================
# RUN
# =========================
if __name__=="__main__":
    print("🚀 Bot Running...")
    app.run()
