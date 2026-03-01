FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg + ffprobe + basic tools
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy files
COPY . .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
