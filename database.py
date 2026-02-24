from firebase_admin import firestore

db = firestore.client()

# Save video file id
def save_video(user_id, file_id):
    db.collection("videos").document(str(user_id)).set({
        "file_id": file_id
    })

# Get video file id
def get_video(user_id):
    data = db.collection("videos").document(str(user_id)).get()
    if data.exists:
        return data.to_dict()
    return None
