from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.agent.policy import LLMToolCatalogPolicy  # noqa: E402
from app.agent.state import AgentGoal, AgentRunState  # noqa: E402
from app.tools.base import ToolMetadata  # noqa: E402


class _FakePlannerClient:
    def __init__(self, payload: str, raises: bool = False) -> None:
        self._payload = payload
        self._raises = raises

    def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        assert "recursive planning policy for an admin agent" in system_prompt
        assert "tool_catalog" in user_prompt
        if self._raises:
            raise RuntimeError("boom")
        return self._payload


def test_llm_tool_catalog_policy_selects_read_only_tool() -> None:
    policy = LLMToolCatalogPolicy(
        client=_FakePlannerClient(
            """
            {
              "action_type": "call_tool",
              "message": "Inspect the current chunking strategy catalog first.",
              "tool_name": "get_chunking_strategy_catalog",
              "arguments": {},
              "reason": "Need grounded chunking options before recommending one.",
              "expected_observation": "Current chunking config and available strategies.",
              "goal_subject": "chunking",
              "proposed_steps": []
            }
            """
        ),
        tool_catalog=[
            ToolMetadata(name="get_chunking_strategy_catalog", description="Chunking catalog", requires_confirmation=False),
            ToolMetadata(name="update_chunking_config", description="Update chunking", requires_confirmation=True),
        ],
    )

    state = AgentRunState(goal=AgentGoal(message="Which chunking strategy should I use?"))
    decision = policy(state)

    assert decision.action_type == "call_tool"
    assert decision.tool_name == "get_chunking_strategy_catalog"
    assert state.goal is not None
    assert state.goal.subject == "chunking"


def test_llm_tool_catalog_policy_accepts_confirmation_for_mutation() -> None:
    policy = LLMToolCatalogPolicy(
        client=_FakePlannerClient(
            """
            {
              "action_type": "request_confirmation",
              "message": "I recommend switching to overlap chunking with a larger chunk size. Confirm to apply it.",
              "tool_name": "update_chunking_config",
              "arguments": {
                "chunk_strategy": "overlap",
                "chunk_size": 1200,
                "chunk_overlap": 64
              },
              "reason": "This lowers chunk count and overall processing cost.",
              "expected_observation": "Updated chunking config and rollback payload.",
              "goal_subject": "chunking",
              "proposed_steps": [
                {
                  "tool": "update_chunking_config",
                  "arguments": {
                    "chunk_strategy": "overlap",
                    "chunk_size": 1200,
                    "chunk_overlap": 64
                  }
                }
              ]
            }
            """
        ),
        tool_catalog=[
            ToolMetadata(name="update_chunking_config", description="Update chunking", requires_confirmation=True),
        ],
    )

    state = AgentRunState(goal=AgentGoal(message="Apply the best low-cost chunking setup."))
    decision = policy(state)

    assert decision.action_type == "request_confirmation"
    assert decision.tool_name == "update_chunking_config"
    assert state.proposed_steps[0]["tool"] == "update_chunking_config"


def test_llm_tool_catalog_policy_rejects_direct_mutation_tool_calls() -> None:
    policy = LLMToolCatalogPolicy(
        client=_FakePlannerClient(
            """
            {
              "action_type": "call_tool",
              "message": "Apply the chunking change directly.",
              "tool_name": "update_chunking_config",
              "arguments": {
                "chunk_strategy": "overlap"
              },
              "reason": "Try to update immediately.",
              "expected_observation": "Updated config.",
              "goal_subject": "chunking",
              "proposed_steps": []
            }
            """
        ),
        tool_catalog=[
            ToolMetadata(name="update_chunking_config", description="Update chunking", requires_confirmation=True),
        ],
    )

    decision = policy(AgentRunState(goal=AgentGoal(message="Change chunking.")))

    assert decision.action_type == "stop"
    assert decision.reason == "fallback_legacy_planner"


def test_llm_tool_catalog_policy_falls_back_to_legacy_when_client_fails() -> None:
    policy = LLMToolCatalogPolicy(
        client=_FakePlannerClient("", raises=True),
        tool_catalog=[ToolMetadata(name="get_pipeline_status", description="Get pipeline status")],
    )

    decision = policy(AgentRunState(goal=AgentGoal(message="Show me pipeline status.")))

    assert decision.action_type == "stop"
    assert decision.reason == "fallback_legacy_planner"
