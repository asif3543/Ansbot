from pyrogram import Client, filters

from config import BOT_TOKEN

app = Client(
    "animebot",
    bot_token=BOT_TOKEN
)

# Video Receive
@app.on_message(filters.video)
async def video_handler(client, message):

    user_id = message.from_user.id

    await message.download(
        file_name=f"/tmp/{user_id}.mp4"
    )

    await message.reply("✅ Video received\nSend subtitle (.ass)")

# Subtitle Receive
@app.on_message(filters.document)
async def sub_handler(client, message):

    if message.document.file_name.endswith(".ass"):

        user_id = message.from_user.id

        await message.download(
            file_name=f"/tmp/{user_id}.ass"
        )

        await message.reply("✅ Subtitle received\nProcessing...")

        import os

        os.system(f"""
        ffmpeg -i /tmp/{user_id}.mp4
        -vf ass=/tmp/{user_id}.ass
        -preset ultrafast -crf 30
        /tmp/{user_id}_out.mp4
        """)

        await app.send_video(
            message.chat.id,
            f"/tmp/{user_id}_out.mp4"
        )

app.run()
