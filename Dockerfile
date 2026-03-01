FROM python:3.11-slim

# Install FFmpeg, Fonts, and Subtitle libraries
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libass-dev \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Refresh font cache to recognize new fonts
RUN fc-cache -f -v

# Copy all files to the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Start the bot
CMD ["python", "bot.py"]
