from pyrogram import Client, filters
import os

BOT_TOKEN = "YOUR_BOT_TOKEN"

app = Client(
    "animebot",
    bot_token=BOT_TOKEN
)

# Create folders
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

# =========================
# Video Receive
# =========================
@app.on_message(filters.video)
async def video_handler(client, message):

    user_id = message.from_user.id

    await message.reply("✅ Video Received\nSend Subtitle (.ass)")

    await message.download(
        file_name=f"downloads/{user_id}.mp4"
    )

# =========================
# Subtitle Receive
# =========================
@app.on_message(filters.document)
async def sub_handler(client, message):

    if not message.document.file_name.endswith(".ass"):
        return

    user_id = message.from_user.id

    await message.reply("✅ Subtitle Received")

    await message.download(
        file_name=f"downloads/{user_id}.ass"
    )

    await message.reply("Now Send /bakk to Process Video 🎬")

# =========================
# Thumbnail Receive
# =========================
@app.on_message(filters.photo & filters.command("thumbnail"))
async def thumbnail_handler(client, message):

    user_id = message.from_user.id

    await message.download(
        file_name=f"thumbnails/{user_id}.jpg"
    )

    await message.reply("✅ Thumbnail Saved")

# =========================
# HardSub Processing
# =========================
@app.on_message(filters.command("bakk"))
async def bakk(client, message):

    user_id = message.from_user.id

    video_file = f"downloads/{user_id}.mp4"
    sub_file = f"downloads/{user_id}.ass"
    thumb_file = f"thumbnails/{user_id}.jpg"

    if not os.path.exists(video_file):
        return await message.reply("❌ Send Video First")

    if not os.path.exists(sub_file):
        return await message.reply("❌ Send Subtitle First")

    await message.reply("🎬 Processing HardSub Video...")

    # FFmpeg Processing
    if os.path.exists(thumb_file):

        os.system(f"""
        ffmpeg -y -i {video_file}
        -i {thumb_file}
        -filter_complex "[0:v][1:v] overlay=W-w-10:10"
        -vf "ass={sub_file}"
        -preset ultrafast
        downloads/{user_id}_out.mp4
        """)

    else:

        os.system(f"""
        ffmpeg -y -i {video_file}
        -vf "ass={sub_file}"
        -preset ultrafast
        downloads/{user_id}_out.mp4
        """)

    # Send Final Video
    await app.send_video(
        message.chat.id,
        f"downloads/{user_id}_out.mp4"
    )

    await message.reply("✅ HardSub Video Ready")

# Start Bot
app.run()
