from google.adk.agents.llm_agent import Agent
from .tools import (
    get_user_profile,
    update_user_profile,
    save_nutrition_log,
    get_daily_intake,
    google_search_restaurants,
    analyze_menu_nutrition
)

# -------------------------------------------------------------
# 1. Nutrition Tracker Sub-Agent
# -------------------------------------------------------------
nutrition_tracker = Agent(
    model='gemini-2.5-flash-lite',
    name='nutrition_tracker',
    description='Specializes in logging user food intake, estimating calories, and checking daily nutrition totals.',
    instruction=(
        "You are the Nutrition Tracker Sub-Agent. Your task is to log the user's food intake, "
        "estimate calories and macros (protein, carbs, fat in grams) if the user does not specify them, "
        "and record it using the `save_nutrition_log` tool. "
        "You can check their current aggregated intake for the day using the `get_daily_intake` tool. "
        "Always cross-reference the user's target calorie limit from their profile (retrieved via `get_user_profile`) "
        "and tell the user how many calories they have consumed and how many they have left for the day. "
        "Speak to the user directly, be supportive, and confirm details when logging."
    ),
    tools=[get_user_profile, save_nutrition_log, get_daily_intake]
)

# -------------------------------------------------------------
# 2. Preference Profiler / Profile Manager Sub-Agent
# -------------------------------------------------------------
profile_manager = Agent(
    model='gemini-2.5-flash-lite',
    name='profile_manager',
    description='Specializes in updating and retrieving user profiles, cuisine interests (Asian, American, French), and dietary restrictions.',
    instruction=(
        "You are the Profile Manager Sub-Agent. Your task is to update or retrieve the user's profile "
        "including daily calorie goals, dietary restrictions, and cuisine preferences (e.g. Asian, American, French). "
        "Use the `get_user_profile` tool to read the current profile, and `update_user_profile` to update specific fields. "
        "You can update cuisine interests on a scale from 0.0 to 1.0. "
        "Confirm the profile changes with the user and provide a clear summary of their updated preferences."
    ),
    tools=[get_user_profile, update_user_profile]
)

# -------------------------------------------------------------
# 3. Meal & Restaurant Search Sub-Agent
# -------------------------------------------------------------
meal_searcher = Agent(
    model='gemini-2.5-flash-lite',
    name='meal_searcher',
    description='Specializes in recommending recipes or finding D.C. area restaurants that fit within the user\'s daily calorie limit.',
    instruction=(
        "You are the Meal & Restaurant Search Sub-Agent. Your task is to recommend either a recipe to cook "
        "or a restaurant in the Washington D.C. metro area to order from/dine at. "
        "To make a recommendation: "
        "1. Retrieve the user's profile via `get_user_profile` (to check location, cuisine preferences, and calorie target). "
        "2. Retrieve the user's logged intake for today via `get_daily_intake` (to calculate remaining daily calorie budget). "
        "3. Find suggestions that fit within the user's remaining calorie budget. "
        "   - For restaurant searches: Use `google_search_restaurants` with the user's preferred cuisine and neighborhood. "
        "     Estimate or analyze the calorie counts of dishes using `analyze_menu_nutrition`. "
        "   - For recipes: Generate a recipe tailored to their cuisine preferences, dietary restrictions, and remaining calories. "
        "Present the user with clear calorie estimates, and detail why the suggestions match their cuisine interests."
    ),
    tools=[get_user_profile, get_daily_intake, google_search_restaurants, analyze_menu_nutrition]
)

# -------------------------------------------------------------
# 4. Main Orchestrator Agent (Root Agent)
# -------------------------------------------------------------
root_agent = Agent(
    model='gemini-2.5-flash-lite',
    name='root_agent',
    description='Core Food & Nutrition Assistant that coordinates logging, profile updates, and meal searches.',
    instruction=(
        "You are the Food & Nutrition Assistant Orchestrator. Your role is to greet the user and "
        "delegate their request to the appropriate specialized sub-agent: "
        "- For logging meals, checking daily totals, or estimating calories: Transfer to the `nutrition_tracker` sub-agent. "
        "- For updating dietary restrictions, cuisine preferences, or calorie goals: Transfer to the `profile_manager` sub-agent. "
        "- For meal suggestions, recipes, or searching for D.C. area restaurants under calorie limits: Transfer to the `meal_searcher` sub-agent. "
        "Always be friendly, welcoming, and guide the user on how they can manage their food and nutrition."
    ),
    sub_agents=[nutrition_tracker, profile_manager, meal_searcher]
)
