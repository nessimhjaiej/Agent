from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.agent.memory import AgentRunStateStore  # noqa: E402
from app.agent.state import (  # noqa: E402
    AgentDecision,
    AgentGoal,
    AgentObservation,
    AgentPendingConfirmation,
    AgentRunState,
)


def test_agent_run_state_store_round_trips_state(tmp_path: Path) -> None:
    store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    state = AgentRunState(
        run_id="run-1",
        goal=AgentGoal(
            message="Recommend a reranker.",
            subject="reranking",
            desired_outcome="select the best reranker",
            constraints=["low cost"],
            success_criteria=["recommend one supported option"],
        ),
        status="paused_for_confirmation",
        iteration_count=2,
        tool_call_count=1,
        facts={"default_ranker": "cross_encoder"},
        observations=[
            AgentObservation(
                source="get_reranker_config",
                content="Loaded current reranker configuration.",
                data={"default_ranker": "cross_encoder", "rerank_top_n": 20},
            )
        ],
        decision_history=[
            AgentDecision(
                action_type="call_tool",
                tool_name="get_reranker_config",
                reason="Need current state before recommending.",
                expected_observation="Current reranker config.",
            )
        ],
        proposed_steps=[
            {
                "tool": "update_reranker_config",
                "arguments": {"default_ranker": "cross_encoder", "rerank_top_n": 10},
            }
        ],
        pending_confirmation=AgentPendingConfirmation(
            tool_name="update_reranker_config",
            arguments={"default_ranker": "cross_encoder", "rerank_top_n": 10},
            reason="Changing reranker config mutates system state.",
        ),
        final_answer="I recommend switching to cross_encoder with top_n=10.",
        stop_reason="confirmation_required",
    )

    store.save("admin-session-1", state)
    loaded = store.load("admin-session-1")

    assert loaded is not None
    assert loaded.run_id == "run-1"
    assert loaded.goal is not None
    assert loaded.goal.subject == "reranking"
    assert loaded.observations[0].source == "get_reranker_config"
    assert loaded.pending_confirmation is not None
    assert loaded.pending_confirmation.tool_name == "update_reranker_config"
    assert loaded.proposed_steps[0]["tool"] == "update_reranker_config"


def test_agent_run_state_store_deletes_session_state(tmp_path: Path) -> None:
    store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    store.save(
        "admin-session-1",
        AgentRunState(goal=AgentGoal(message="Recommend a reranker.")),
    )

    assert store.load("admin-session-1") is not None
    store.delete("admin-session-1")
    assert store.load("admin-session-1") is None


def test_agent_run_state_store_returns_none_for_unknown_session(tmp_path: Path) -> None:
    store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")

    assert store.load("missing-session") is None
