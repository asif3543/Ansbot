FROM python:3.11-slim

# Work directory
WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    wget \
    tar \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run bot
CMD ["python", "bot.py"]
