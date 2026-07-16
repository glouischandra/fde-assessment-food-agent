import os
import json
from datetime import datetime
try:
    from .storage import (
        db,
        FIRESTORE_AVAILABLE,
        get_user_profile,
        update_user_profile,
        save_nutrition_log,
        get_daily_intake
    )
except ImportError:
    from storage import (
        db,
        FIRESTORE_AVAILABLE,
        get_user_profile,
        update_user_profile,
        save_nutrition_log,
        get_daily_intake
    )

try:
    from .trace_logging import logger
except ImportError:
    from trace_logging import logger

# -------------------------------------------------------------
# Google Search Fallback / D.C. Restaurant Database
# -------------------------------------------------------------
DC_RESTAURANTS = [
    # French
    {
        "name": "Le Diplomate",
        "cuisine": "French",
        "neighborhood": "Logan Circle",
        "rating": 4.7,
        "description": "A bustling French brasserie offering classic dishes.",
        "healthy_dishes": [
            {"name": "Steak Frites (shareable)", "calories": 850, "description": "Classic steak frites."},
            {"name": "Moules Frites", "calories": 600, "description": "Mussels steamed in white wine and garlic."},
            {"name": "Salade Nicoise", "calories": 480, "description": "Tuna, potatoes, green beans, hard-boiled eggs."}
        ]
    },
    {
        "name": "Bistrot du Coin",
        "cuisine": "French",
        "neighborhood": "Dupont Circle",
        "rating": 4.4,
        "description": "Traditional French cafe with dynamic bistro fare.",
        "healthy_dishes": [
            {"name": "Salade de Chevre Chaud", "calories": 400, "description": "Warm goat cheese salad."},
            {"name": "Poulet Roti", "calories": 550, "description": "Roasted chicken with herbs and salad."}
        ]
    },
    # Asian
    {
        "name": "Rasika",
        "cuisine": "Asian (Indian)",
        "neighborhood": "Penn Quarter",
        "rating": 4.8,
        "description": "Award-winning modern Indian restaurant.",
        "healthy_dishes": [
            {"name": "Palak Chaat (crispy spinach)", "calories": 350, "description": "Spinach with yogurt and tamarind."},
            {"name": "Chicken Tikka Sansar", "calories": 450, "description": "Tandoori chicken with spices."}
        ]
    },
    {
        "name": "Thip Khao",
        "cuisine": "Asian (Laotian)",
        "neighborhood": "Columbia Heights",
        "rating": 4.6,
        "description": "Fiery and complex flavors of Laos cuisine.",
        "healthy_dishes": [
            {"name": "Minced Chicken Larb", "calories": 380, "description": "Laotian minced chicken salad with fresh herbs."},
            {"name": "Moo Som (sour pork)", "calories": 490, "description": "Cured pork belly."}
        ]
    },
    {
        "name": "Daikaya",
        "cuisine": "Asian (Japanese)",
        "neighborhood": "Chinatown",
        "rating": 4.5,
        "description": "Vibrant ramen shop and izakaya.",
        "healthy_dishes": [
            {"name": "Shio Ramen", "calories": 650, "description": "Light salt-based broth ramen."},
            {"name": "Yakitori (Skewered Chicken)", "calories": 250, "description": "Grilled chicken skewers."}
        ]
    },
    # American
    {
        "name": "Founding Farmers",
        "cuisine": "American",
        "neighborhood": "Foggy Bottom",
        "rating": 4.3,
        "description": "Farm-to-table American classics and comfort food.",
        "healthy_dishes": [
            {"name": "Farmers Salad & Salmon", "calories": 550, "description": "Mixed greens, seeds, and roasted salmon."},
            {"name": "Turkey Burger", "calories": 600, "description": "Lean turkey burger on a brioche bun."}
        ]
    },
    {
        "name": "The Dabney",
        "cuisine": "American",
        "neighborhood": "Shaw",
        "rating": 4.7,
        "description": "Mid-Atlantic regional cuisine cooked over a wood-burning hearth.",
        "healthy_dishes": [
            {"name": "Hearth-Roasted Rockfish", "calories": 520, "description": "Rockfish with seasonal vegetables."},
            {"name": "Charred Broccoli Salad", "calories": 280, "description": "Broccoli, peanuts, and vinegar dressing."}
        ]
    }
]

def google_search_restaurants(query: str, neighborhood: str = "Washington D.C.") -> dict:
    """Queries Google Search (or uses the local D.C. restaurant database) to suggest restaurants matching cuisine and neighborhood.

    Args:
        query: The search query (e.g. "French restaurants").
        neighborhood: The neighborhood to target in the D.C. area (e.g. "Dupont Circle").
    """
    query_lower = query.lower()
    neighborhood_lower = neighborhood.lower()

    # Search local database for match
    matches = []
    for r in DC_RESTAURANTS:
        cuisine_match = r["cuisine"].lower() in query_lower or query_lower in r["cuisine"].lower()
        neighborhood_match = r["neighborhood"].lower() in neighborhood_lower or neighborhood_lower in r["neighborhood"].lower()
        
        # Check if query matches restaurant name or description
        text_match = query_lower in r["name"].lower() or query_lower in r["description"].lower()

        if cuisine_match or text_match or (neighborhood_match and len(matches) < 2):
            matches.append(r)

    # Return matching entries structured as a search result
    if matches:
        return {
            "status": "success",
            "source": "local_dc_restaurant_db",
            "query": f"{query} in {neighborhood}",
            "results": matches
        }

    # Default fallback if no match found
    return {
        "status": "success",
        "source": "local_dc_restaurant_db",
        "query": f"{query} in {neighborhood}",
        "results": DC_RESTAURANTS[:3] # return top 3
    }


def analyze_menu_nutrition(restaurant_name: str, dish_description: str) -> dict:
    """Estimates the calories and macronutrients of a restaurant dish.

    Args:
        restaurant_name: Name of the restaurant.
        dish_description: Description or name of the dish.
    """
    # Look up in our local database first
    dish_lower = dish_description.lower()
    for r in DC_RESTAURANTS:
        if r["name"].lower() == restaurant_name.lower():
            for dish in r["healthy_dishes"]:
                if dish["name"].lower() in dish_lower or dish_lower in dish["name"].lower():
                    return {
                        "status": "success",
                        "restaurant": restaurant_name,
                        "dish": dish["name"],
                        "estimated_calories": dish["calories"],
                        "estimated_protein_g": int(dish["calories"] * 0.05), # rough mock calculation
                        "estimated_carbs_g": int(dish["calories"] * 0.1),
                        "estimated_fat_g": int(dish["calories"] * 0.03)
                    }

    # If not found, use a rough baseline estimation
    # The agent LLM itself can override this using its internal reasoning.
    return {
        "status": "success",
        "restaurant": restaurant_name,
        "dish": dish_description,
        "estimated_calories": 500,
        "estimated_protein_g": 25,
        "estimated_carbs_g": 40,
        "estimated_fat_g": 15
    }
