from google.adk.agents.llm_agent import Agent
from google.adk.models.google_llm import Gemini
from google.genai import types
from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Optional
from .tools import (
    get_user_profile,
    update_user_profile,
    save_nutrition_log,
    get_daily_intake,
    google_search_restaurants,
    analyze_menu_nutrition
)

# Configure retry options for Vertex AI Gemini calls (for robust 429 rate limit mitigation)
retry_config = types.HttpRetryOptions(
    attempts=5,        # Maximum retry attempts
    exp_base=7,        # Exponential backoff base
    initial_delay=1,   # Starting delay in seconds
    http_status_codes=[429, 500, 503, 504], # Retry on these HTTP errors
)

ORCHESTRATOR_MODEL = Gemini(model='gemini-2.5-pro', retry_options=retry_config)
TASK_MODEL = Gemini(model='gemini-2.5-flash-lite', retry_options=retry_config)

# -------------------------------------------------------------
# Structured Output Schemas for Task Sub-Agents
# -------------------------------------------------------------
class NutritionTrackerResult(BaseModel):
    status: str = Field(description="Result status: 'success' or 'error'")
    logged_meal: Optional[str] = Field(None, description="The description of the meal logged")
    calories_logged: Optional[int] = Field(None, description="Calories of the meal logged")
    daily_calories_consumed: int = Field(description="Total daily calories consumed today")
    daily_calories_remaining: int = Field(description="Calories remaining under the user's daily budget")


class ProfileManagerResult(BaseModel):
    status: str = Field(description="Result status: 'success' or 'error'")
    user_id: str = Field(description="The user identifier")
    updated_fields: Dict = Field(description="Dictionary of fields that were updated")
    current_profile: Dict = Field(description="The complete current profile of the user")


class MealSearcherResult(BaseModel):
    status: str = Field(description="Result status: 'success' or 'error'")
    remaining_calories: int = Field(description="User's remaining daily calorie budget")
    recommendation_type: Literal["recipe", "restaurant"] = Field(description="The recommendation type: recipe or restaurant")
    recommendations: List[Dict] = Field(description="List of recommendations, including names, descriptions, and estimated calories")

# -------------------------------------------------------------
# 1. Nutrition Tracker Sub-Agent (Task Mode)
# -------------------------------------------------------------
nutrition_tracker = Agent(
    model=ORCHESTRATOR_MODEL,
    name='nutrition_tracker',
    description='Specializes in logging user food intake, estimating calories, and checking daily nutrition totals.',
    mode='task',
    output_schema=NutritionTrackerResult,
    instruction=(
        "You are the Nutrition Tracker Sub-Agent. Your task is to log the user's food intake. "
        "To perform this task: "
        "1. Retrieve the user's current daily intake via `get_daily_intake` for today, and target calorie limit from `get_user_profile`. "
        "2. If the user does not specify the calorie number, you MUST estimate the calories and macros (protein, carbs, fat in grams) yourself immediately (do NOT ask the user for the calories; estimate them yourself, e.g. 350 calories for a Turkey sandwich). "
        "3. BEFORE calling the `save_nutrition_log` tool, you MUST explicitly ask the user for permission. Your message asking for permission MUST include: "
        "   - The food details (description). "
        "   - The calories number (estimated or specified). "
        "   - The new projected daily calorie count for the day (today's current total + this meal's calories). "
        "   (For example: 'I would like to log a Turkey sandwich (350 calories). This will bring your daily calorie count to 1250. May I proceed?'). "
        "   Do NOT call the `save_nutrition_log` tool yet; ask and wait for the user to respond. "
        "4. Once the user replies and gives you permission in a subsequent turn, call the `save_nutrition_log` tool. "
        "5. Calculate the final daily calories consumed and remaining, and return the structured result by calling the `finish_task` tool. "
        "CRITICAL: Call the `finish_task` tool directly as a tool call. Never wrap the tool call inside print(), python markdown blocks, code blocks, or string formats. Invoke it strictly as a tool function."
    ),
    tools=[get_user_profile, save_nutrition_log, get_daily_intake]
)

# -------------------------------------------------------------
# 2. Preference Profiler / Profile Manager Sub-Agent (Task Mode)
# -------------------------------------------------------------
profile_manager = Agent(
    model=ORCHESTRATOR_MODEL,
    name='profile_manager',
    description='Specializes in updating and retrieving user profiles, cuisine interests (Asian, American, French), and dietary restrictions.',
    mode='task',
    output_schema=ProfileManagerResult,
    instruction=(
        "You are the Profile Manager Sub-Agent. Your task is to update or retrieve the user's profile "
        "including daily calorie goals, dietary restrictions, and cuisine preferences (e.g. Asian, American, French). "
        "Use the `get_user_profile` tool to read the current profile, and `update_user_profile` to update specific fields. "
        "You can update cuisine interests on a scale from 0.0 to 1.0. "
        "Once completed, return the structured result by calling the `finish_task` tool. "
        "CRITICAL: Call the `finish_task` tool directly as a tool call. Never wrap the tool call inside print(), python markdown blocks, code blocks, or string formats. Invoke it strictly as a tool function."
    ),
    tools=[get_user_profile, update_user_profile]
)

# -------------------------------------------------------------
# 3. Meal & Restaurant Search Sub-Agent (Task Mode)
# -------------------------------------------------------------
meal_searcher = Agent(
    model=ORCHESTRATOR_MODEL,
    name='meal_searcher',
    description='Specializes in recommending recipes or finding D.C. area restaurants that fit within the user\'s daily calorie limit.',
    mode='task',
    output_schema=MealSearcherResult,
    instruction=(
        "You are the Meal & Restaurant Search Sub-Agent. Your task is to recommend either a recipe to cook "
        "or a restaurant in the Washington D.C. metro area to order from/dine at. "
        "To make a recommendation: "
        "1. Retrieve the user's profile via `get_user_profile` (to check location, cuisine preferences, and calorie target). "
        "2. Retrieve the user's logged intake for today via `get_daily_intake` (to calculate remaining daily calorie budget). "
        "3. Find suggestions that fit within the user's remaining calorie budget. "
        "   - For restaurant searches: BEFORE you call the `google_search_restaurants` tool, you MUST explicitly ask the user for permission (e.g., 'I would like to search Google for French restaurants in Dupont Circle. May I proceed?'). Do NOT call the tool yet; ask and wait for the user to respond. Once the user replies and gives you permission in a subsequent turn, proceed to call `google_search_restaurants` with the user's preferred cuisine and neighborhood. Then estimate or analyze the calorie counts of dishes using `analyze_menu_nutrition`. "
        "   - For recipes: Generate a recipe tailored to their cuisine preferences, dietary restrictions, and remaining calories. "
        "Once completed, return the structured result by calling the `finish_task` tool. "
        "CRITICAL: Call the `finish_task` tool directly. Never wrap your tool call inside a Python print() statement, python markdown block, or code block."
    ),
    tools=[get_user_profile, get_daily_intake, google_search_restaurants, analyze_menu_nutrition]
)

# -------------------------------------------------------------
# 4. Main Orchestrator Agent (Root Agent)
# -------------------------------------------------------------
from typing import Any, AsyncGenerator

class CustomRootAgent(Agent):
    async def _run_impl(
        self,
        *,
        ctx: Any,
        node_input: Any,
    ) -> AsyncGenerator[Any, None]:
        # Clear dynamic node task references from prior turns to prevent asyncio self-await deadlocks.
        if ctx._workflow_scheduler and hasattr(ctx._workflow_scheduler, '_state'):
            runs = getattr(ctx._workflow_scheduler._state, 'runs', {})
            import asyncio
            current_task = asyncio.current_task()
            for path, run in list(runs.items()):
                if run.task and run.task != current_task:
                    if not run.task.done():
                        run.task.cancel()
                    run.task = None

        async for event in super()._run_impl(ctx=ctx, node_input=node_input):
            yield event

root_agent = CustomRootAgent(
    model=ORCHESTRATOR_MODEL,
    name='root_agent',
    description='Core Food & Nutrition Assistant that coordinates logging, profile updates, and meal searches.',
    instruction=(
        "You are the Food & Nutrition Assistant Orchestrator. Your role is to coordinate and "
        "delegate tasks to the appropriate specialized sub-agent by calling their tool function:\n"
        "- Call the `nutrition_tracker` tool for logging meals, checking daily totals, or estimating calories.\n"
        "- Call the `profile_manager` tool for updating dietary restrictions, cuisine preferences, or calorie goals.\n"
        "- Call the `meal_searcher` tool for meal suggestions, recipes, or searching for D.C. area restaurants under calorie limits.\n\n"
        "Provide the user request to the sub-agent as the input argument. "
        "Once the sub-agent returns its structured output, summarize the result nicely for the user."
    ),
    sub_agents=[nutrition_tracker, profile_manager, meal_searcher]
)

# -------------------------------------------------------------
# 5. App Orchestration with Memory Event Compaction
# -------------------------------------------------------------
from google.adk.apps.app import App, EventsCompactionConfig

app = App(
    name="food_agent",
    root_agent=root_agent,
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,  # Trigger compaction every 3 turns
        overlap_size=1,        # Keep 1 turn of history for overlap context
    )
)
