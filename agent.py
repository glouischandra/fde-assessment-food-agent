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
    model=TASK_MODEL,
    name='nutrition_tracker',
    description='Specializes in logging user food intake, estimating calories, and checking daily nutrition totals.',
    mode='task',
    output_schema=NutritionTrackerResult,
    instruction=(
        "You are a nutrition log agent. You have access to get_user_profile, get_daily_intake, save_nutrition_log, and finish_task tools.\n"
        "Your task is to log a user's meal intake.\n"
        "Follow these rules strictly:\n"
        "1. First, call get_user_profile and get_daily_intake to find the user's calorie targets and current logged intake.\n"
        "2. If calorie count is not specified by the user, estimate the calories and macros yourself immediately.\n"
        "3. Before saving the log, ask the user for permission. State the food details, estimated calories, and projected new daily total.\n"
        "   Do NOT call the save_nutrition_log tool until they grant permission in a subsequent turn.\n"
        "4. Once permission is granted, call save_nutrition_log to save the entry.\n"
        "5. Once finished, call finish_task to return the log details.\n"
        "CRITICAL: Do NOT write any Python code, markdown code blocks, or print statements. You must only interact by calling the provided tools directly."
    ),
    tools=[get_user_profile, save_nutrition_log, get_daily_intake]
)

# -------------------------------------------------------------
# 2. Preference Profiler / Profile Manager Sub-Agent (Task Mode)
# -------------------------------------------------------------
profile_manager = Agent(
    model=TASK_MODEL,
    name='profile_manager',
    description='Specializes in updating and retrieving user profiles, cuisine interests (Asian, American, French), and dietary restrictions.',
    mode='task',
    output_schema=ProfileManagerResult,
    instruction=(
        "You are a profile manager agent. You have access to get_user_profile and update_user_profile tools.\n"
        "Your task is to fetch or update the user's calorie targets, dietary restrictions, and cuisine preferences.\n"
        "Follow these rules strictly:\n"
        "1. To read the profile, invoke the get_user_profile tool. Do NOT write python code or wrap it in print(). Simply call the tool.\n"
        "2. To update the profile, invoke the update_user_profile tool.\n"
        "3. Once finished, invoke the finish_task tool to return the final profile, updated_fields, and status.\n"
        "CRITICAL: Do NOT write any Python code, markdown code blocks, or print statements. You must only interact by calling the provided tools directly."
    ),
    tools=[get_user_profile, update_user_profile]
)

# -------------------------------------------------------------
# 3. Meal & Restaurant Search Sub-Agent (Task Mode)
# -------------------------------------------------------------
meal_searcher = Agent(
    model=TASK_MODEL,
    name='meal_searcher',
    description='Specializes in recommending recipes or finding D.C. area restaurants that fit within the user\'s daily calorie limit.',
    mode='task',
    output_schema=MealSearcherResult,
    instruction=(
        "You are a meal recommendation agent. You have access to get_user_profile, get_daily_intake, google_search_restaurants, analyze_menu_nutrition, and finish_task tools.\n"
        "Your task is to recommend a recipe or a restaurant under the user's daily calorie target.\n"
        "Follow these rules strictly:\n"
        "1. Fetch the user profile and daily intake to find the remaining calorie budget.\n"
        "2. For restaurants, ask the user for permission stating the target cuisine and neighborhood before calling google_search_restaurants. Once granted, call google_search_restaurants and analyze_menu_nutrition.\n"
        "3. For recipes, generate a recipe under their remaining calorie budget.\n"
        "4. Once finished, call finish_task to return recommendations.\n"
        "CRITICAL: Do NOT write any Python code, markdown code blocks, or print statements. You must only interact by calling the provided tools directly."
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

from .trace_logging import logger
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.apps.compaction import _run_compaction_for_sliding_window
from google.adk.agents.callback_context import CallbackContext

compaction_config = EventsCompactionConfig(
    compaction_interval=3,  # Trigger compaction every 3 turns
    overlap_size=1,        # Keep 1 turn of history for overlap context
)

async def run_compaction_bg(session, session_service):
    from copy import copy
    temp_app = copy(app)
    temp_app.events_compaction_config = compaction_config
    try:
        await _run_compaction_for_sliding_window(
            app=temp_app,
            session=session,
            session_service=session_service,
        )
        logger.info("Background sliding window event compaction completed successfully.")
    except Exception as e:
        logger.error(f"Background event compaction failed: {e}")

async def async_compaction_callback(ctx: CallbackContext):
    inv_ctx = ctx._invocation_context
    # Run the compaction as a non-blocking background task.
    asyncio.create_task(run_compaction_bg(inv_ctx.session, inv_ctx.session_service))

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
    after_agent_callback=[async_compaction_callback],
    sub_agents=[nutrition_tracker, profile_manager, meal_searcher]
)

# App Orchestration (Compaction is offloaded to the callback above to execute in background)
app = App(
    name="food_agent",
    root_agent=root_agent,
)
