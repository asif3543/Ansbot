import os
import time
import asyncio
import threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image
from flask import Flask
from config import API_ID, API_HASH, BOT_TOKEN

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
# /START COMMAND
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
# WATERMARK & THUMBNAIL (PHOTO RECEIVE)
# =========================
@app.on_message(filters.photo & filters.private)
async def save_photo(client, message):
    user_id = message.from_user.id
    msg = await message.reply("⏳ Processing Logo & Thumbnail...")
    
    logo_path = f"downloads/{user_id}_logo.png"
    thumb_path = f"thumbnails/{user_id}.jpg"
    
    await message.download(file_name=logo_path)
    
    try:
        img = Image.open(logo_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.thumbnail((320, 320))
        img.save(thumb_path, "JPEG")
    except Exception as e:
        print(f"Thumbnail resize error: {e}")

    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("↖️ Top Left", callback_data="wm_topleft"),
         InlineKeyboardButton("↗️ Top Right", callback_data="wm_topright")],[InlineKeyboardButton("❌ No Watermark (Cover Only)", callback_data="wm_none")]
    ])
    
    await msg.edit(
        "✅ **Image Saved!**\n\n"
        "Where do you want to place this as a Watermark on the video?",
        reply_markup=buttons
    )

# =========================
# BUTTON CLICK HANDLER
# =========================
@app.on_callback_query(filters.regex("^wm_"))
async def wm_callback(client, callback_query):
    user_id = callback_query.from_user.id
    choice = callback_query.data
    
    if user_id not in user_settings:
        user_settings[user_id] = {}
        
    if choice == "wm_topleft":
        user_settings[user_id]["wm_pos"] = "topleft"
        await callback_query.message.edit("✅ Watermark Position Set: **Top Left ↖️**")
    elif choice == "wm_topright":
        user_settings[user_id]["wm_pos"] = "topright"
        await callback_query.message.edit("✅ Watermark Position Set: **Top Right ↗️**")
    else:
        user_settings[user_id]["wm_pos"] = "none"
        await callback_query.message.edit("✅ Watermark Disabled.\n(Image will only be used as Cover Thumbnail)")

# =========================
# /HSUB - VIDEO RECEIVE
# =========================
@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(client, message):
    if not message.reply_to_message or not message.reply_to_message.video:
        return await message.reply("❌ Please reply to a Video with **/hsub**")

    user_id = message.from_user.id
    video = message.reply_to_message.video

    file_name = video.file_name or "video.mp4"
    ext = file_name.split(".")[-1] if "." in file_name else "mp4"
    file_path = f"downloads/{user_id}.{ext}"

    msg = await message.reply("⏳ Downloading Video...")
    await message.reply_to_message.download(file_name=file_path)
    
    await msg.edit("✅ Success\n\n📁 Now send the **.ass** file and reply to it with **/encode**")

# =========================
# /ENCODE - SUBTITLE & PROCESS
# =========================
@app.on_message(filters.command("encode") & filters.private)
async def handle_encode(client, message):
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("❌ Please reply to an **.ass** Document with **/encode**")

    doc = message.reply_to_message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".ass"):
        return await message.reply("❌ This is not a valid .ass subtitle file")

    user_id = message.from_user.id

    video_file = None
    for ext in["mp4", "mkv"]:
        path = f"downloads/{user_id}.{ext}"
        if os.path.exists(path):
            video_file = path
            break

    if not video_file:
        return await message.reply("❌ No video found! Please reply to a video with /hsub first.")

    sub_file = f"downloads/{user_id}.ass"
    logo_file = f"downloads/{user_id}_logo.png"
    thumb_file = f"thumbnails/{user_id}.jpg"
    output_file = f"downloads/{user_id}_out.mp4"

    msg = await message.reply("⏳ Downloading Subtitle...")
    await message.reply_to_message.download(file_name=sub_file)

    await msg.edit("✅ Success\n\n⏳ Added to queue...")

    async with process_semaphore:
        start_time = time.time()
        is_encoding = True

        async def update_timer():
            while is_encoding:
                elapsed = int(time.time() - start_time)
                try:
                    await msg.edit(f"🎬 Processing HardSub & Logo...\n⏱ **Timer:** {elapsed} seconds")
                except:
                    pass
                await asyncio.sleep(5)

        timer_task = asyncio.create_task(update_timer())

        try:
            escaped_sub = sub_file.replace("\\", "/").replace(":", "\\:")
            wm_pos = user_settings.get(user_id, {}).get("wm_pos", "topright") 
            
            if wm_pos in ["topleft", "topright"] and os.path.exists(logo_file):
                overlay_coords = "15:15" if wm_pos == "topleft" else "main_w-overlay_w-15:15"
                cmd = (
                    f'ffmpeg -y -i "{video_file}" -i "{logo_file}" '
                    f'-filter_complex "[1:v]scale=120:-1[wm];[0:v][wm]overlay={overlay_coords}[bg];[bg]ass=\'{escaped_sub}\'[out]" '
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

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            is_encoding = False 
            timer_task.cancel()

            if not os.path.exists(output_file):
                return await msg.edit("❌ HardSub Failed")

            await msg.edit("📤 Uploading Video...")
            thumb_path = thumb_file if os.path.exists(thumb_file) else None

            await client.send_video(
                chat_id=message.chat.id,
                video=output_file,
                thumb=thumb_path,
                caption="✅ HardSub & Logo Completed Automatically!",
                supports_streaming=True
            )
            await msg.delete()

        except Exception as e:
            is_encoding = False
            timer_task.cancel()
            await msg.edit(f"❌ Error during processing:\n{str(e)}")
        finally:
            for file in [video_file, sub_file, output_file]:
                if file and os.path.exists(file):
                    os.remove(file)

# =========================
# DUMMY WEB SERVER FOR RENDER
# =========================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🚀 Anime HardSub Bot is Running Perfectly!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# =========================
# RUN BOT
# =========================
if __name__ == "__main__":
    print("🌐 Starting Dummy Web Server for Render...")
    threading.Thread(target=run_server, daemon=True).start()
    
    print("🚀 Anime HardSub Bot is Starting...")
    app.run()
