from pyrogram import Client, filters
import os

BOT_TOKEN = "YOUR_BOT_TOKEN"

app = Client(
    "animebot",
    bot_token=BOT_TOKEN
)

# Ensure folders exist
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

# =========================
# Video Receive
# =========================
@app.on_message(filters.video)
async def video_handler(client, message):

    user_id = message.from_user.id

    video_path = await message.download(
        file_name=f"downloads/{user_id}.mp4"
    )

    await message.reply("✅ Video Saved\nSend Subtitle (.ass)")

# =========================
# Subtitle + HardSub Processing
# =========================
@app.on_message(filters.document)
async def sub_handler(client, message):

    if not message.document.file_name.endswith(".ass"):
        return

    user_id = message.from_user.id

    sub_path = await message.download(
        file_name=f"downloads/{user_id}.ass"
    )

    await message.reply("✅ Subtitle Received\nProcessing HardSub...")

    # FFmpeg HardSub Processing
    os.system(f"""
    ffmpeg -y -i downloads/{user_id}.mp4
    -vf "ass=downloads/{user_id}.ass"
    -preset ultrafast
    downloads/{user_id}_out.mp4
    """)

    # Send Final Video
    if os.path.exists(f"downloads/{user_id}_out.mp4"):

        await app.send_video(
            message.chat.id,
            f"downloads/{user_id}_out.mp4"
        )

        await message.reply("✅ HardSub Video Ready")

app.run()
