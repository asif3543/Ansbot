from pyrogram import Client, filters
import os
import asyncio

# =========================
# CONFIG
# =========================
API_ID = 123456  # apna api_id daalo
API_HASH = "YOUR_API_HASH"
BOT_TOKEN = "YOUR_BOT_TOKEN"

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

processing_lock = asyncio.Lock()
waiting_thumbnail = {}

# =========================
# VIDEO RECEIVE
# =========================
@app.on_message(filters.video)
async def video_handler(client, message):
    user_id = message.from_user.id
    await message.reply("✅ Video Received\nNow send Subtitle (.ass)")
    await message.download(file_name=f"downloads/{user_id}.mp4")


# =========================
# SUBTITLE RECEIVE
# =========================
@app.on_message(filters.document)
async def sub_handler(client, message):

    if not message.document.file_name.endswith(".ass"):
        return

    user_id = message.from_user.id

    await message.reply("✅ Subtitle Received\nSend /bakk to start processing 🎬")

    await message.download(file_name=f"downloads/{user_id}.ass")


# =========================
# THUMBNAIL COMMAND
# =========================
@app.on_message(filters.command("thumbnail"))
async def ask_thumbnail(client, message):
    user_id = message.from_user.id
    waiting_thumbnail[user_id] = True
    await message.reply("📸 Send the photo for Thumbnail")


# =========================
# THUMBNAIL RECEIVE
# =========================
@app.on_message(filters.photo)
async def save_thumbnail(client, message):
    user_id = message.from_user.id

    if waiting_thumbnail.get(user_id):
        await message.download(file_name=f"thumbnails/{user_id}.jpg")
        waiting_thumbnail[user_id] = False
        await message.reply("✅ Thumbnail Saved Successfully")


# =========================
# REMOVE THUMBNAIL
# =========================
@app.on_message(filters.command("remove_thumbnail"))
async def remove_thumbnail(client, message):
    user_id = message.from_user.id
    thumb_file = f"thumbnails/{user_id}.jpg"

    if os.path.exists(thumb_file):
        os.remove(thumb_file)
        await message.reply("🗑 Thumbnail Removed")
    else:
        await message.reply("❌ No Thumbnail Found")


# =========================
# HARD SUB PROCESSING
# =========================
@app.on_message(filters.command("bakk"))
async def process_video(client, message):

    user_id = message.from_user.id

    video_file = f"downloads/{user_id}.mp4"
    sub_file = f"downloads/{user_id}.ass"
    thumb_file = f"thumbnails/{user_id}.jpg"
    output_file = f"downloads/{user_id}_out.mp4"

    if not os.path.exists(video_file):
        return await message.reply("❌ Send Video First")

    if not os.path.exists(sub_file):
        return await message.reply("❌ Send Subtitle First")

    async with processing_lock:
        await message.reply("🎬 Processing... Please Wait")

        if os.path.exists(thumb_file):
            cmd = f'ffmpeg -y -i "{video_file}" -i "{thumb_file}" -filter_complex "[0:v][1:v] overlay=W-w-10:10" -vf "ass={sub_file}" -preset ultrafast "{output_file}"'
        else:
            cmd = f'ffmpeg -y -i "{video_file}" -vf "ass={sub_file}" -preset ultrafast "{output_file}"'

        os.system(cmd)

        await client.send_video(
            message.chat.id,
            output_file
        )

        await message.reply("✅ HardSub Video Ready")

        # Optional Cleanup
        # os.remove(video_file)
        # os.remove(sub_file)
        # os.remove(output_file)


# =========================
# START BOT
# =========================
app.run()
