from pymongo import MongoClient
from config import MONGO_URL

client = MongoClient(MONGO_URL)

db = client["animebot"]
users = db["users"]
