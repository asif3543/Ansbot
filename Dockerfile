FROM python:3.11-slim

# Work directory set
WORKDIR /app

# System tools install (important for ffmpeg + render style servers)
RUN apt-get update && apt-get install -y wget tar && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download FFmpeg Static Binary
RUN wget -q https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz && \
    tar -xf ffmpeg-release-amd64-static.tar.xz && \
    cp ffmpeg-*-static/ffmpeg /usr/local/bin/ffmpeg && \
    cp ffmpeg-*-static/ffprobe /usr/local/bin/ffprobe && \
    chmod +x /usr/local/bin/ffmpeg && \
    chmod +x /usr/local/bin/ffprobe

# Run bot
CMD ["python", "bot.py"]
