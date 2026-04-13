from __future__ import annotations

import json
import re
from time import time
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.config import Settings
from app.schemas import AdminActivityItem, AdminAgentRunState, AdminChatRequest, AdminChatResponse, IntentClassification
from app.state import AdminState
from app.tools import AdminToolbox, build_tools, is_generic_follow_up


def _make_model(settings: Settings):
    if not settings.openai_key.strip():
        return None
    return ChatOpenAI(
        api_key=settings.openai_key,
        model=settings.admin_model,
        temperature=0.1,
    )


class IntentClassifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def classify(self, message: str, session_context: dict | None = None) -> IntentClassification:
        session_context = session_context or {}
        previous_route = str(session_context.get("last_route") or "").strip()
        previous_topic = str(session_context.get("last_topic") or "").strip()

        if is_generic_follow_up(message) and previous_route in {"advisory", "inspect"}:
            return IntentClassification(
                category=previous_route, intent=previous_topic or previous_route, reasoning="Follow-up reused the previous route.",
            )

        model = _make_model(self._settings)
        if model is not None:
            try:
                structured = model.with_structured_output(IntentClassification)
                return structured.invoke(
                    [
                        SystemMessage(
                            content=(
                                "Classify the admin request into one category: advisory, inspect, mutate, workflow. "
                                "Use advisory for recommendations/explanations, inspect for information lookup, "
                                "mutate for a single change, workflow for sequenced operations. "
                                "The admin may write in any language or with non-technical phrasing. "
                                "Infer intent from meaning, not exact keywords. "
                                f"Previous route: {previous_route or 'none'}. Previous topic: {previous_topic or 'none'}."
                            )
                        ),
                        HumanMessage(content=message),
                    ]
                )
            except Exception:
                pass

        return self._fallback(message, previous_route, previous_topic)

    def _fallback(self, message: str, previous_route: str, previous_topic: str) -> IntentClassification:
        lowered = message.lower()
        if is_generic_follow_up(message) and previous_route in {"advisory", "inspect"}:
            return IntentClassification(
                category=previous_route, intent=previous_topic or previous_route, reasoning="Generic follow-up reused the previous route.",
            )

        if any(token in lowered for token in ["reindex", "run evaluation", "compare evaluation", "compare reports", "réindex", "evaluer", "évaluation"]):
            category: Literal["workflow"] = "workflow"
        elif any(token in lowered for token in ["delete document", "remove document", "delete file", "change", "set", "switch", "update", "changer", "modifier", "supprimer"]):
            category = "mutate"
        elif any(token in lowered for token in ["show", "list", "status", "which documents", "what is current", "reports", "documents", "montre", "liste", "quel est", "ما هو", "اعرض"]):
            category = "inspect"
        else:
            category = "advisory"

        intent = previous_topic or category
        if "rerank" in lowered:
            intent = "reranking_strategy"
        elif "evaluation" in lowered:
            intent = "evaluation"
        elif "document" in lowered:
            intent = "documents"
        elif "cost" in lowered:
            intent = "cost_optimization"

        return IntentClassification(category=category, intent=intent, reasoning="Deterministic classifier fallback.")


def _safe_json(content: Any) -> Any:
    if isinstance(content, list):
        if len(content) == 1 and isinstance(content[0], dict) and "text" in content[0]:
            content = content[0]["text"]
        else:
            return content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return content


def _history_messages(state: AdminState) -> list:
    messages = []
    for item in state.get("chat_history", [])[-8:]:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def _fallback_advisory_answer(state: AdminState) -> str:
    message = state["message"].lower()
    if "rerank" in message and any(token in message for token in ["cost", "money", "cheap"]):
        return (
            "To save money, start without reranking. It is the cheapest option and usually the fastest. "
            "Add reranking only if retrieval quality is clearly weak. A lightweight reranker is the middle ground: "
            "better quality than no reranking, but cheaper than a heavier model."
        )
    if "rerank" in message and any(token in message for token in ["performance", "speed", "latency"]):
        return (
            "For speed, skipping reranking is usually best. Reranking improves result quality, but it adds extra work "
            "after retrieval, so responses take longer."
        )
    return (
        "The lowest-cost setup is the simplest one: fewer retrieval steps, no reranking unless quality needs it, "
        "and evaluation before changing production. If you want, I can compare that advice with your current reports or documents."
    )


def _normalize_user_answer(answer: str) -> str:
    normalized = answer.replace(".env.local", "the system configuration").replace(".env", "the system configuration")
    normalized = normalized.replace("repo config", "system configuration")
    normalized = normalized.replace("repo-backed", "current")
    normalized = normalized.replace("write that into the system configuration.local", "apply that change to the system configuration")
    return normalized


def _summarize_inspection_result(tool_result: dict[str, Any], message: str, session_context: dict) -> str:
    if not tool_result:
        last_result = session_context.get("last_result")
        if isinstance(last_result, dict):
            tool_result = last_result
        else:
            return "I could not collect live inspection data."

    if "reports" in tool_result:
        reports = tool_result.get("reports", [])
        if not reports:
            return "There are no saved evaluation reports yet."
        report_ids = [str(item.get("report_id") or "") for item in reports[:3] if isinstance(item, dict)]
        return f"I found {len(reports)} evaluation reports. Recent report IDs: {', '.join(report_ids)}."

    if "documents" in tool_result:
        documents = tool_result.get("documents", [])
        if not documents:
            return "There are no documents loaded in ingestion."
        preview = []
        for item in documents[:3]:
            if isinstance(item, dict):
                preview.append(str(item.get("original_name") or item.get("storage_path") or item.get("id") or "document"))
        return f"There are {len(documents)} documents loaded. Examples: {', '.join(preview)}."

    if "status_counts" in tool_result:
        counts = tool_result.get("status_counts", {})
        total = tool_result.get("total_documents", 0)
        embedded = tool_result.get("embedded_documents", 0)
        return f"There are {total} documents in ingestion, and {embedded} are already embedded. Status breakdown: {counts}."

    if "config" in tool_result and "scope" in tool_result:
        scope = str(tool_result.get("scope") or "config")
        config = tool_result.get("config", {})
        if isinstance(config, dict):
            parts = [f"{key}={value}" for key, value in config.items()]
            return f"The current {scope} settings are: {', '.join(parts)}."

    return f"I inspected the system and got: {tool_result}."


def _extract_dataset_path(message: str) -> str:
    match = re.search(r"([A-Za-z0-9_./-]+\.json)", message)
    return match.group(1) if match else "evals/sample_eval_dataset.json"


def _plan_mutation(message: str, toolbox: AdminToolbox) -> tuple[dict[str, Any] | None, str]:
    lowered = message.lower()
    if any(token in lowered for token in ["change", "set", "switch", "update"]) and any(
        token in lowered for token in ["chunk", "rerank", "retrieval", "embedding", "generation"]
    ):
        try:
            scope = toolbox.resolve_config_scope(message)
        except ValueError:
            scope = ""
        changes: dict[str, Any] = {}
        if scope == "preprocessing":
            size_match = re.search(r"chunk size(?:\s+to)?\s+(\d+)", lowered)
            overlap_match = re.search(r"chunk overlap(?:\s+to)?\s+(\d+)", lowered)
            if "late" in lowered:
                changes["chunk_strategy"] = "late"
            elif "overlap" in lowered:
                changes["chunk_strategy"] = "overlap"
            elif "semantic" in lowered:
                changes["chunk_strategy"] = "semantic"
            if size_match:
                changes["chunk_size"] = int(size_match.group(1))
            if overlap_match:
                changes["chunk_overlap"] = int(overlap_match.group(1))
        elif scope == "retrieval":
            if "cross_encoder" in lowered or "cross encoder" in lowered:
                changes["ranker"] = "cross_encoder"
            elif "llm_batch" in lowered or "llm rerank" in lowered:
                changes["ranker"] = "llm_batch"
            elif "no rerank" in lowered or "no reranking" in lowered or "without reranking" in lowered:
                changes["ranker"] = "none"
            topk_match = re.search(r"top k(?: retrieve)?(?:\s+to)?\s+(\d+)", lowered)
            if topk_match:
                changes["top_k_retrieve"] = int(topk_match.group(1))
        elif scope == "embedding":
            model_match = re.search(r"(text-embedding-[\\w-]+)", lowered)
            if model_match:
                changes["embedding_model"] = model_match.group(1)
        elif scope == "generation":
            model_match = re.search(r"(gpt-[\\w.-]+)", lowered)
            if model_match:
                changes["generation_model"] = model_match.group(1)

        if scope and changes:
            return (
                {
                    "intent": "mutation",
                    "tool": "update_repo_config",
                    "arguments": {"service_name": scope, "changes": changes},
                    "steps": [],
                "summary": f"Update {scope} config with {changes}.",
            },
                f"I am ready to update the {scope} settings with {changes}. Confirm if you want me to apply that change.",
            )

    if "document" in lowered and any(token in lowered for token in ["delete", "remove"]):
        guess = message
        for prefix in ["delete document", "remove document", "delete file", "remove file"]:
            guess = re.sub(prefix, "", guess, flags=re.IGNORECASE).strip(" :")
        target = toolbox.find_document(guess) if guess else None
        if target is None:
            return None, "I can delete a document if you tell me the exact document name or ID."
        summary = str(target.get("original_name") or target.get("storage_path") or target.get("id") or "document")
        return (
            {
                "intent": "mutation",
                "tool": "delete_document_completely",
                "arguments": {"document_id": str(target.get("id") or "")},
                "steps": [],
                "summary": f"Delete document '{summary}' and remove its indexed vectors.",
            },
            f"I found the document '{summary}'. Confirm if you want me to delete it and clean up its vectors.",
        )

    return None, (
        "That change is not exposed through admin-service yet. The current service can execute document deletion, reindexing, "
        "and evaluation workflows."
    )


def _plan_workflow(message: str, toolbox: AdminToolbox) -> tuple[dict[str, Any] | None, str]:
    lowered = message.lower()
    if "compare" in lowered and "evaluation" in lowered:
        pair = toolbox.resolve_report_pair(message)
        if pair is None:
            return None, "I need two evaluation report IDs to compare, or I can compare the two most recent reports if they exist."
        baseline_report_id, candidate_report_id = pair
        return (
            {
                "intent": "workflow",
                "tool": "compare_evaluation_reports",
                "arguments": {
                    "baseline_report_id": baseline_report_id,
                    "candidate_report_id": candidate_report_id,
                },
                "steps": [],
                "summary": f"Compare evaluation reports '{baseline_report_id}' and '{candidate_report_id}'.",
            },
            f"I am ready to compare report '{baseline_report_id}' against '{candidate_report_id}'. Confirm to run it.",
        )

    if "evaluation" in lowered:
        dataset_path = _extract_dataset_path(message)
        return (
            {
                "intent": "workflow",
                "tool": "run_evaluation",
                "arguments": {"dataset_path": dataset_path},
                "steps": [],
                "summary": f"Run evaluation with dataset '{dataset_path}'.",
            },
            f"I am ready to run the evaluation with '{dataset_path}'. Confirm to start it.",
        )

    if "reindex" in lowered and any(token in lowered for token in ["all", "validated", "documents"]):
        return (
            {
                "intent": "workflow",
                "tool": "reindex_validated_documents",
                "arguments": {},
                "steps": [],
                "summary": "Reindex every validated document currently tracked by ingestion.",
            },
            "I am ready to reindex every validated document. Confirm to start the workflow.",
        )

    if "reindex" in lowered:
        guess = re.sub("reindex", "", message, flags=re.IGNORECASE).strip(" :")
        target = toolbox.find_document(guess) if guess else None
        if target is None:
            return None, "I can reindex one document if you tell me the exact document name or ID."
        summary = str(target.get("original_name") or target.get("storage_path") or target.get("id") or "document")
        return (
            {
                "intent": "workflow",
                "tool": "reindex_document",
                "arguments": {"document_id": str(target.get("id") or "")},
                "steps": [],
                "summary": f"Reindex document '{summary}'.",
            },
            f"I found the document '{summary}'. Confirm if you want me to rebuild its embeddings.",
        )

    return None, "I could not map that workflow to a supported operation yet."


def _run_llm_tool_loop(
    *,
    settings: Settings,
    tools: list,
    system_prompt: str,
    state: AdminState,
) -> tuple[str, dict[str, Any] | None, list[dict], int, dict[str, dict]]:
    model = _make_model(settings)
    if model is None:
        return "", None, [], 0, {}

    tool_node = ToolNode(tools)
    bound_model = model.bind_tools(tools)
    messages = [SystemMessage(content=system_prompt), *_history_messages(state), HumanMessage(content=state["message"])]
    activity: list[dict] = []
    last_tool_result: dict[str, Any] | None = None
    tool_call_count = 0
    cache_updates: dict[str, dict] = {}
    cached_results = state.get("tool_cache", {}) if isinstance(state.get("tool_cache"), dict) else {}

    for _ in range(settings.max_tool_calls):
        ai_message = bound_model.invoke(messages)
        messages.append(ai_message)
        if not getattr(ai_message, "tool_calls", None):
            return str(ai_message.content or ""), last_tool_result, activity, tool_call_count, cache_updates

        resolved_messages: list[ToolMessage] = []
        uncached_calls = []
        for tool_call in ai_message.tool_calls:
            cache_key = json.dumps({"name": tool_call["name"], "args": tool_call.get("args", {})}, sort_keys=True)
            cached_entry = cached_results.get(cache_key)
            if isinstance(cached_entry, dict):
                ttl_seconds = int(cached_entry.get("ttl_seconds", 0) or 0)
                created_at = float(cached_entry.get("created_at", 0) or 0)
                if ttl_seconds <= 0 or time() - created_at <= ttl_seconds:
                    payload = cached_entry.get("result")
                    resolved_messages.append(
                        ToolMessage(
                            content=json.dumps(payload) if isinstance(payload, dict) else str(payload),
                            tool_call_id=tool_call["id"],
                            name=tool_call["name"],
                        )
                    )
                    if isinstance(payload, dict):
                        last_tool_result = payload
                    else:
                        last_tool_result = {"raw": payload}
                    activity.append(
                        {
                            "phase": "tool",
                            "status": "completed",
                            "title": f"Tool reused from memory: {tool_call['name']}",
                            "detail": "The agent reused recently collected information instead of calling the service again.",
                            "tool": tool_call["name"],
                            "arguments": tool_call.get("args", {}),
                        }
                    )
                    continue
            uncached_calls.append(tool_call)

        if uncached_calls:
            tool_response = tool_node.invoke({"messages": [AIMessage(content="", tool_calls=uncached_calls)]})
            for item in tool_response.get("messages", []):
                if isinstance(item, ToolMessage):
                    resolved_messages.append(item)

        for item in resolved_messages:
            if isinstance(item, ToolMessage):
                tool_call_count += 1
                payload = _safe_json(item.content)
                if isinstance(payload, dict):
                    last_tool_result = payload
                else:
                    last_tool_result = {"raw": payload}
                if not any(entry.get("title") == f"Tool reused from memory: {item.name}" for entry in activity[-1:]):
                    activity.append(
                        {
                            "phase": "tool",
                            "status": "completed",
                            "title": f"Tool executed: {item.name}",
                            "detail": "The agent collected data from a live service.",
                            "tool": item.name,
                            "arguments": {},
                        }
                    )
                tool_call = next((call for call in ai_message.tool_calls if call["id"] == item.tool_call_id), None)
                if tool_call and isinstance(last_tool_result, dict):
                    cache_key = json.dumps({"name": item.name, "args": tool_call.get("args", {})}, sort_keys=True)
                    ttl_seconds, tags = _tool_cache_policy(item.name)
                    cache_updates[cache_key] = {
                        "tool": item.name,
                        "args": tool_call.get("args", {}),
                        "result": last_tool_result,
                        "created_at": time(),
                        "ttl_seconds": ttl_seconds,
                        "tags": tags,
                    }
                    cached_results[cache_key] = cache_updates[cache_key]
                messages.append(item)

    return "I hit the tool-call limit before finishing the answer.", last_tool_result, activity, tool_call_count, cache_updates


def _tool_cache_policy(tool_name: str) -> tuple[int, list[str]]:
    if tool_name == "get_repo_config":
        return 600, ["config"]
    if tool_name in {"get_ingestion_status", "list_loaded_documents"}:
        return 90, ["documents", "ingestion"]
    if tool_name == "list_evaluation_reports":
        return 180, ["evaluation_reports"]
    return 60, [tool_name]


def build_graph(settings: Settings, access_token: str | None = None):
    graph = StateGraph(AdminState)
    classifier = IntentClassifier(settings)

    def classify_intent(state: AdminState) -> AdminState:
        try:
            result = classifier.classify(state["message"], state.get("session_context"))
        except TypeError:
            result = classifier.classify(state["message"])
        activity = list(state.get("activity", []))
        activity.append(
            {
                "phase": "classify",
                "status": "completed",
                "title": "Intent classified",
                "detail": result.reasoning,
                "arguments": {"category": result.category, "intent": result.intent},
            }
        )
        return {
            **state,
            "route": result.category,
            "intent": result.intent,
            "status": "running",
            "activity": activity,
            "current_step": "route",
        }

    def advisory_node(state: AdminState) -> AdminState:
        toolbox = AdminToolbox(settings, access_token=state.get("access_token") or access_token)
        read_tools = build_tools(toolbox, include_mutations=False)
        answer, tool_result, tool_activity, tool_call_count, cache_updates = _run_llm_tool_loop(
            settings=settings,
            tools=read_tools,
            system_prompt=(
                "You are an admin copilot speaking to a non-technical operator who only pilots the system from chat. "
                "The admin does not see source code, environment files, or implementation details. "
                "Answer in the user's language when possible, in plain language, and never mention graph nodes, branches, code files, env files, or internal implementation. "
                "If the question is conceptual, answer directly. If current system state or current configuration would materially improve the answer, use tools."
            ),
            state=state,
        )
        if not answer:
            answer = _fallback_advisory_answer(state)
        answer = _normalize_user_answer(answer)

        activity = list(state.get("activity", []))
        activity.extend(tool_activity)
        activity.append(
            {
                "phase": "advisory",
                "status": "completed",
                "title": "Advice prepared",
                "detail": "The request was answered for a non-technical admin.",
                "arguments": {},
            }
        )
        return {
            **state,
            "status": "completed",
            "final_answer": answer,
            "current_step": "summarize",
            "activity": activity,
            "tool_result": tool_result,
            "tool_call_count": tool_call_count,
            "tool_cache_updates": cache_updates,
        }

    def inspect_node(state: AdminState) -> AdminState:
        toolbox = AdminToolbox(settings, access_token=state.get("access_token") or access_token)
        read_tools = build_tools(toolbox, include_mutations=False)
        activity = list(state.get("activity", []))
        try:
            answer, tool_result, tool_activity, tool_call_count, cache_updates = _run_llm_tool_loop(
                settings=settings,
                tools=read_tools,
                system_prompt=(
                    "You inspect live system state for a non-technical admin who only pilots the system from chat. "
                    "Use tools when needed, then summarize concrete facts plainly in the user's language when possible. "
                    "If the user message is a generic follow-up, use prior context. "
                    "Use get_repo_config for current settings like chunking, reranking, embedding, or generation config. "
                    "Never mention code files, env files, repositories, or implementation details."
                ),
                state=state,
            )
        except Exception as exc:
            answer = ""
            tool_result = {"status": "error", "detail": str(exc)}
            tool_activity = []
            tool_call_count = 0
            cache_updates = {}

        if (not tool_result or tool_result.get("status") == "error") and any(
            token in state["message"].lower()
            for token in ["chunk", "rerank", "reranking", "retrieval", "embedding model", "generation model", "config"]
        ):
            try:
                scope = toolbox.resolve_config_scope(state["message"])
                tool_result = toolbox.get_repo_config(scope)
                tool_activity.append(
                    {
                        "phase": "tool",
                        "status": "completed",
                        "title": f"Tool executed: get_repo_config ({scope})",
                        "detail": "The agent read repo-backed config values.",
                        "tool": "get_repo_config",
                        "arguments": {"service_name": scope},
                    }
                )
            except Exception:
                pass

        if not answer:
            answer = _summarize_inspection_result(tool_result or {}, state["message"], state.get("session_context", {}))
        answer = _normalize_user_answer(answer)

        activity.extend(tool_activity)
        activity.append(
            {
                "phase": "inspect",
                "status": "completed" if tool_result is not None else "failed",
                "title": "Inspection finished",
                "detail": "Live system information was prepared for the admin." if tool_result is not None else "Inspection had no usable data.",
                "arguments": {},
            }
        )
        return {
            **state,
            "status": "completed",
            "final_answer": answer,
            "current_step": "summarize",
            "activity": activity,
            "tool_result": tool_result,
            "tool_call_count": tool_call_count,
            "tool_cache_updates": cache_updates,
        }

    def mutate_node(state: AdminState) -> AdminState:
        toolbox = AdminToolbox(settings, access_token=state.get("access_token") or access_token)
        pending_action, answer = _plan_mutation(state["message"], toolbox)
        activity = list(state.get("activity", []))
        activity.append(
            {
                "phase": "mutate",
                "status": "completed" if pending_action else "failed",
                "title": "Mutation planned" if pending_action else "Mutation unsupported",
                "detail": answer,
                "tool": (pending_action or {}).get("tool"),
                "arguments": (pending_action or {}).get("arguments", {}),
            }
        )
        return {
            **state,
            "status": "completed",
            "requires_confirmation": pending_action is not None,
            "pending_action": pending_action,
            "final_answer": _normalize_user_answer(answer),
            "current_step": "summarize",
            "activity": activity,
        }

    def workflow_node(state: AdminState) -> AdminState:
        toolbox = AdminToolbox(settings, access_token=state.get("access_token") or access_token)
        pending_action, answer = _plan_workflow(state["message"], toolbox)
        activity = list(state.get("activity", []))
        activity.append(
            {
                "phase": "workflow",
                "status": "completed" if pending_action else "failed",
                "title": "Workflow planned" if pending_action else "Workflow could not be planned",
                "detail": answer,
                "tool": (pending_action or {}).get("tool"),
                "arguments": (pending_action or {}).get("arguments", {}),
            }
        )
        return {
            **state,
            "status": "completed",
            "requires_confirmation": pending_action is not None,
            "pending_action": pending_action,
            "final_answer": _normalize_user_answer(answer),
            "current_step": "summarize",
            "activity": activity,
        }

    def summarize(state: AdminState) -> AdminState:
        activity = list(state.get("activity", []))
        activity.append(
            {
                "phase": "summarize",
                "status": "completed",
                "title": "Response prepared",
                "detail": "The graph produced a user-facing response.",
                "arguments": {},
            }
        )
        return {**state, "activity": activity, "status": "completed", "current_step": None}

    def route(state: AdminState) -> str:
        return str(state.get("route") or "advisory")

    graph.add_node("classify_intent_llm", classify_intent)
    graph.add_node("advisory_agent", advisory_node)
    graph.add_node("inspect_agent", inspect_node)
    graph.add_node("mutate_executor", mutate_node)
    graph.add_node("workflow_executor", workflow_node)
    graph.add_node("summarize_llm", summarize)

    graph.add_edge(START, "classify_intent_llm")
    graph.add_conditional_edges(
        "classify_intent_llm",
        route,
        {
            "advisory": "advisory_agent",
            "inspect": "inspect_agent",
            "mutate": "mutate_executor",
            "workflow": "workflow_executor",
        },
    )
    graph.add_edge("advisory_agent", "summarize_llm")
    graph.add_edge("inspect_agent", "summarize_llm")
    graph.add_edge("mutate_executor", "summarize_llm")
    graph.add_edge("workflow_executor", "summarize_llm")
    graph.add_edge("summarize_llm", END)
    return graph.compile()


def get_graph_mermaid(settings: Settings) -> str:
    compiled = build_graph(settings)
    return compiled.get_graph().draw_mermaid()


def run_graph(payload: AdminChatRequest, settings: Settings, session_context: dict | None = None) -> AdminChatResponse:
    app = build_graph(settings, access_token=payload.access_token)
    final_state = app.invoke(
        {
            "session_id": payload.session_id,
            "message": payload.message,
            "selected_mode": payload.selected_mode,
            "access_token": payload.access_token,
            "status": "running",
            "activity": [],
            "requires_confirmation": False,
            "chat_history": [item.model_dump() for item in payload.chat_history],
            "session_context": session_context or {},
            "tool_call_count": 0,
            "tool_cache": session_context.get("tool_cache", {}) if isinstance(session_context, dict) else {},
        }
    )

    activity_items = [AdminActivityItem(**item) for item in final_state.get("activity", [])]
    answer = str(final_state.get("final_answer") or "")
    requires_confirmation = bool(final_state.get("requires_confirmation", False))
    pending_action = final_state.get("pending_action")
    route = str(final_state.get("route") or "advisory")
    intent = str(final_state.get("intent") or route)
    tool_result = final_state.get("tool_result")
    tool_call_count = int(final_state.get("tool_call_count") or 0)
    tool_cache_updates = final_state.get("tool_cache_updates", {})

    return AdminChatResponse(
        status="needs_confirmation" if requires_confirmation else "ok",
        mode=route,
        selected_mode=payload.selected_mode,
        session_id=payload.session_id,
        message=payload.message,
        answer=answer,
        intent=intent,
        tool=(pending_action or {}).get("tool") if isinstance(pending_action, dict) else None,
        arguments=(pending_action or {}).get("arguments", {}) if isinstance(pending_action, dict) else {},
        requires_confirmation=requires_confirmation,
        executed=False,
        pending_action=pending_action,
        citations=[],
        thinking_summary=f"Request routed through the {route} branch.",
        activity=activity_items,
        result={"route": route, "tool_result": tool_result, "tool_cache_updates": tool_cache_updates},
        agent_run=AdminAgentRunState(
            status="paused_for_confirmation" if requires_confirmation else "completed",
            iteration_count=1,
            tool_call_count=tool_call_count,
            max_iterations=settings.max_iterations,
            max_tool_calls=settings.max_tool_calls,
            facts={"route": route, "intent": intent},
            observations=[],
            decision_history=[],
            proposed_steps=[],
            pending_confirmation=pending_action if requires_confirmation else None,
            final_answer=answer,
            stop_reason="branch_completed",
        ),
    )
