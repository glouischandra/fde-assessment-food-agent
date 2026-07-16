import os
import json
from pydantic import BaseModel, Field, field_validator, ValidationError
from typing import Literal

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
# Input Validation Schemas
# -------------------------------------------------------------
class GoogleSearchRestaurantsInput(BaseModel):
    query: str = Field(..., description="The search query (e.g. French restaurant, Asian restaurant, salad)")
    neighborhood: str = Field(..., description="Target D.C. neighborhood (e.g. Dupont Circle, Logan Circle)")

    @field_validator("neighborhood")
    def validate_neighborhood(cls, v):
        # Normalize and validate neighborhood input
        allowed = {"dupont circle", "logan circle", "penn quarter", "columbia heights", "chinatown", "foggy bottom", "shaw", "washington d.c."}
        if v.lower() not in allowed:
            raise ValueError(f"neighborhood must be one of the known D.C. metro neighborhoods: {', '.join(allowed)}")
        return v


class AnalyzeMenuNutritionInput(BaseModel):
    restaurant_name: str = Field(..., description="Name of the restaurant")
    dish_description: str = Field(..., description="Description or name of the dish")

try:
    from .constants import DC_RESTAURANTS
except ImportError:
    from constants import DC_RESTAURANTS

# -------------------------------------------------------------
# Google Search Fallback / D.C. Restaurant Database (Synchronous Tools)
# -------------------------------------------------------------
def google_search_restaurants(query: str, neighborhood: str = "Washington D.C.") -> dict:
    """Queries Google Search (or uses the local D.C. restaurant database) to suggest restaurants matching cuisine and neighborhood.

    Args:
        query: The search query (e.g. "French restaurants").
        neighborhood: The neighborhood to target in the D.C. area (e.g. "Dupont Circle").
    """
    try:
        GoogleSearchRestaurantsInput(query=query, neighborhood=neighborhood)
    except ValidationError as ve:
        error_msg = f"Argument Validation Error: {ve}. Please correct the parameters and call the tool again with valid inputs."
        logger.warning(error_msg)
        return {"status": "error", "message": error_msg}

    query_lower = query.lower()
    neighborhood_lower = neighborhood.lower()

    try:
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
    except Exception as search_err:
        error_msg = f"Search Execution Error: {search_err}. Unable to parse results from the restaurant database."
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}


def analyze_menu_nutrition(restaurant_name: str, dish_description: str) -> dict:
    """Estimates the calories and macronutrients of a restaurant dish.

    Args:
        restaurant_name: Name of the restaurant.
        dish_description: Description or name of the dish.
    """
    try:
        AnalyzeMenuNutritionInput(restaurant_name=restaurant_name, dish_description=dish_description)
    except ValidationError as ve:
        error_msg = f"Argument Validation Error: {ve}. Please correct the parameters and call the tool again with valid inputs."
        logger.warning(error_msg)
        return {"status": "error", "message": error_msg}

    try:
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
    except Exception as analysis_err:
        error_msg = f"Nutrition Analysis Error: {analysis_err}. Unable to estimate nutritional values."
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}
