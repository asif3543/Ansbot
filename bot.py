import os
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image
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
# FOLDERS
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
        "🔥 Anime HardSub Bot Ready!\n\n"
        "Send Video → Reply /hsub\n"
        "Send Subtitle → Reply /encode\n\n"
        "Send Photo = Watermark + Thumbnail"
    )

# =========================
# PHOTO → WATERMARK + THUMBNAIL
# =========================
@app.on_message(filters.photo & filters.private)
async def save_photo(client, message):

    user_id = message.from_user.id
    msg = await message.reply("⏳ Processing Image...")

    logo_path = f"downloads/{user_id}_logo.png"
    thumb_path = f"thumbnails/{user_id}.jpg"

    await message.download(file_name=logo_path)

    try:
        img = Image.open(logo_path)
        if img.mode != "RGB":
            img = img.convert("RGB")

        img.thumbnail((320, 320))
        img.save(thumb_path, "JPEG")

    except Exception as e:
        print(e)

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("↖️ Top Left", callback_data="wm_topleft"),
         InlineKeyboardButton("↗️ Top Right", callback_data="wm_topright")],
        [InlineKeyboardButton("❌ No Watermark", callback_data="wm_none")]
    ])

    await msg.edit("✅ Image Saved\nSelect Watermark Position:", reply_markup=buttons)

# =========================
# WATERMARK POSITION
# =========================
@app.on_callback_query(filters.regex("wm_"))
async def wm_callback(client, callback_query):

    user_id = callback_query.from_user.id
    choice = callback_query.data

    if user_id not in user_settings:
        user_settings[user_id] = {}

    if choice == "wm_topleft":
        user_settings[user_id]["wm_pos"] = "topleft"
        await callback_query.message.edit("✅ Watermark → Top Left")
    elif choice == "wm_topright":
        user_settings[user_id]["wm_pos"] = "topright"
        await callback_query.message.edit("✅ Watermark → Top Right")
    else:
        user_settings[user_id]["wm_pos"] = "none"
        await callback_query.message.edit("✅ Watermark Disabled")

# =========================
# VIDEO RECEIVE
# =========================
@app.on_message(filters.command("hsub") & filters.private)
async def handle_hsub(client, message):

    if not message.reply_to_message or not message.reply_to_message.video:
        return await message.reply("❌ Reply to video with /hsub")

    user_id = message.from_user.id
    video = message.reply_to_message.video

    file_name = video.file_name or "video.mp4"
    ext = file_name.split(".")[-1]

    file_path = f"downloads/{user_id}.{ext}"

    msg = await message.reply("⏳ Downloading Video...")

    await message.reply_to_message.download(file_name=file_path)

    await msg.edit("✅ Video Saved\nNow send subtitle and reply with /encode")

# =========================
# ENCODE PROCESS
# =========================
@app.on_message(filters.command("encode") & filters.private)
async def handle_encode(client, message):

    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("❌ Reply to .ass subtitle with /encode")

    if not message.reply_to_message.document.file_name.lower().endswith(".ass"):
        return await message.reply("❌ Only .ass subtitle allowed")

    user_id = message.from_user.id

    # Video check
    video_file = None
    for ext in ["mp4", "mkv"]:
        path = f"downloads/{user_id}.{ext}"
        if os.path.exists(path):
            video_file = path
            break

    if not video_file:
        return await message.reply("❌ Video not found")

    # Size protection
    if os.path.getsize(video_file) > 800 * 1024 * 1024:
        return await message.reply("❌ Max 800MB video allowed")

    sub_file = f"downloads/{user_id}.ass"
    logo_file = f"downloads/{user_id}_logo.png"
    thumb_file = f"thumbnails/{user_id}.jpg"
    output_file = f"downloads/{user_id}_out.mp4"

    msg = await message.reply("⏳ Downloading Subtitle...")
    await message.reply_to_message.download(file_name=sub_file)

    await msg.edit("⏳ Processing Queue...")

    async with process_semaphore:

        start_time = time.time()
        is_encoding = True

        async def timer():
            while is_encoding:
                try:
                    await msg.edit(
                        f"🎬 Encoding...\n⏱ {int(time.time()-start_time)} sec"
                    )
                except:
                    pass
                await asyncio.sleep(5)

        timer_task = asyncio.create_task(timer())

        try:

            escaped_sub = sub_file.replace("\\", "/").replace(":", "\\:")
            wm_pos = user_settings.get(user_id, {}).get("wm_pos", "topright")

            if wm_pos in ["topleft", "topright"] and os.path.exists(logo_file):

                overlay_coords = "15:15" if wm_pos == "topleft" else "main_w-overlay_w-15:15"

                cmd = (
                    f'ffmpeg -y -i "{video_file}" -i "{logo_file}" '
                    f'-filter_complex "[1:v]scale=120:-1[wm];'
                    f'[0:v][wm]overlay={overlay_coords},ass=\'{escaped_sub}\'" '
                    f'-c:v libx264 -preset ultrafast '
                    f'-c:a copy "{output_file}"'
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
                return await msg.edit("❌ Encoding Failed")

            await msg.edit("📤 Uploading Video...")

            thumb_path = thumb_file if os.path.exists(thumb_file) else None

            await client.send_video(
                message.chat.id,
                output_file,
                thumb=thumb_path,
                caption="✅ HardSub Completed"
            )

            await msg.delete()

        except Exception as e:
            is_encoding = False
            timer_task.cancel()
            await msg.edit(f"❌ Error:\n{e}")

        finally:
            for file in [video_file, sub_file, output_file]:
                if file and os.path.exists(file):
                    os.remove(file)

# =========================
# RUN BOT
# =========================
if __name__ == "__main__":
    print("Bot Running...")
    app.run()
