# Python 3.11 ka base image use karega
FROM python:3.11-slim

# Yeh server me FFmpeg install karega jo hardsub ke liye zaroori hai
RUN apt-get update && apt-get install -y ffmpeg

# Folder setup aur requirements install
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baaki saara bot ka code copy karega
COPY . .

# Bot ko start karega
CMD ["python", "bot.py"]
