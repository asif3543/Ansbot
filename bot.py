Aapke code mein kuch badi mistakes hain jo bot ko crash kar sakti hain ya slow kar sakti hain. Main unhe point-out karke sahi code de raha hu.

🔴 Problems in your code:

os.system(cmd) (Blocking Issue): Yeh function poore bot ko freeze kar dega. Jab tak ek video process hogi, bot kisi aur user ka message read nahi karega (even /start bhi nahi). Ise asyncio.create_subprocess_shell se replace karna hoga.

FFmpeg Filter Conflict: Aapne FFmpeg command mein -filter_complex (watermark ke liye) aur -vf (subtitle ke liye) ek sath use kiya hai. FFmpeg mein yeh dono ek sath kaam nahi karte, error aata hai.

Missing File Names: Telegram par kabhi-kabhi video ya document ka file_name nahi hota (None hota hai). Aapka code waha .split() karte waqt crash ho jayega.

Global Lock: processing_lock lagane se ek time par sirf 1 hi banda bot use kar payega. Ise asyncio.Semaphore mein badalna chahiye taaki server overload bhi na ho aur multiple log use bhi kar sakein.

code
Python
download
content_copy
expand_less
import os
import asyncio
from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN

# =========================
# APP INIT
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

# Allow maximum 2 videos to process at the same time to prevent server crash
process_semaphore = asyncio.Semaphore(2) 
waiting_thumbnail = {}

# =========================
# START COMMAND
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
    
    # Safe check for filename
    file_name = message.video.file_name if message.video.file_name else "video.mp4"
    ext = file_name.split(".")[-1] if "." in file_name else "mp4"

    file_path = f"downloads/{user_id}.{ext}"
    msg = await message.reply("⏳ Downloading Video...")
    
    await message.download(file_name=file_path)
    await msg.edit("✅ **Video Received**\nNow send Subtitle (.ass)")

# =========================
# SUBTITLE RECEIVE
# =========================
@app.on_message(filters.document & filters.private)
async def subtitle_handler(client, message):
    file_name = message.document.file_name
    
    if not file_name or not file_name.endswith(".ass"):
        return await message.reply("❌ Please send a valid `.ass` subtitle file.")

    user_id = message.from_user.id
    file_path = f"downloads/{user_id}.ass"

    msg = await message.reply("⏳ Downloading Subtitle...")
    await message.download(file_name=file_path)
    await msg.edit("✅ **Subtitle Received**\nSend /bakk to start processing 🎬")

# =========================
# THUMBNAIL COMMANDS
# =========================
@app.on_message(filters.command("thumbnail") & filters.private)
async def ask_thumbnail(client, message):
    user_id = message.from_user.id
    waiting_thumbnail[user_id] = True
    await message.reply("📸 Send a Photo to set as Video Thumbnail (Cover).")

@app.on_message(filters.photo & filters.private)
async def save_thumbnail(client, message):
    user_id = message.from_user.id

    if waiting_thumbnail.get(user_id):
        thumb_path = f"thumbnails/{user_id}.jpg"
        msg = await message.reply("⏳ Saving Thumbnail...")
        await message.download(file_name=thumb_path)
        waiting_thumbnail[user_id] = False
        await msg.edit("✅ **Thumbnail Saved**")

@app.on_message(filters.command("remove_thumbnail") & filters.private)
async def remove_thumbnail(client, message):
    user_id = message.from_user.id
    thumb_file = f"thumbnails/{user_id}.jpg"

    if os.path.exists(thumb_file):
        os.remove(thumb_file)
        await message.reply("🗑 **Thumbnail Removed**")
    else:
        await message.reply("❌ No Thumbnail Found")

# =========================
# HARD SUB PROCESS
# =========================
@app.on_message(filters.command("bakk") & filters.private)
async def process_video(client, message):
    user_id = message.from_user.id

    mp4_file = f"downloads/{user_id}.mp4"
    mkv_file = f"downloads/{user_id}.mkv"
    sub_file = f"downloads/{user_id}.ass"
    thumb_file = f"thumbnails/{user_id}.jpg"
    output_file = f"downloads/{user_id}_out.mp4"

    video_file = mp4_file if os.path.exists(mp4_file) else mkv_file if os.path.exists(mkv_file) else None

    if not video_file:
        return await message.reply("❌ Send Video First")

    if not os.path.exists(sub_file):
        return await message.reply("❌ Send Subtitle First")

    msg = await message.reply("⏳ Added to queue... Please wait.")

    # Using Semaphore so that server doesn't crash from too many FFmpeg processes at once
    async with process_semaphore:
        await msg.edit("🎬 **Processing HardSub... Please Wait**\nThis may take some time.")

        try:
            # Proper escaping for subtitle path in FFmpeg
            escaped_sub = sub_file.replace("\\", "/").replace(":", "\\:")
            
            # Subtitle only Command (Telegram Video Cover as Thumbnail)
            cmd = f'ffmpeg -y -i "{video_file}" -vf "ass=\'{escaped_sub}\'" -c:v libx264 -preset ultrafast -c:a copy "{output_file}"'
            
            # Run FFmpeg asynchronously (Won't freeze the bot)
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            if os.path.exists(output_file):
                await msg.edit("📤 **Uploading Video...**")
                
                # Use the thumbnail as Telegram video cover if it exists
                thumb_path = thumb_file if os.path.exists(thumb_file) else None

                await client.send_video(
                    chat_id=message.chat.id,
                    video=output_file,
                    thumb=thumb_path, # Attaches thumbnail to telegram video
                    caption="✅ HardSub Completed",
                    supports_streaming=True
                )
                await msg.delete()
            else:
                await msg.edit("❌ **Error during HardSubbing!** Process failed.")

        except Exception as e:
            await msg.edit(f"❌ **Error:** `{str(e)}`")

        finally:
            # CLEANUP FILES TO SAVE DISK SPACE
            for file in[mp4_file, mkv_file, sub_file, output_file]:
                if os.path.exists(file):
                    os.remove(file)

# =========================
# RUN BOT
# =========================
if __name__ == "__main__":
    print("Bot is Running...")
    app.run()
