import os

def hardsub_video(user_id):
    os.system(f"""
    ffmpeg -i /tmp/{user_id}.mp4
    -vf ass=/tmp/{user_id}.ass
    -preset ultrafast -crf 30
    /tmp/{user_id}_out.mp4
    """)
