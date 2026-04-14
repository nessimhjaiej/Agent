from __future__ import annotations

import json
import re
from time import time
from typing import Any, Callable, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field
from pydantic import BaseModel, Field

from app.config import Settings
from app.schemas import AdminActivityItem, AdminAgentRunState, AdminChatRequest, AdminChatResponse, IntentClassification
from app.state import AdminState
from app.tools import AdminToolbox, build_tools, is_generic_follow_up


ProgressCallback = Callable[[dict[str, Any]], None]


class SemanticActionPlan(BaseModel):
    action_type: str = Field(
        default="none",
        pattern="^(none|update_config|delete_document|reindex_document|reindex_validated_documents|run_evaluation|compare_evaluation_reports)$",
    )
    service_name: str | None = Field(default=None, pattern="^(preprocessing|retrieval|embedding|generation)$")
    changes: dict[str, Any] = Field(default_factory=dict)
    document_query: str | None = None
    dataset_path: str | None = None
    baseline_report_id: str | None = None
    candidate_report_id: str | None = None
    reasoning: str = ""


class SemanticActionPlan(BaseModel):
    action_type: str = Field(
        default="none",
        pattern="^(none|update_config|delete_document|reindex_document|reindex_validated_documents|run_evaluation|compare_evaluation_reports)$",
    )
    service_name: str | None = Field(default=None, pattern="^(preprocessing|retrieval|embedding|generation)$")
    changes: dict[str, Any] = Field(default_factory=dict)
    document_query: str | None = None
    dataset_path: str | None = None
    baseline_report_id: str | None = None
    candidate_report_id: str | None = None
    reasoning: str = ""


def _progress_item(
    *,
    phase: str,
    status: str,
    title: str,
    detail: str,
    tool: str | None = None,
    arguments: dict | None = None,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "status": status,
        "title": title,
        "detail": detail,
        "tool": tool,
        "arguments": arguments or {},
    }


def _emit_progress(progress_callback: ProgressCallback | None, item: dict[str, Any]) -> None:
    if progress_callback is not None:
        progress_callback(item)


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
                structured = model.with_structured_output(IntentClassification, method="function_calling")
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

        if _is_chunking_methods_question(message) or _is_reranking_methods_question(message):
            category: Literal["inspect"] = "inspect"
        elif any(token in lowered for token in ["reindex", "run evaluation", "compare evaluation", "compare reports", "réindex", "evaluer", "évaluation"]):
            category: Literal["workflow"] = "workflow"
        elif any(token in lowered for token in ["delete document", "remove document", "delete file", "change", "set", "switch", "update", "changer", "modifier", "remplacer", "supprimer"]):
            category = "mutate"
        elif (
            any(token in lowered for token in ["config", "configuration", "settings", "current", "what is the current"])
            and any(
                token in lowered
                for token in ["chunk", "rerank", "retrieval", "embedding", "generation", "top k", "temperature", "model"]
            )
        ):
            category = "inspect"
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
        elif "chunk" in lowered:
            intent = "chunking"
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


def _serialize_chat_history(chat_history: list[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in chat_history:
        if hasattr(item, "model_dump"):
            serialized.append(item.model_dump())
        elif isinstance(item, dict):
            serialized.append(
                {
                    "role": str(item.get("role") or ""),
                    "content": str(item.get("content") or ""),
                }
            )
    return serialized


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


def _prefers_french(message: str) -> bool:
    lowered = message.lower()
    return bool(
        re.search(r"[àâçéèêëîïôùûü]", lowered)
        or any(
            token in lowered
            for token in [
                "quelle",
                "quelles",
                "strategie",
                "stratég",
                "rempla",
                "changer",
                "modifier",
                "mettre",
                "taille",
                "actuelle",
                "disponibles",
            ]
        )
    )


def _is_chunking_methods_question(message: str) -> bool:
    lowered = message.lower()
    if any(token in lowered for token in ["chunk_strategy", "chunk_size", "chunk_overlap"]):
        return False
    asks_about_chunking = bool(re.search(r"\b(chunking|chunk|chunks)\b", lowered))
    asks_for_options = bool(re.search(r"\b(available|supported|methods|method|strategies|options|types)\b", lowered))
    return asks_about_chunking and asks_for_options


def _is_reranking_methods_question(message: str) -> bool:
    lowered = message.lower()
    if "default_ranker_type" in lowered:
        return False
    if any(token in lowered for token in ["change", "set", "switch", "update"]):
        return False
    asks_about_reranking = bool(re.search(r"\b(rerank|reranking|reranker|ranker|ranking)\b", lowered))
    asks_for_options = bool(re.search(r"\b(available|supported|methods|strategies|options|types)\b", lowered))
    return asks_about_reranking and asks_for_options


def _summarize_inspection_result(tool_result: dict[str, Any], message: str, session_context: dict) -> str:
    prefers_french = _prefers_french(message)
    if not tool_result:
        last_result = session_context.get("last_result")
        if isinstance(last_result, dict):
            tool_result = last_result
        else:
            return "Je n'ai pas pu collecter les informations d'inspection en direct." if prefers_french else "I could not collect live inspection data."

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

    if "methods" in tool_result:
        implemented = []
        pending = []
        for item in tool_result.get("methods", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            if item.get("implemented"):
                implemented.append(name)
            else:
                pending.append(name)

        segments = []
        if tool_result.get("scope") == "retrieval":
            if implemented:
                if prefers_french:
                    segments.append(f"Les methodes de reranking disponibles sont {', '.join(implemented)}")
                    segments.append(f"vous pouvez changer la methode de reranking vers l'une de celles-ci : {', '.join(implemented)}")
                else:
                    segments.append(f"Available reranking methods are {', '.join(implemented)}")
                    segments.append(f"you can change the reranking method to any of these: {', '.join(implemented)}")
            if pending:
                segments.append(
                    f"{', '.join(pending)} existe dans le pipeline mais n'est pas encore implemente"
                    if prefers_french
                    else f"{', '.join(pending)} exists in the pipeline but is not implemented yet"
                )
            current_ranker = tool_result.get("current_default_ranker_type")
            if current_ranker:
                segments.append(
                    f"la methode de reranking par defaut actuelle est {current_ranker}"
                    if prefers_french
                    else f"the current default reranking method is {current_ranker}"
                )
        else:
            if implemented:
                if prefers_french:
                    segments.append(f"Les strategies de chunking disponibles sont {', '.join(implemented)}")
                    segments.append(f"vous pouvez changer la strategie de chunking vers l'une de celles-ci : {', '.join(implemented)}")
                else:
                    segments.append(f"Available chunking strategies are {', '.join(implemented)}")
                    segments.append(f"you can change the chunking strategy to any of these: {', '.join(implemented)}")
            if pending:
                segments.append(
                    f"{', '.join(pending)} existe dans le pipeline mais n'est pas encore implemente"
                    if prefers_french
                    else f"{', '.join(pending)} exists in the pipeline but is not implemented yet"
                )
            current_strategy = tool_result.get("current_strategy")
            if current_strategy:
                segments.append(
                    f"la strategie de chunking actuelle est {current_strategy}"
                    if prefers_french
                    else f"the current chunking strategy is {current_strategy}"
                )
            chunk_size = tool_result.get("current_chunk_size")
            chunk_overlap = tool_result.get("current_chunk_overlap")
            if chunk_size is not None and chunk_overlap is not None:
                segments.append(
                    f"la taille actuelle des chunks est {chunk_size} avec un overlap de {chunk_overlap}"
                    if prefers_french
                    else f"the current chunk size is {chunk_size} with overlap {chunk_overlap}"
                )
        if segments:
            return ". ".join(segments) + "."

    return f"J'ai inspecte le systeme et obtenu : {tool_result}." if prefers_french else f"I inspected the system and got: {tool_result}."


def _extract_dataset_path(message: str) -> str:
    match = re.search(r"([A-Za-z0-9_./-]+\.json)", message)
    return match.group(1) if match else "evals/sample_eval_dataset.json"


def _extract_int_setting(message: str, patterns: list[str]) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))
    return None


def _extract_chunk_strategy(message: str) -> str | None:
    patterns = [
        r"chunk[_ ]strategy(?:\s+to)?\s+(late|overlap|semantic|sentence)",
        r"set\s+chunk[_ ]strategy\s+(?:to\s+)?(late|overlap|semantic|sentence)",
        r"change\s+chunk[_ ]strategy\s+(?:to\s+)?(late|overlap|semantic|sentence)",
        r"update\s+chunk[_ ]strategy\s+(?:to\s+)?(late|overlap|semantic|sentence)",
        r"(?:use|switch to)\s+(late|overlap|semantic|sentence)(?:\s+chunk(?:ing)?(?:\s+strategy)?)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1)
    bare = re.search(r"\b(late|overlap|semantic|sentence)\b", message)
    if bare:
        return bare.group(1)
    return None


def _infer_scope_from_context(message: str, toolbox: AdminToolbox, session_context: dict | None = None) -> str:
    try:
        return toolbox.resolve_config_scope(message)
    except ValueError:
        pass

    context = session_context or {}
    previous_topic = str(context.get("last_topic") or "").lower()
    pending_action = context.get("pending_action")
    if isinstance(pending_action, dict) and str(pending_action.get("tool") or "") == "update_repo_config":
        arguments = pending_action.get("arguments", {})
        if isinstance(arguments, dict):
            pending_scope = str(arguments.get("service_name") or "").lower()
            if pending_scope in {"preprocessing", "retrieval", "embedding", "generation"}:
                return pending_scope

    last_result = context.get("last_result")
    if isinstance(last_result, dict):
        tool_result = last_result.get("tool_result")
        if isinstance(tool_result, dict):
            result_scope = str(tool_result.get("scope") or "").lower()
            if result_scope in {"preprocessing", "retrieval", "embedding", "generation"}:
                return result_scope
            if "current_default_ranker_type" in tool_result or "methods" in tool_result:
                return "retrieval"
            if "current_strategy" in tool_result or "current_chunk_size" in tool_result:
                return "preprocessing"

    if previous_topic in {"reranking_strategy", "update_repo_config"}:
        lowered = message.lower()
        if any(token in lowered for token in ["none", "cross", "llm", "rank", "rerank", "top k", "top-k"]):
            return "retrieval"
    if previous_topic in {"chunking"}:
        return "preprocessing"

    return ""


def _semantic_action_planner(
    message: str,
    settings: Settings,
    session_context: dict | None = None,
) -> SemanticActionPlan | None:
    model = _make_model(settings)
    if model is None:
        return None

    context = session_context or {}
    previous_route = str(context.get("last_route") or "none")
    previous_topic = str(context.get("last_topic") or "none")
    last_result = context.get("last_result", {})
    if not isinstance(last_result, dict):
        last_result = {}

    try:
        structured = model.with_structured_output(SemanticActionPlan, method="function_calling")
        return structured.invoke(
            [
                SystemMessage(
                    content=(
                        "Infer whether the user is asking to execute one supported admin task. "
                        "Do not require exact technical wording. Understand paraphrases, French phrasing, and follow-ups like 'it', 'la', or 'that'. "
                        "Return action_type='none' unless the user is asking to do a task. "
                        "Supported actions are: "
                        "update_config, delete_document, reindex_document, reindex_validated_documents, run_evaluation, compare_evaluation_reports. "
                        "For update_config, use only normalized keys already supported by the system. "
                        "Retrieval changes use: ranker, top_k_retrieve, top_k_return. "
                        "Use previous session context when the user refers to an already discussed setting. "
                        f"Previous route: {previous_route}. Previous topic: {previous_topic}. "
                        f"Last result snapshot: {json.dumps(last_result, ensure_ascii=True)}"
                    )
                ),
                HumanMessage(content=message),
            ]
        )
    except Exception:
        return None


def _pending_action_from_semantic_plan(
    plan: SemanticActionPlan,
    message: str,
    toolbox: AdminToolbox,
    session_context: dict | None = None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    prefers_french = _prefers_french(message)
    if plan.action_type == "none":
        return "advisory", None, None

    if plan.action_type == "update_config":
        scope = str(plan.service_name or "").strip().lower()
        if scope not in {"preprocessing", "retrieval", "embedding", "generation"}:
            scope = _infer_scope_from_context(message, toolbox, session_context)
        changes = dict(plan.changes)
        lowered = message.lower()
        if scope == "retrieval" and "ranker" not in changes:
            if "cross encoder" in lowered or "cross_encoder" in lowered or "cross-encoder" in lowered:
                changes["ranker"] = "cross_encoder"
            elif "llm batch" in lowered or "llm_batch" in lowered:
                changes["ranker"] = "llm_batch"
            elif re.search(r"\bnone\b", lowered) or re.search(r"\boff\b", lowered) or re.search(r"\bdisable\b", lowered):
                changes["ranker"] = "none"
        if not scope or not changes:
            return "advisory", None, None
        return (
            "mutate",
            {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": scope, "changes": changes},
                "steps": [],
                "summary": f"Update {scope} config with {changes}.",
            },
            (
                f"Je suis pret a mettre a jour les parametres {scope} avec {changes}. Confirmez-vous que je dois appliquer ce changement ?"
                if prefers_french
                else f"I am ready to update the {scope} settings with {changes}. Confirm if you want me to apply that change."
            ),
        )

    if plan.action_type == "reindex_validated_documents":
        return (
            "workflow",
            {
                "intent": "workflow",
                "tool": "reindex_validated_documents",
                "arguments": {},
                "steps": [],
                "summary": "Reindex every validated document currently tracked by ingestion.",
            },
            "I am ready to reindex every validated document. Confirm to start the workflow.",
        )

    if plan.action_type == "run_evaluation":
        dataset_path = str(plan.dataset_path or _extract_dataset_path(message))
        return (
            "workflow",
            {
                "intent": "workflow",
                "tool": "run_evaluation",
                "arguments": {"dataset_path": dataset_path},
                "steps": [],
                "summary": f"Run evaluation with dataset '{dataset_path}'.",
            },
            f"I am ready to run the evaluation with '{dataset_path}'. Confirm to start it.",
        )

    if plan.action_type == "compare_evaluation_reports":
        baseline = str(plan.baseline_report_id or "").strip()
        candidate = str(plan.candidate_report_id or "").strip()
        if not baseline or not candidate:
            pair = toolbox.resolve_report_pair(message)
            if pair is None:
                return "advisory", None, None
            baseline, candidate = pair
        return (
            "workflow",
            {
                "intent": "workflow",
                "tool": "compare_evaluation_reports",
                "arguments": {"baseline_report_id": baseline, "candidate_report_id": candidate},
                "steps": [],
                "summary": f"Compare evaluation reports '{baseline}' and '{candidate}'.",
            },
            f"I am ready to compare report '{baseline}' against '{candidate}'. Confirm to run it.",
        )

    return "advisory", None, None


def _plan_mutation(message: str, toolbox: AdminToolbox, session_context: dict | None = None) -> tuple[dict[str, Any] | None, str]:
    lowered = message.lower()
    prefers_french = _prefers_french(message)
    scope = _infer_scope_from_context(message, toolbox, session_context)
    changes: dict[str, Any] = {}
    if scope == "preprocessing":
        chunk_strategy = _extract_chunk_strategy(lowered)
        chunk_size = _extract_int_setting(
            lowered,
            [
                r"chunk[_ ]size(?:\s+to)?\s+(\d+)",
                r"set\s+chunk[_ ]size\s+(?:to\s+)?(\d+)",
                r"change\s+chunk[_ ]size\s+(?:to\s+)?(\d+)",
            ],
        )
        if chunk_size is None:
            bare_size = re.fullmatch(r"\s*(\d+)\s*", lowered)
            if bare_size:
                chunk_size = int(bare_size.group(1))
        chunk_overlap = _extract_int_setting(
            lowered,
            [
                r"chunk[_ ]overlap(?:\s+to)?\s+(\d+)",
                r"set\s+chunk[_ ]overlap\s+(?:to\s+)?(\d+)",
                r"change\s+chunk[_ ]overlap\s+(?:to\s+)?(\d+)",
            ],
        )
        if chunk_strategy is not None:
            changes["chunk_strategy"] = chunk_strategy
        if chunk_size is not None:
            changes["chunk_size"] = chunk_size
        if chunk_overlap is not None:
            changes["chunk_overlap"] = chunk_overlap
    elif scope == "retrieval":
        if "cross_encoder" in lowered or "cross encoder" in lowered or "cross-encoder" in lowered:
            changes["ranker"] = "cross_encoder"
        elif "llm_batch" in lowered or "llm batch" in lowered or "llm rerank" in lowered:
            changes["ranker"] = "llm_batch"
        elif (
            "no rerank" in lowered
            or "no reranking" in lowered
            or "without reranking" in lowered
            or re.search(r"\bnone\b", lowered)
            or re.search(r"\boff\b", lowered)
            or re.search(r"\bdisable\b", lowered)
        ):
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
            (
                f"Je suis pret a mettre a jour les parametres {scope} avec {changes}. Confirmez-vous que je dois appliquer ce changement ?"
                if prefers_french
                else f"I am ready to update the {scope} settings with {changes}. Confirm if you want me to apply that change."
            ),
        )

    if "document" in lowered and any(token in lowered for token in ["delete", "remove"]):
        guess = message
        for prefix in ["delete document", "remove document", "delete file", "remove file"]:
            guess = re.sub(prefix, "", guess, flags=re.IGNORECASE).strip(" :")
        target = toolbox.find_document(guess) if guess else None
        if target is None:
            return None, "Je peux supprimer un document si vous me donnez son nom exact ou son identifiant." if prefers_french else "I can delete a document if you tell me the exact document name or ID."
        summary = str(target.get("original_name") or target.get("storage_path") or target.get("id") or "document")
        return (
            {
                "intent": "mutation",
                "tool": "delete_document_completely",
                "arguments": {"document_id": str(target.get("id") or "")},
                "steps": [],
                "summary": f"Delete document '{summary}' and remove its indexed vectors.",
            },
            (
                f"J'ai trouve le document '{summary}'. Confirmez-vous que je dois le supprimer et nettoyer ses vecteurs ?"
                if prefers_french
                else f"I found the document '{summary}'. Confirm if you want me to delete it and clean up its vectors."
            ),
        )

    return None, (
        "Ce changement n'est pas encore expose par admin-service. Le service actuel peut executer la suppression de documents, le reindexing et les workflows d'evaluation."
        if prefers_french
        else "That change is not exposed through admin-service yet. The current service can execute document deletion, reindexing, and evaluation workflows."
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


def _plan_inspection_step(message: str, toolbox: AdminToolbox) -> dict[str, Any] | None:
    lowered = message.lower()
    if _is_chunking_methods_question(message):
        return {"tool": "get_chunking_methods", "arguments": {}}
    if any(token in lowered for token in ["rerank", "reranking", "reranker", "ranker"]):
        return {"tool": "get_repo_config", "arguments": {"service_name": "retrieval"}}
    if any(token in lowered for token in ["chunk", "chunking", "chunk overlap", "chunk size"]):
        return {"tool": "get_repo_config", "arguments": {"service_name": "preprocessing"}}
    if "evaluation" in lowered and any(token in lowered for token in ["report", "reports", "latest", "recent", "current"]):
        return {"tool": "list_evaluation_reports", "arguments": {}}
    if any(token in lowered for token in ["ingestion", "document status", "status"]) and "document" not in lowered:
        return {"tool": "get_ingestion_status", "arguments": {}}
    if "document" in lowered:
        return {"tool": "list_loaded_documents", "arguments": {}}
    return None


def _split_into_clauses(message: str) -> list[str]:
    clauses = [
        clause.strip(" ,;")
        for clause in re.split(r"\b(?:and also|also|and then|then|and|et aussi|et puis|puis|ensuite)\b", message, flags=re.IGNORECASE)
        if clause.strip(" ,;")
    ]
    return clauses or [message.strip()]


def _build_compound_pending_action(steps: list[dict[str, Any]]) -> dict[str, Any]:
    has_workflow = any(step.get("tool") in {"reindex_document", "reindex_validated_documents", "run_evaluation", "compare_evaluation_reports"} for step in steps)
    return {
        "intent": "workflow" if has_workflow else "mutation",
        "tool": "compound_action",
        "arguments": {},
        "steps": [{"tool": step["tool"], "arguments": step.get("arguments", {})} for step in steps],
        "summary": "Execute the planned admin actions in order.",
    }


def _summarize_compound_plan(steps: list[dict[str, Any]]) -> str:
    readable = []
    for step in steps:
        tool = str(step.get("tool") or "")
        args = step.get("arguments", {})
        if tool == "update_repo_config":
            readable.append(f"update {args.get('service_name')} settings")
        elif tool == "get_repo_config":
            readable.append(f"check current {args.get('service_name')} settings")
        elif tool == "get_chunking_methods":
            readable.append("check current chunking methods")
        elif tool == "reindex_validated_documents":
            readable.append("reindex validated documents")
        elif tool == "reindex_document":
            readable.append("reindex one document")
        elif tool == "run_evaluation":
            readable.append("run an evaluation")
        elif tool == "compare_evaluation_reports":
            readable.append("compare evaluation reports")
        else:
            readable.append(tool.replace("_", " "))
    return f"I planned these actions in order: {', '.join(readable)}. Confirm if you want me to execute them."


def _plan_request(
    message: str,
    requested_route: str,
    toolbox: AdminToolbox,
    settings: Settings,
    session_context: dict | None = None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    clauses = _split_into_clauses(message)
    if len(clauses) <= 1:
        semantic_plan = _semantic_action_planner(message, settings, session_context)
        if semantic_plan is not None:
            semantic_route, semantic_action, semantic_answer = _pending_action_from_semantic_plan(
                semantic_plan,
                message,
                toolbox,
                session_context,
            )
            if semantic_action is not None:
                return semantic_route, semantic_action, semantic_answer
        if requested_route == "workflow":
            pending_action, answer = _plan_workflow(message, toolbox)
            if pending_action is not None:
                return "workflow", pending_action, answer
        if requested_route == "mutate":
            pending_action, answer = _plan_mutation(message, toolbox, session_context)
            if pending_action is not None:
                return "mutate", pending_action, answer
        pending_action, answer = _plan_workflow(message, toolbox)
        if pending_action is not None:
            return "workflow", pending_action, answer
        pending_action, answer = _plan_mutation(message, toolbox, session_context)
        if pending_action is not None:
            return "mutate", pending_action, answer
        if requested_route in {"workflow", "mutate"}:
            return "advisory", None, None
        return requested_route, None, None

    planned_steps: list[dict[str, Any]] = []
    has_mutation_like = False
    has_workflow = False

    for clause in clauses:
        semantic_plan = _semantic_action_planner(clause, settings, session_context)
        if semantic_plan is not None:
            semantic_route, semantic_action, _ = _pending_action_from_semantic_plan(
                semantic_plan,
                clause,
                toolbox,
                session_context,
            )
            if semantic_action is not None:
                planned_steps.append({"tool": semantic_action["tool"], "arguments": semantic_action.get("arguments", {})})
                has_mutation_like = True
                if semantic_route == "workflow":
                    has_workflow = True
                continue
        workflow_action, _ = _plan_workflow(clause, toolbox)
        if workflow_action is not None:
            planned_steps.append({"tool": workflow_action["tool"], "arguments": workflow_action.get("arguments", {})})
            has_workflow = True
            has_mutation_like = True
            continue

        mutation_action, _ = _plan_mutation(clause, toolbox, session_context)
        if mutation_action is not None:
            planned_steps.append({"tool": mutation_action["tool"], "arguments": mutation_action.get("arguments", {})})
            has_mutation_like = True
            continue

        inspect_step = _plan_inspection_step(clause, toolbox)
        if inspect_step is not None:
            planned_steps.append(inspect_step)

    if len(planned_steps) > 1 and has_mutation_like:
        pending_action = _build_compound_pending_action(planned_steps)
        return ("workflow" if has_workflow else "mutate"), pending_action, _summarize_compound_plan(planned_steps)

    return requested_route, None, None


def _run_llm_tool_loop(
    *,
    settings: Settings,
    tools: list,
    system_prompt: str,
    state: AdminState,
    progress_callback: ProgressCallback | None = None,
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
                    if progress_callback is not None:
                        progress_callback(activity[-1])
                    continue
            uncached_calls.append(tool_call)

        if uncached_calls:
            for tool_call in uncached_calls:
                started_item = _progress_item(
                    phase="tool",
                    status="in_progress",
                    title=f"Tool started: {tool_call['name']}",
                    detail="Collecting live data from a backend service.",
                    tool=tool_call["name"],
                    arguments=tool_call.get("args", {}),
                )
                activity.append(started_item)
                _emit_progress(progress_callback, started_item)
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
                    if progress_callback is not None:
                        progress_callback(activity[-1])
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
    if tool_name in {"get_repo_config", "get_reranking_methods"}:
        return 600, ["config"]
    if tool_name in {"get_ingestion_status", "list_loaded_documents"}:
        return 90, ["documents", "ingestion"]
    if tool_name == "list_evaluation_reports":
        return 180, ["evaluation_reports"]
    return 60, [tool_name]


def build_graph(settings: Settings, access_token: str | None = None, progress_callback: ProgressCallback | None = None):
    graph = StateGraph(AdminState)
    classifier = IntentClassifier(settings)

    def classify_intent(state: AdminState) -> AdminState:
        in_progress_item = _progress_item(
            phase="classify",
            status="in_progress",
            title="Classifying request",
            detail="Understanding the request and choosing the right admin path.",
        )
        _emit_progress(progress_callback, in_progress_item)
        try:
            result = classifier.classify(state["message"], state.get("session_context"))
        except TypeError:
            result = classifier.classify(state["message"])
        activity = list(state.get("activity", []))
        activity.append(in_progress_item)
        completed_item = _progress_item(
            phase="classify",
            status="completed",
            title="Intent classified",
            detail=result.reasoning,
            arguments={"category": result.category, "intent": result.intent},
        )
        activity.append(completed_item)
        _emit_progress(progress_callback, completed_item)
        toolbox = AdminToolbox(settings, access_token=state.get("access_token") or access_token)
        route, planned_pending_action, planned_answer = _plan_request(
            state["message"],
            result.category,
            toolbox,
            settings,
            state.get("session_context", {}),
        )
        return {
            **state,
            "route": route,
            "intent": result.intent,
            "status": "running",
            "activity": activity,
            "current_step": "route",
            "planned_pending_action": planned_pending_action,
            "planned_answer": planned_answer,
        }

    def advisory_node(state: AdminState) -> AdminState:
        toolbox = AdminToolbox(settings, access_token=state.get("access_token") or access_token)
        read_tools = build_tools(toolbox, include_mutations=False)
        advisory_started = _progress_item(
            phase="advisory",
            status="in_progress",
            title="Preparing advisory answer",
            detail="Gathering the context needed to answer the request clearly.",
        )
        _emit_progress(progress_callback, advisory_started)
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
            progress_callback=progress_callback,
        )
        if not answer:
            answer = _fallback_advisory_answer(state)
        answer = _normalize_user_answer(answer)

        activity = list(state.get("activity", []))
        activity.append(advisory_started)
        activity.extend(tool_activity)
        advisory_completed = _progress_item(
            phase="advisory",
            status="completed",
            title="Advice prepared",
            detail="The request was answered for a non-technical admin.",
        )
        activity.append(advisory_completed)
        _emit_progress(progress_callback, advisory_completed)
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
        inspect_started = _progress_item(
            phase="inspect",
            status="in_progress",
            title="Inspecting current settings",
            detail="Checking the live admin context and current system configuration.",
        )
        activity.append(inspect_started)
        _emit_progress(progress_callback, inspect_started)
        if _is_chunking_methods_question(state["message"]):
            tool_result = toolbox.get_chunking_methods()
            tool_activity = [
                {
                    "phase": "tool",
                    "status": "completed",
                    "title": "Chunking strategies inspected",
                    "detail": "The agent read the current preprocessing chunking strategies and the active default.",
                    "tool": "get_chunking_methods",
                    "arguments": {},
                }
            ]
            if progress_callback is not None:
                progress_callback(tool_activity[-1])
            answer = _summarize_inspection_result(tool_result, state["message"], state.get("session_context", {}))
            answer = _normalize_user_answer(answer)
            activity.extend(tool_activity)
            inspect_finished = _progress_item(
                phase="inspect",
                status="completed",
                title="Inspection finished",
                detail="Live chunking strategy information was prepared for the admin.",
            )
            activity.append(inspect_finished)
            _emit_progress(progress_callback, inspect_finished)
            return {
                **state,
                "status": "completed",
                "final_answer": answer,
                "current_step": "summarize",
                "activity": activity,
                "tool_result": tool_result,
                "tool_call_count": 1,
                "tool_cache_updates": {},
            }
        if _is_reranking_methods_question(state["message"]):
            tool_result = toolbox.get_reranking_methods()
            tool_activity = [
                {
                    "phase": "tool",
                    "status": "completed",
                    "title": "Reranking methods inspected",
                    "detail": "The agent read the current retrieval reranking methods and the active default.",
                    "tool": "get_reranking_methods",
                    "arguments": {},
                }
            ]
            if progress_callback is not None:
                progress_callback(tool_activity[-1])
            answer = _summarize_inspection_result(tool_result, state["message"], state.get("session_context", {}))
            answer = _normalize_user_answer(answer)
            activity.extend(tool_activity)
            inspect_finished = _progress_item(
                phase="inspect",
                status="completed",
                title="Inspection finished",
                detail="Live reranking method information was prepared for the admin.",
            )
            activity.append(inspect_finished)
            _emit_progress(progress_callback, inspect_finished)
            return {
                **state,
                "status": "completed",
                "final_answer": answer,
                "current_step": "summarize",
                "activity": activity,
                "tool_result": tool_result,
                "tool_call_count": 1,
                "tool_cache_updates": {},
            }

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
                progress_callback=progress_callback,
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
                if _is_chunking_methods_question(state["message"]):
                    tool_result = toolbox.get_chunking_methods()
                    tool_activity.append(
                        {
                            "phase": "tool",
                            "status": "completed",
                            "title": "Chunking methods inspected",
                            "detail": "The agent read the current preprocessing chunking options.",
                            "tool": "get_chunking_methods",
                            "arguments": {},
                        }
                    )
                    if progress_callback is not None:
                        progress_callback(tool_activity[-1])
                elif _is_reranking_methods_question(state["message"]):
                    tool_result = toolbox.get_reranking_methods()
                    tool_activity.append(
                        {
                            "phase": "tool",
                            "status": "completed",
                            "title": "Reranking methods inspected",
                            "detail": "The agent read the current retrieval reranking methods.",
                            "tool": "get_reranking_methods",
                            "arguments": {},
                        }
                    )
                    if progress_callback is not None:
                        progress_callback(tool_activity[-1])
                else:
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
                    if progress_callback is not None:
                        progress_callback(tool_activity[-1])
            except Exception:
                pass

        if not answer:
            answer = _summarize_inspection_result(tool_result or {}, state["message"], state.get("session_context", {}))
        answer = _normalize_user_answer(answer)

        activity.extend(tool_activity)
        inspect_finished = _progress_item(
            phase="inspect",
            status="completed" if tool_result is not None else "failed",
            title="Inspection finished",
            detail="Live system information was prepared for the admin." if tool_result is not None else "Inspection had no usable data.",
        )
        activity.append(inspect_finished)
        _emit_progress(progress_callback, inspect_finished)
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
        mutate_started = _progress_item(
            phase="mutate",
            status="in_progress",
            title="Planning requested change",
            detail="Checking whether the requested change can be applied safely.",
        )
        _emit_progress(progress_callback, mutate_started)
        toolbox = AdminToolbox(settings, access_token=state.get("access_token") or access_token)
        pending_action = state.get("planned_pending_action")
        answer = state.get("planned_answer")
        if pending_action is None:
            pending_action, answer = _plan_mutation(state["message"], toolbox, state.get("session_context", {}))
        activity = list(state.get("activity", []))
        activity.append(mutate_started)
        mutate_finished = _progress_item(
            phase="mutate",
            status="completed" if pending_action else "failed",
            title="Mutation planned" if pending_action else "Mutation unsupported",
            detail=answer,
            tool=(pending_action or {}).get("tool"),
            arguments=(pending_action or {}).get("arguments", {}),
        )
        activity.append(mutate_finished)
        _emit_progress(progress_callback, mutate_finished)
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
        workflow_started = _progress_item(
            phase="workflow",
            status="in_progress",
            title="Planning workflow",
            detail="Mapping the request to the supported admin workflow steps.",
        )
        _emit_progress(progress_callback, workflow_started)
        toolbox = AdminToolbox(settings, access_token=state.get("access_token") or access_token)
        pending_action = state.get("planned_pending_action")
        answer = state.get("planned_answer")
        if pending_action is None:
            pending_action, answer = _plan_workflow(state["message"], toolbox)
        activity = list(state.get("activity", []))
        activity.append(workflow_started)
        workflow_finished = _progress_item(
            phase="workflow",
            status="completed" if pending_action else "failed",
            title="Workflow planned" if pending_action else "Workflow could not be planned",
            detail=answer,
            tool=(pending_action or {}).get("tool"),
            arguments=(pending_action or {}).get("arguments", {}),
        )
        activity.append(workflow_finished)
        _emit_progress(progress_callback, workflow_finished)
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
        summarize_started = _progress_item(
            phase="summarize",
            status="in_progress",
            title="Finalizing response",
            detail="Preparing the final response for display.",
        )
        summarize_completed = _progress_item(
            phase="summarize",
            status="completed",
            title="Response prepared",
            detail="The graph produced a user-facing response.",
        )
        activity.append(summarize_started)
        _emit_progress(progress_callback, summarize_started)
        activity.append(summarize_completed)
        _emit_progress(progress_callback, summarize_completed)
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


def run_graph(
    payload: AdminChatRequest,
    settings: Settings,
    session_context: dict | None = None,
    progress_callback: ProgressCallback | None = None,
) -> AdminChatResponse:
    app = build_graph(settings, access_token=payload.access_token, progress_callback=progress_callback)
    final_state = app.invoke(
        {
            "session_id": payload.session_id,
            "message": payload.message,
            "selected_mode": payload.selected_mode,
            "access_token": payload.access_token,
            "status": "running",
            "activity": [],
            "requires_confirmation": False,
            "chat_history": _serialize_chat_history(payload.chat_history),
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
