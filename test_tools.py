import os
import logging
logging.basicConfig(level=logging.INFO)
from tools import (
    get_user_profile,
    update_user_profile,
    save_nutrition_log,
    get_daily_intake,
    google_search_restaurants,
    analyze_menu_nutrition
)

def run_tests():
    user_id = "test_user_999"
    date_str = "2026-07-14"

    # Clean up existing test data in Firestore for idempotence
    from tools import db
    try:
        db.collection("users").document(user_id).delete()
        logs = db.collection("nutrition_logs").where("userId", "==", user_id).stream()
        for doc in logs:
            doc.reference.delete()
    except Exception as e:
        print("Firestore cleanup warning (likely local fallback mode):", e)

    print("--- 1. Testing User Profile Fetch ---")
    profile = get_user_profile(user_id)
    print("Fetched Profile:", profile)
    assert profile["userId"] == user_id, "User ID mismatch"
    assert profile["location"]["neighborhood"] == "Dupont Circle", "Default neighborhood mismatch"

    print("\n--- 2. Testing User Profile Update ---")
    updated_profile = update_user_profile(user_id, {
        "cuisinePreferences": {"french": 0.9, "asian": 0.2},
        "location": {"neighborhood": "Logan Circle"}
    })
    print("Updated Profile:", updated_profile)
    assert updated_profile["cuisinePreferences"]["french"] == 0.9, "Preference update failed"
    assert updated_profile["location"]["neighborhood"] == "Logan Circle", "Location update failed"

    print("\n--- 3. Testing Save Nutrition Log ---")
    log1 = save_nutrition_log(
        user_id=user_id,
        date=date_str,
        meal_type="lunch",
        description="Turkey sandwich with mustard",
        calories=350,
        protein_g=25,
        carbs_g=40,
        fat_g=8
    )
    print("Logged Meal 1:", log1)
    
    log2 = save_nutrition_log(
        user_id=user_id,
        date=date_str,
        meal_type="snack",
        description="Apple",
        calories=95,
        protein_g=0,
        carbs_g=25,
        fat_g=0
    )
    print("Logged Meal 2:", log2)

    print("\n--- 4. Testing Daily Intake Aggregation ---")
    intake = get_daily_intake(user_id, date_str)
    print("Aggregated Intake:", intake)
    assert intake["total_calories"] == 445, f"Calorie sum mismatch: {intake['total_calories']}"
    assert len(intake["meals"]) == 2, "Meal count mismatch"

    print("\n--- 5. Testing Restaurant Search ---")
    search_results = google_search_restaurants("French restaurants", "Logan Circle")
    print("Search Results (French/Logan Circle):", search_results)
    assert len(search_results["results"]) > 0, "No restaurants found"
    
    search_results_asian = google_search_restaurants("Asian", "Dupont Circle")
    print("Search Results (Asian/Dupont Circle):", search_results_asian)

    print("\n--- 6. Testing Menu Nutrition Analysis ---")
    nutrition_le_dip = analyze_menu_nutrition("Le Diplomate", "Salade Nicoise")
    print("Le Diplomate Salade Nicoise estimated nutrition:", nutrition_le_dip)
    assert nutrition_le_dip["estimated_calories"] == 480, "Menu lookup failed"
    
    print("\n--- 7. Testing Validation Error Handling ---")
    # Test invalid date in save_nutrition_log
    res_date = save_nutrition_log(
        user_id=user_id,
        date="invalid-date-format",
        meal_type="lunch",
        description="Turkey sandwich",
        calories=350
    )
    print("Invalid Date Result:", res_date)
    assert res_date["status"] == "error", "Should return error status for invalid date"
    assert "Argument Validation Error" in res_date["message"], "Should have validation error message for date"

    # Test invalid calories in save_nutrition_log
    res_cal = save_nutrition_log(
        user_id=user_id,
        date=date_str,
        meal_type="lunch",
        description="Turkey sandwich",
        calories=-100
    )
    print("Negative Calories Result:", res_cal)
    assert res_cal["status"] == "error", "Should return error status for negative calories"
    assert "Argument Validation Error" in res_cal["message"], "Should have validation error message for calories"

    # Test invalid neighborhood in restaurant search
    res_neigh = google_search_restaurants(query="French", neighborhood="New York")
    print("Invalid Neighborhood Result:", res_neigh)
    assert res_neigh["status"] == "error", "Should return error status for invalid neighborhood"
    assert "Argument Validation Error" in res_neigh["message"], "Should have validation error message for neighborhood"

    print("\nALL DATABASE AND TOOL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
