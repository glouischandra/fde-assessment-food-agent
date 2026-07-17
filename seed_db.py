from datetime import datetime, timedelta
import logging
import os

from google.cloud import firestore

from trace_logging import logger

# -------------------------------------------------------------
# Define Seed Data
# -------------------------------------------------------------
SEED_USERS = [
    {
        "userId": "user123",
        "name": "Alice",
        "dailyCalorieTarget": 1800,
        "dietaryRestrictions": ["gluten-free"],
        "cuisinePreferences": {
            "asian": 0.8,
            "american": 0.5,
            "french": 0.4
        },
        "location": {
            "metroArea": "Washington D.C. Metro Area",
            "neighborhood": "Dupont Circle",
            "latitude": 38.9096,
            "longitude": -77.0433
        }
    },
    {
        "userId": "user456",
        "name": "Bob",
        "dailyCalorieTarget": 2200,
        "dietaryRestrictions": ["vegan"],
        "cuisinePreferences": {
            "asian": 0.9,
            "american": 0.6,
            "french": 0.2
        },
        "location": {
            "metroArea": "Washington D.C. Metro Area",
            "neighborhood": "Georgetown",
            "latitude": 38.9049,
            "longitude": -77.0628
        }
    },
    {
        "userId": "user789",
        "name": "Charlie",
        "dailyCalorieTarget": 2500,
        "dietaryRestrictions": [],
        "cuisinePreferences": {
            "asian": 0.4,
            "american": 0.8,
            "french": 0.7
        },
        "location": {
            "metroArea": "Washington D.C. Metro Area",
            "neighborhood": "Navy Yard",
            "latitude": 38.8765,
            "longitude": -77.0011
        }
    }
]

# Generate log timestamps for today and yesterday
today_str = datetime.utcnow().strftime("%Y-%m-%d")
yesterday_str = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

SEED_LOGS = [
    # Alice (user123)
    {
        "userId": "user123",
        "date": yesterday_str,
        "mealType": "breakfast",
        "description": "Gluten-free oatmeal with banana and honey",
        "nutrients": {"calories": 350, "proteinGrams": 8, "carbsGrams": 65, "fatGrams": 5},
        "timestamp": f"{yesterday_str}T08:15:00Z"
    },
    {
        "userId": "user123",
        "date": yesterday_str,
        "mealType": "lunch",
        "description": "Salmon avocado sushi roll (8 pcs)",
        "nutrients": {"calories": 500, "proteinGrams": 20, "carbsGrams": 60, "fatGrams": 18},
        "timestamp": f"{yesterday_str}T13:00:00Z"
    },
    {
        "userId": "user123",
        "date": today_str,
        "mealType": "breakfast",
        "description": "Scrambled eggs (2) with spinach",
        "nutrients": {"calories": 180, "proteinGrams": 14, "carbsGrams": 2, "fatGrams": 12},
        "timestamp": f"{today_str}T08:30:00Z"
    },
    
    # Bob (user456)
    {
        "userId": "user456",
        "date": today_str,
        "mealType": "breakfast",
        "description": "Tofu scramble and whole wheat toast",
        "nutrients": {"calories": 400, "proteinGrams": 22, "carbsGrams": 45, "fatGrams": 14},
        "timestamp": f"{today_str}T09:00:00Z"
    },
    {
        "userId": "user456",
        "date": today_str,
        "mealType": "lunch",
        "description": "Vegan buddha bowl with tahini dressing",
        "nutrients": {"calories": 650, "proteinGrams": 18, "carbsGrams": 85, "fatGrams": 24},
        "timestamp": f"{today_str}T13:15:00Z"
    },

    # Charlie (user789)
    {
        "userId": "user789",
        "date": today_str,
        "mealType": "lunch",
        "description": "Double cheeseburger and small fries",
        "nutrients": {"calories": 950, "proteinGrams": 45, "carbsGrams": 85, "fatGrams": 48},
        "timestamp": f"{today_str}T12:45:00Z"
    }
]

def seed_database():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "glouischandra-demo")
    logger.info("Connecting to Firestore project", extra={"project_id": project_id})
    
    try:
        db = firestore.Client(project=project_id)
    except Exception as e:
        logger.error(
            "Failed to connect to Firestore during seeding",
            exc_info=True,
            extra={"error.message": str(e), "project_id": project_id}
        )
        return

    # Seed Users
    logger.info("Seeding users collection")
    for user_data in SEED_USERS:
        user_id = user_data["userId"]
        db.collection("users").document(user_id).set(user_data)
        logger.info(
            "Added/Updated user profile in database",
            extra={"user_id": user_id, "user_name": user_data["name"]}
        )

    # Seed Logs
    logger.info("Seeding nutrition_logs collection")
    # First, let's clean up existing mock logs for these seed users to keep it clean
    for user_data in SEED_USERS:
        uid = user_data["userId"]
        existing = db.collection("nutrition_logs").where("userId", "==", uid).stream()
        for doc in existing:
            doc.reference.delete()
            
    for log_data in SEED_LOGS:
        doc_ref = db.collection("nutrition_logs").document()
        doc_ref.set(log_data)
        logger.info(
            "Added/Updated nutrition log entry in database",
            extra={
                "user_id": log_data["userId"],
                "meal_type": log_data["mealType"],
                "description": log_data["description"],
                "calories": log_data["nutrients"]["calories"]
            }
        )

    logger.info("Database seeding completed successfully")

if __name__ == "__main__":
    seed_database()
