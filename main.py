# --- 1. THE DNS PATCH (MUST BE AT THE TOP) ---
import dns.resolver

# Force the code to use Google DNS to bypass ISP blocks
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

from fastapi import FastAPI, UploadFile, File, HTTPException
import pymongo
from pydantic import BaseModel
from typing import Dict, Any, List
import json
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import certifi

# --- 2. CONFIGURATION & DATABASE CONNECTION ---
ENCRYPTION_KEY = "sG5fR8eN2kL6wA3zV9bD1uXoQpY4tM7c"
MONGO_URI = "mongodb+srv://firebase_db_user:8edkAtPooOvq7hrG@teachtheworldfoundation.vpeurku.mongodb.net/?appName=TeachTheWorldFoundation"

app = FastAPI()

try:
    client = pymongo.MongoClient(
        MONGO_URI,
        tlsCAFile=certifi.where()  # <--- Forces Python to use the correct certificates
    )
    # tlsAllowInvalidCertificates=True helps with some local Windows SSL issues
    #client = pymongo.MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
    db = client["SchoolDB"]
    profiles_col = db["StudentProfiles"]
    activity_col = db["ActivityLogs"]
    client.admin.command('ping')
    print("✅ SUCCESS! Connected to MongoDB Atlas")
except Exception as e:
    print(f"❌ Connection failed: {e}")


# --- 3. DATA MODELS ---
class SyncData(BaseModel):
    schoolID: str
    ProfilesGenrated: List[Dict[str, Any]]
    localSyncDictionary: List[Dict[str, Any]]


class UIDList(BaseModel):
    uids: List[str]


# --- 4. HELPER FUNCTIONS (The Logic Core) ---

def decrypt_payload(encrypted_base64: str) -> str:
    """
    Takes a Base64 encrypted string and returns the decrypted JSON string.
    """
    try:
        key_bytes = ENCRYPTION_KEY.encode('utf-8')
        encrypted_bytes = base64.b64decode(encrypted_base64)
        cipher = AES.new(key_bytes, AES.MODE_ECB)
        decrypted_padded_bytes = cipher.decrypt(encrypted_bytes)
        decrypted_bytes = unpad(decrypted_padded_bytes, AES.block_size)
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}")


def process_and_save_data(data_dict: Dict[str, Any]):
    """
    The shared logic that saves data to MongoDB. 
    Used by both JSON sync and File Upload.
    """
    # 1. Save Profiles
    profiles = data_dict.get("ProfilesGenrated", [])
    for profile in profiles:
        uid = profile.get("profileUID")
        if uid:
            profiles_col.update_one({"profileUID": uid}, {"$set": profile}, upsert=True)

    # 2. Save Activities
    sync_dicts = data_dict.get("localSyncDictionary", [])
    if sync_dicts and len(sync_dicts) > 0:
        raw_sync = sync_dicts[0]
        if "keys" in raw_sync and "values" in raw_sync:
            clean_activities = dict(zip(raw_sync["keys"], raw_sync["values"]))

            # Use the first profile's UID as the owner
            if profiles:
                main_student_uid = profiles[0].get("profileUID")

                # Fetch existing to merge
                existing_record = activity_col.find_one({"profileUID": main_student_uid})

                if existing_record and "activities" in existing_record:
                    final_activities = existing_record["activities"]
                    final_activities.update(clean_activities)
                else:
                    final_activities = clean_activities

                activity_col.update_one(
                    {"profileUID": main_student_uid},
                    {"$set": {"profileUID": main_student_uid, "activities": final_activities}},
                    upsert=True
                )
    return len(profiles)


# --- 5. API ENDPOINTS ---

@app.get("/")
def home():
    return {"message": "API is Online, Encrypted File Upload Ready!"}


# Endpoint A: Accepts Raw JSON (Legacy/Testing)
@app.post("/sync-data")
def sync_student_data(data: SyncData):
    print(f"Received JSON sync request for School ID: {data.schoolID}")
    # Convert Pydantic model to dict and save
    count = process_and_save_data(data.dict())
    return {"status": "Success", "message": f"Synced {count} profiles from JSON."}


# Endpoint B: Accepts Encrypted Text File (The New Feature)
@app.post("/upload-file")
async def upload_encrypted_file(file: UploadFile = File(...)):
    print(f"Received file upload: {file.filename}")

    # 1. Read the file
    content = await file.read()

    # 2. Decode content (Handle UTF-8 vs CP1252)
    try:
        encrypted_text = content.decode("utf-8")
    except UnicodeDecodeError:
        encrypted_text = content.decode("cp1252")

    # 3. Decrypt
    try:
        json_str = decrypt_payload(encrypted_text)
        data_dict = json.loads(json_str)
    except Exception as e:
        return {"status": "Error", "message": f"Decryption/Parsing Failed: {str(e)}"}

    # 4. Save to MongoDB
    try:
        count = process_and_save_data(data_dict)
        return {
            "status": "Success",
            "filename": file.filename,
            "message": f"Successfully decrypted and synced {count} profiles."
        }
    except Exception as e:
        return {"status": "Error", "message": f"Database Save Failed: {str(e)}"}


# Endpoint C: Check Single Student
@app.get("/student/{profile_uid}")
def get_full_student_data(profile_uid: str):
    profile_data = profiles_col.find_one({"profileUID": profile_uid})
    if not profile_data:
        return {"status": 2505, "message": "Student not found"}

    activity_data = activity_col.find_one({"profileUID": profile_uid})
    profile_data.pop("_id", None)

    if activity_data:
        activity_data.pop("_id", None)
    else:
        activity_data = {}

    return {
        "status": 200,
        "profileUID": profile_uid,
        "profile_info": profile_data,
        "activity_logs": activity_data
    }


# Endpoint D: Check Multiple Students
@app.post("/check-multiple-users")
def check_multiple_users_exist(data: UIDList):
    results = {}
    for uid in data.uids:
        count = profiles_col.count_documents({"profileUID": uid}, limit=1)
        results[uid] = (count > 0)
    return results