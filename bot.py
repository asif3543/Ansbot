import os
import asyncio
from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN

# =========================
# INIT
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

# Max 2 videos at same time
process_semaphore = asyncio.Semaphore(2)
waiting_thumbnail = {}

# =========================
# START
# =========================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply(
        "🔥 **Anime HardSub Bot Ready!**\n\n"
        "1️⃣ Send Video (.mp4 / .mkv)\n"
        "2️⃣ Send Subtitle (.ass)\n"
        "3️⃣ Use /bakk to Process\n\n"
        "Thumbnail: /thumbnail"
    )

# =========================
# VIDEO RECEIVE
# =========================
@app.on_message(filters.video & filters.private)
async def video_handler(client, message):
    user_id = message.from_user.id

    file_name = message.video.file_name or "video.mp4"
    ext = file_name.split(".")[-1] if "." in file_name else "mp4"

    file_path = f"downloads/{user_id}.{ext}"

    msg = await message.reply("⏳ Downloading Video...")
    await message.download(file_name=file_path)
    await msg.edit("✅ Video Received\nNow send Subtitle (.ass)")

# =========================
# SUBTITLE RECEIVE
# =========================
@app.on_message(filters.document & filters.private)
async def subtitle_handler(client, message):
    file_name = message.document.file_name

    if not file_name or not file_name.lower().endswith(".ass"):
        return await message.reply("❌ Please send a valid .ass subtitle file")

    user_id = message.from_user.id
    file_path = f"downloads/{user_id}.ass"

    msg = await message.reply("⏳ Downloading Subtitle...")
    await message.download(file_name=file_path)
    await msg.edit("✅ Subtitle Received\nSend /bakk to start processing 🎬")

# =========================
# THUMBNAIL COMMAND
# =========================
@app.on_message(filters.command("thumbnail") & filters.private)
async def ask_thumbnail(client, message):
    waiting_thumbnail[message.from_user.id] = True
    await message.reply("📸 Send Photo to set as Thumbnail")

@app.on_message(filters.photo & filters.private)
async def save_thumbnail(client, message):
    user_id = message.from_user.id

    if waiting_thumbnail.get(user_id):
        thumb_path = f"thumbnails/{user_id}.jpg"
        msg = await message.reply("⏳ Saving Thumbnail...")
        await message.download(file_name=thumb_path)
        waiting_thumbnail[user_id] = False
        await msg.edit("✅ Thumbnail Saved")

@app.on_message(filters.command("remove_thumbnail") & filters.private)
async def remove_thumbnail(client, message):
    user_id = message.from_user.id
    thumb_file = f"thumbnails/{user_id}.jpg"

    if os.path.exists(thumb_file):
        os.remove(thumb_file)
        await message.reply("🗑 Thumbnail Removed")
    else:
        await message.reply("❌ No Thumbnail Found")

# =========================
# HARD SUB PROCESS
# =========================
@app.on_message(filters.command("bakk") & filters.private)
async def process_video(client, message):

    user_id = message.from_user.id

    # Detect video file
    video_file = None
    for ext in ["mp4", "mkv"]:
        path = f"downloads/{user_id}.{ext}"
        if os.path.exists(path):
            video_file = path
            break

    sub_file = f"downloads/{user_id}.ass"
    thumb_file = f"thumbnails/{user_id}.jpg"
    output_file = f"downloads/{user_id}_out.mp4"

    if not video_file:
        return await message.reply("❌ Send Video First")

    if not os.path.exists(sub_file):
        return await message.reply("❌ Send Subtitle First")

    msg = await message.reply("⏳ Added to queue...")

    async with process_semaphore:
        await msg.edit("🎬 Processing HardSub...\nPlease wait")

        try:
            escaped_sub = sub_file.replace("\\", "/").replace(":", "\\:")

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

            if not os.path.exists(output_file):
                return await msg.edit("❌ HardSub Failed")

            await msg.edit("📤 Uploading Video...")

            thumb_path = thumb_file if os.path.exists(thumb_file) else None

            await client.send_video(
                chat_id=message.chat.id,
                video=output_file,
                thumb=thumb_path,
                caption="✅ HardSub Completed",
                supports_streaming=True
            )

            await msg.delete()

        except Exception as e:
            await msg.edit(f"❌ Error:\n{str(e)}")

        finally:
            # Cleanup
            for file in [video_file, sub_file, output_file]:
                if file and os.path.exists(file):
                    os.remove(file)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    print("Bot is Running...")
    app.run()
