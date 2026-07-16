import os
import json
from datetime import datetime
from google.cloud import firestore

try:
    from .trace_logging import logger
except ImportError:
    from trace_logging import logger

# -------------------------------------------------------------
# Firestore / JSON Database Client Initialization
# -------------------------------------------------------------
FIRESTORE_AVAILABLE = False
db = None

# Attempt to initialize Firestore Client
try:
    import google.auth
    from google.auth.transport.requests import Request
    
    credentials, project_id = google.auth.default()
    
    # Determine the execution identity
    identity = "Unknown Identity"
    if hasattr(credentials, "service_account_email") and credentials.service_account_email:
        identity = credentials.service_account_email
    elif hasattr(credentials, "signer_email") and credentials.signer_email:
        identity = credentials.signer_email
    else:
        try:
            if not credentials.valid:
                credentials.refresh(Request())
            # Fetch token info to extract the user/SA email
            import urllib.request
            import json
            req = urllib.request.Request(f"https://oauth2.googleapis.com/tokeninfo?access_token={credentials.token}")
            with urllib.request.urlopen(req) as resp:
                token_info = json.loads(resp.read().decode('utf-8'))
                identity = token_info.get("email", "User Account (ADC)")
        except Exception:
            identity = "User Account (ADC)"
            
    import json
    creds_dict = {
        "type": type(credentials).__name__,
        "token": getattr(credentials, "token", None),
        "refresh_token": getattr(credentials, "refresh_token", None),
        "token_uri": getattr(credentials, "token_uri", None),
        "client_id": getattr(credentials, "client_id", None),
        "scopes": list(getattr(credentials, "scopes", [])) if getattr(credentials, "scopes", None) else None,
        "expiry": str(getattr(credentials, "expiry", "")) if getattr(credentials, "expiry", None) else None,
        "service_account_email": getattr(credentials, "service_account_email", None),
        "project_id": getattr(credentials, "project_id", None),
    }
    logger.info(f"credentials data: {json.dumps(creds_dict, indent=2)}")
            
    logger.info(f"[Initialization] Project ID: {project_id}")
    logger.info(f"[Initialization] Service Account / Identity: {identity}")
    
    db = firestore.Client(project=project_id)
    # Perform a quick read check to verify connectivity and credentials
    db.collection("users").document("connectivity_test_doc_ref").get()
    FIRESTORE_AVAILABLE = True
    logger.info("Firestore client initialized successfully.")
except Exception as e:
    logger.warning(f"Firestore not available, falling back to local JSON persistence: {e}")
    FIRESTORE_AVAILABLE = False

LOCAL_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_db.json")

def _read_local_db() -> dict:
    if not os.path.exists(LOCAL_DB_PATH):
        return {"users": {}, "nutrition_logs": []}
    try:
        with open(LOCAL_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}, "nutrition_logs": []}

def _write_local_db(data: dict):
    try:
        with open(LOCAL_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write to local DB: {e}")

# -------------------------------------------------------------
# User Profile Operations
# -------------------------------------------------------------
def get_user_profile(user_id: str) -> dict:
    """Fetches the user's profile, including dietary restrictions, cuisine preferences, and D.C. location.

    Args:
        user_id: Unique identifier for the user (e.g. "user_123").
    """
    default_profile = {
        "userId": user_id,
        "name": "User",
        "dailyCalorieTarget": 2000,
        "dietaryRestrictions": [],
        "cuisinePreferences": {
            "asian": 0.5,
            "american": 0.5,
            "french": 0.5
        },
        "location": {
            "metroArea": "Washington D.C. Metro Area",
            "neighborhood": "Dupont Circle",
            "latitude": 38.9096,
            "longitude": -77.0433
        }
    }

    if FIRESTORE_AVAILABLE:
        try:
            doc_ref = db.collection("users").document(user_id)
            doc = doc_ref.get()
            if doc.exists:
                profile = doc.to_dict()
                # Ensure all default keys exist
                for k, v in default_profile.items():
                    if k not in profile:
                        profile[k] = v
                return profile
            else:
                doc_ref.set(default_profile)
                return default_profile
        except Exception as e:
            logger.error(f"Firestore get_user_profile failed: {e}")

    # Local JSON Fallback
    data = _read_local_db()
    if user_id in data["users"]:
        profile = data["users"][user_id]
        for k, v in default_profile.items():
            if k not in profile:
                profile[k] = v
        return profile
    else:
        data["users"][user_id] = default_profile
        _write_local_db(data)
        return default_profile


def update_user_profile(user_id: str, fields: dict) -> dict:
    """Updates the user's profile in Firestore (e.g., changes preferences or calorie targets).

    Args:
        user_id: Unique identifier for the user.
        fields: A dictionary of fields to update/merge.
    """
    current_profile = get_user_profile(user_id)
    
    # Merge fields
    for k, v in fields.items():
        if isinstance(v, dict) and k in current_profile and isinstance(current_profile[k], dict):
            current_profile[k].update(v)
        else:
            current_profile[k] = v

    if FIRESTORE_AVAILABLE:
        try:
            db.collection("users").document(user_id).set(current_profile)
            return current_profile
        except Exception as e:
            logger.error(f"Firestore update_user_profile failed: {e}")

    # Local JSON Fallback
    data = _read_local_db()
    data["users"][user_id] = current_profile
    _write_local_db(data)
    return current_profile

# -------------------------------------------------------------
# Nutrition Log Operations
# -------------------------------------------------------------
def save_nutrition_log(user_id: str, date: str, meal_type: str, description: str, calories: int, protein_g: int = 0, carbs_g: int = 0, fat_g: int = 0) -> dict:
    """Logs a meal consumed by the user.

    Args:
        user_id: Unique identifier for the user.
        date: Date string formatted as 'YYYY-MM-DD'.
        meal_type: Type of meal, e.g. 'breakfast', 'lunch', 'dinner', 'snack'.
        description: Description of the food eaten.
        calories: Number of calories.
        protein_g: Grams of protein (optional).
        carbs_g: Grams of carbohydrates (optional).
        fat_g: Grams of fat (optional).
    """
    log_entry = {
        "userId": user_id,
        "date": date,
        "mealType": meal_type.lower(),
        "description": description,
        "nutrients": {
            "calories": int(calories),
            "proteinGrams": int(protein_g),
            "carbsGrams": int(carbs_g),
            "fatGrams": int(fat_g)
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    if FIRESTORE_AVAILABLE:
        try:
            doc_ref = db.collection("nutrition_logs").document()
            doc_ref.set(log_entry)
            result = log_entry.copy()
            result["logId"] = doc_ref.id
            return result
        except Exception as e:
            logger.error(f"Firestore save_nutrition_log failed: {e}")

    # Local JSON Fallback
    data = _read_local_db()
    log_id = f"log_{int(datetime.utcnow().timestamp() * 1000)}"
    log_entry["logId"] = log_id
    data["nutrition_logs"].append(log_entry)
    _write_local_db(data)
    return log_entry


def get_daily_intake(user_id: str, date: str) -> dict:
    """Aggregates all nutrition logs for a given user on a specific date.

    Args:
        user_id: Unique identifier for the user.
        date: Date string formatted as 'YYYY-MM-DD'.
    """
    total_calories = 0
    total_protein = 0
    total_carbs = 0
    total_fat = 0
    meals = []

    if FIRESTORE_AVAILABLE:
        try:
            logs = db.collection("nutrition_logs")\
                     .where("userId", "==", user_id)\
                     .where("date", "==", date)\
                     .stream()
            for doc in logs:
                data = doc.to_dict()
                nutrients = data.get("nutrients", {})
                total_calories += nutrients.get("calories", 0)
                total_protein += nutrients.get("proteinGrams", 0)
                total_carbs += nutrients.get("carbsGrams", 0)
                total_fat += nutrients.get("fatGrams", 0)
                meals.append({
                    "mealType": data.get("mealType"),
                    "description": data.get("description"),
                    "calories": nutrients.get("calories", 0)
                })
            return {
                "date": date,
                "total_calories": total_calories,
                "total_protein": total_protein,
                "total_carbs": total_carbs,
                "total_fat": total_fat,
                "meals": meals
            }
        except Exception as e:
            logger.error(f"Firestore get_daily_intake failed: {e}")

    # Local JSON Fallback
    data = _read_local_db()
    for entry in data["nutrition_logs"]:
        if entry["userId"] == user_id and entry["date"] == date:
            nutrients = entry.get("nutrients", {})
            total_calories += nutrients.get("calories", 0)
            total_protein += nutrients.get("proteinGrams", 0)
            total_carbs += nutrients.get("carbsGrams", 0)
            total_fat += nutrients.get("fatGrams", 0)
            meals.append({
                "mealType": entry.get("mealType"),
                "description": entry.get("description"),
                "calories": nutrients.get("calories", 0)
            })

    return {
        "date": date,
        "total_calories": total_calories,
        "total_protein": total_protein,
        "total_carbs": total_carbs,
        "total_fat": total_fat,
        "meals": meals
    }
