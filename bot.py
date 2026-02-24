from pyrogram import Client, filters
import os
from config import *
from ffmpeg import hardsub_video

app = Client("animebot",
             api_id=API_ID,
             api_hash=API_HASH,
             bot_token=BOT_TOKEN)

# Video Save
@app.on_message(filters.video)
async def save_video(client, message):

    user_id = message.from_user.id

    path = await message.download(
        file_name=f"/tmp/{user_id}.mp4"
    )

    await message.reply("✅ Video received\nSend subtitle (.ass)")

# Subtitle Save + Process
@app.on_message(filters.document)
async def save_sub(client, message):

    if message.document.file_name.endswith(".ass"):

        user_id = message.from_user.id

        await message.download(
            file_name=f"/tmp/{user_id}.ass"
        )

        await message.reply("✅ Subtitle received\nProcessing HardSub...")

        hardsub_video(user_id)

        await app.send_video(
            user_id,
            f"/tmp/{user_id}_out.mp4"
        )

app.run()
