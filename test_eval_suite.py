import asyncio
import os
import unittest
from dotenv import load_dotenv

# Load environment variables from .env before importing agent
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import sys
# Add parent directory of food_agent to sys.path to resolve relative imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from google.adk.evaluation.eval_config import get_evaluation_criteria_or_default, get_eval_metrics_from_config
from google.adk.evaluation.in_memory_eval_sets_manager import InMemoryEvalSetsManager
from google.adk.evaluation.local_eval_sets_manager import load_eval_set_from_file
from google.adk.evaluation.local_eval_service import LocalEvalService
from google.adk.evaluation.metric_evaluator_registry import DEFAULT_METRIC_EVALUATOR_REGISTRY
from google.adk.evaluation.simulation.user_simulator_provider import UserSimulatorProvider
from google.adk.evaluation.base_eval_service import InferenceRequest, InferenceConfig
from google.adk.cli.cli_eval import _collect_inferences, _collect_eval_results
from google.adk.evaluation.evaluator import EvalStatus

# Import our agent module as a package
from food_agent.agent import root_agent

class FoodAgentEvalSuite(unittest.IsolatedAsyncioTestCase):
    async def test_food_agent_eval_set(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, "eval_config.json")
        eval_set_path = os.path.join(base_dir, "food_agent_eval_set.json")
        
        # Load config and metrics
        eval_config = get_evaluation_criteria_or_default(config_path)
        eval_metrics = get_eval_metrics_from_config(eval_config)
        
        # Load eval cases from food_agent_eval_set.json
        eval_set = load_eval_set_from_file(eval_set_path, eval_set_path)
        
        # Create InMemory eval manager
        eval_sets_manager = InMemoryEvalSetsManager()
        eval_sets_manager.create_eval_set(app_name="food_agent", eval_set_id=eval_set.eval_set_id)
        for eval_case in eval_set.eval_cases:
            eval_sets_manager.add_eval_case(
                app_name="food_agent",
                eval_set_id=eval_set.eval_set_id,
                eval_case=eval_case
            )
            
        inference_request = InferenceRequest(
            app_name="food_agent",
            eval_set_id=eval_set.eval_set_id,
            eval_case_ids=[],
            inference_config=InferenceConfig()
        )
        
        user_simulator_provider = UserSimulatorProvider(
            user_simulator_config=eval_config.user_simulator_config
        )
        
        eval_service = LocalEvalService(
            root_agent=root_agent,
            eval_sets_manager=eval_sets_manager,
            eval_set_results_manager=None,  # Don't write history json files during test runs
            user_simulator_provider=user_simulator_provider,
            metric_evaluator_registry=DEFAULT_METRIC_EVALUATOR_REGISTRY
        )
        
        inference_results = await _collect_inferences(
            inference_requests=[inference_request],
            eval_service=eval_service
        )
        
        eval_results = await _collect_eval_results(
            inference_results=inference_results,
            eval_service=eval_service,
            eval_metrics=eval_metrics
        )
        
        # Check that all test cases passed
        failed_cases = []
        for eval_result in eval_results:
            if eval_result.final_eval_status != EvalStatus.PASSED:
                failed_cases.append(eval_result.eval_id)
                
        self.assertEqual(len(failed_cases), 0, f"Evaluation failed for cases: {failed_cases}")

if __name__ == "__main__":
    unittest.main()
