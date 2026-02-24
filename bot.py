from pyrogram import Client, filters
import os

BOT_TOKEN = "8732499343:AAF2Zg6qj1gtPZdWfLygzdX3OVgnW6DHlF4"

app = Client(
    "animebot",
    bot_token=BOT_TOKEN
)

# Video Receive
@app.on_message(filters.video)
async def video_handler(client, message):

    user_id = message.from_user.id

    video_path = await message.download(
        file_name=f"{user_id}.mp4"
    )

    await message.reply("✅ Video Saved\nSend Subtitle (.ass)")

# Subtitle Receive + HardSub
@app.on_message(filters.document)
async def sub_handler(client, message):

    if message.document.file_name.endswith(".ass"):

        user_id = message.from_user.id

        sub_path = await message.download(
            file_name=f"{user_id}.ass"
        )

        await message.reply("✅ Subtitle Received\nProcessing...")

        os.system(f"""
        ffmpeg -i {user_id}.mp4
        -vf ass={user_id}.ass
        -preset ultrafast -crf 30
        {user_id}_out.mp4
        """)

        await app.send_video(
            message.chat.id,
            f"{user_id}_out.mp4"
        )

app.run()
