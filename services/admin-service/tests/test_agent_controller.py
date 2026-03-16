from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.agent.controller import RecursiveAgentController  # noqa: E402
from app.agent.state import AgentDecision, AgentGoal, AgentObservation, AgentRunState  # noqa: E402


def test_recursive_controller_runs_tool_then_responds() -> None:
    decisions = iter(
        [
            AgentDecision(
                action_type="call_tool",
                tool_name="get_reranker_config",
                reason="Need current state.",
                expected_observation="Current reranker configuration.",
            ),
            AgentDecision(
                action_type="respond",
                message="I inspected the current reranker configuration and I am ready to recommend a next step.",
            ),
        ]
    )

    controller = RecursiveAgentController(
        policy=lambda state: next(decisions),
        tool_executor=lambda tool_name, arguments: AgentObservation(
            source=tool_name,
            content="Read current reranker config.",
            data={"default_ranker": "cross_encoder", "rerank_top_n": 20},
        ),
    )

    state = AgentRunState(goal=AgentGoal(message="Recommend a reranker."))
    result = controller.run(state)

    assert result.status == "completed"
    assert result.iteration_count == 2
    assert result.tool_call_count == 1
    assert result.observations[0].source == "get_reranker_config"
    assert "ready to recommend" in result.final_answer
    assert result.stop_reason == "responded"


def test_recursive_controller_pauses_for_confirmation() -> None:
    controller = RecursiveAgentController(
        policy=lambda state: AgentDecision(
            action_type="request_confirmation",
            message="I recommend switching to cross_encoder. Confirm to apply it.",
            tool_name="update_reranker_config",
            arguments={"default_ranker": "cross_encoder", "rerank_top_n": 10},
            reason="Changing reranker config mutates system state.",
        ),
        tool_executor=lambda tool_name, arguments: AgentObservation(source=tool_name),
    )

    state = AgentRunState(goal=AgentGoal(message="Apply the best reranker."))
    result = controller.run(state)

    assert result.status == "paused_for_confirmation"
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.tool_name == "update_reranker_config"
    assert result.pending_confirmation.arguments["default_ranker"] == "cross_encoder"
    assert result.stop_reason == "confirmation_required"


def test_recursive_controller_blocks_when_iteration_budget_is_exhausted() -> None:
    controller = RecursiveAgentController(
        policy=lambda state: AgentDecision(action_type="call_tool", tool_name="get_reranker_config"),
        tool_executor=lambda tool_name, arguments: AgentObservation(source=tool_name),
    )

    state = AgentRunState(
        goal=AgentGoal(message="Keep inspecting forever."),
        max_iterations=1,
        max_tool_calls=3,
    )
    result = controller.run(state)

    assert result.status == "blocked"
    assert result.stop_reason == "max_iterations_reached"


def test_recursive_controller_fails_when_tool_raises() -> None:
    controller = RecursiveAgentController(
        policy=lambda state: AgentDecision(action_type="call_tool", tool_name="get_reranker_config"),
        tool_executor=lambda tool_name, arguments: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    state = AgentRunState(goal=AgentGoal(message="Inspect reranker config."))
    result = controller.run(state)

    assert result.status == "failed"
    assert result.stop_reason == "tool_execution_failed"
    assert result.observations[0].data["error"] == "boom"
