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


class SemanticTask(BaseModel):
    task_type: str = Field(
        default="read_config",
        pattern="^(read_config|list_methods|explain_methods|update_config|workflow_action)$",
    )
    service_name: str | None = Field(default=None, pattern="^(preprocessing|retrieval|embedding|generation)$")
    subject: str | None = Field(default=None)
    config_key: str | None = None
    config_value: Any = None
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    ordering_index: int = 0
    reasoning: str = ""


class SemanticTaskPlan(BaseModel):
    tasks: list[SemanticTask] = Field(default_factory=list)


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

        if _is_identity_question(message):
            return IntentClassification(
                category="advisory",
                intent="identity",
                reasoning="The user is asking the admin agent to identify itself.",
            )

        if _is_capability_question(message, session_context):
            return IntentClassification(
                category="advisory",
                intent="capabilities",
                reasoning="The user is asking about available admin capabilities.",
            )

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
                                "Classify the admin request into one category: advisory, inspect, mutate. "
                                "Use advisory for recommendations/explanations, inspect for information lookup, "
                                "mutate for requested changes and sequenced operations. "
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
        if _is_identity_question(message):
            return IntentClassification(
                category="advisory",
                intent="identity",
                reasoning="Identity request matched the deterministic identity detector.",
            )
        if _is_capability_question(message, {"last_route": previous_route, "last_topic": previous_topic}):
            return IntentClassification(
                category="advisory",
                intent="capabilities",
                reasoning="Capability request matched the deterministic capability detector.",
            )
        if is_generic_follow_up(message) and previous_route in {"advisory", "inspect"}:
            return IntentClassification(
                category=previous_route, intent=previous_topic or previous_route, reasoning="Generic follow-up reused the previous route.",
            )

        if _is_chunking_methods_question(message) or _is_reranking_methods_question(message):
            category: Literal["inspect"] = "inspect"
        elif any(token in lowered for token in ["reindex", "run evaluation", "compare evaluation", "compare reports", "réindex", "evaluer", "évaluation"]):
            category: Literal["mutate"] = "mutate"
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


def _is_capability_question(message: str, session_context: dict | None = None) -> bool:
    lowered = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not lowered:
        return False

    direct_patterns = [
        r"\bwhat can you do\b",
        r"\bwhat do you do\b",
        r"\bwhat (?:other )?services can you do\b",
        r"\bwhat (?:other )?services do you offer\b",
        r"\bhow can you assist\b",
        r"\bhow can you help\b",
        r"\bhow do you assist\b",
        r"\bhow do you help\b",
        r"\btell me all tasks you can do\b",
        r"\bgive me all tasks you can do\b",
        r"\blist (?:all )?(?:your )?(?:tools|tasks|capabilities)\b",
        r"\ball (?:available )?(?:tools|tasks|capabilities)\b",
        r"\btell me about (?:all )?(?:available )?(?:tools|tasks|capabilities)\b",
        r"\bhow can you assist me\b",
        r"\bhow can you help me\b",
        r"\bi said what can you do\b",
        r"\bjust list your tools\b",
    ]
    if any(re.search(pattern, lowered) for pattern in direct_patterns):
        return True

    asks_for_capabilities = any(
        phrase in lowered
        for phrase in [
            "what are your capabilities",
            "tell me your capabilities",
            "available tools",
            "available tasks",
            "your tools",
            "your tasks",
            "what tools",
            "what tasks",
        ]
    )
    if asks_for_capabilities and not any(
        token in lowered
        for token in ["delete document", "reindex", "run evaluation", "compare evaluation", "change ", "set ", "switch ", "update "]
    ):
        return True

    context = session_context or {}
    previous_topic = str(context.get("last_topic") or "").strip().lower()
    if previous_topic == "capabilities" and any(
        phrase in lowered
        for phrase in [
            "what can you do",
            "list your tools",
            "list tools",
            "list tasks",
            "your capabilities",
            "all tools",
            "all tasks",
        ]
    ):
        return True

    return False


def _is_identity_question(message: str) -> bool:
    lowered = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not lowered:
        return False
    return any(
        re.search(pattern, lowered)
        for pattern in [
            r"\bwho are you\b",
            r"\bwhat(?:'s| is) your name\b",
            r"\byour name\b",
            r"\bdo you have a name\b",
        ]
    )


def _build_identity_answer(message: str) -> str:
    if _prefers_french(message):
        return (
            "Je m'appelle `Synapse`.\n\n"
            "Je suis l'agent d'administration et je peux vous aider a inspecter l'etat du systeme, "
            "verifier les configurations, consulter les documents et rapports, et preparer des changements "
            "que vous confirmez avant execution."
        )
    return (
        "My name is `Synapse`.\n\n"
        "I am the admin agent. I can inspect system status, review configurations, check documents and "
        "evaluation reports, and prepare admin changes that only run after your confirmation."
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


_DOCUMENT_MUTATION_VERBS = [
    "delete", "remove", "drop", "purge", "erase",
    "reindex", "re-index", "reindexe", "rebuild", "re-embed", "reembed",
    "run ", "evaluate", "compare",
    "supprime", "supprimer", "réindex", "reindexer", "changer", "modifier", "lancer",
    "احذف", "حذف", "أعد",
]


def _is_document_inspection_question(message: str) -> bool:
    """True when the user only wants to see/list documents (optionally by status).

    Safety guard: questions like "which documents were rejected or failed?" are
    read-only and must never be routed to a mutation such as
    reindex_validated_documents. If any explicit mutation verb is present we do
    not treat it as a pure inspection and let normal planning proceed.
    """
    lowered = message.lower()
    if any(verb in lowered for verb in _DOCUMENT_MUTATION_VERBS):
        return False
    # Imperative review verbs (confirm/refuse/approve/reject ...) are actions, not
    # reads. Word boundaries keep status reads ("rejected"/"refused") as inspection.
    if re.search(
        r"\b(confirm|approve|accept|refuse|reject|decline|deny|"
        r"valider|approuver|confirmer|accepter|rejeter|refuser)\b",
        lowered,
    ):
        return False
    asks_documents = bool(
        re.search(r"(document|documents|\bdoc\b|\bdocs\b|file|files|fichier|fichiers|مستند|ملف)", lowered)
    )
    if not asks_documents:
        return False
    asks_listing_or_status = bool(
        re.search(
            r"(show|list|which|what|find|display|any|are there|status|state|"
            r"reject|refus|declin|denied|fail|invalid|problematic|\bbad\b|broken|"
            r"not embedded|did not|didn'?t|pass|montre|liste|quels?|quelles?|rejet|échou|"
            r"اعرض|قائمة|حالة)",
            lowered,
        )
    )
    return asks_listing_or_status


def _doc_names(docs: list[dict[str, Any]]) -> list[str]:
    """Friendly document names from a list of document dicts (for confirmations)."""
    names: list[str] = []
    for doc in docs or []:
        if isinstance(doc, dict):
            name = str(doc.get("original_name") or doc.get("id") or "").strip()
            if name:
                names.append(name)
    return names


def _normalize_workflow_step_arguments(
    tool_name: str,
    arguments: dict[str, Any],
    toolbox: AdminToolbox,
) -> dict[str, Any]:
    """Resolve planner/LLM-emitted arguments into the canonical keys the executor
    and confirmation prompt expect, so the user sees the real target before
    confirming (e.g. a resolved document id instead of an empty string)."""
    args = dict(arguments) if isinstance(arguments, dict) else {}

    if tool_name in {"reindex_document", "delete_document_completely"}:
        doc_id = str(args.get("document_id") or "").strip()
        if doc_id:
            result = {"document_id": doc_id}
            named = _documents_by_ids(toolbox, [doc_id])
            names = _doc_names(named)
            if names:
                result["target_names"] = names[:8]
            return result
        query = AdminToolbox._document_query_from_arguments(args)
        if not query:
            return {"document_id": ""}
        try:
            matches = toolbox.find_documents_by_filter(name_contains=query)
        except Exception:
            matches = []
        if len(matches) == 1:
            return {
                "document_id": str(matches[0].get("id") or ""),
                "target_names": _doc_names(matches)[:8],
            }
        if not matches:
            try:
                single = toolbox.find_document(query)
            except Exception:
                single = None
            if single is not None:
                return {
                    "document_id": str(single.get("id") or ""),
                    "target_names": _doc_names([single])[:8],
                }
        # Zero or multiple matches: keep the query so the executor can run a bulk
        # reindex / ask for delete disambiguation, and the prompt can show it.
        result = {"document_query": query, "match_count": len(matches)}
        names = _doc_names(matches)
        if names:
            result["target_names"] = names[:8]
        return result

    if tool_name == "compare_evaluation_reports":
        baseline, candidate = toolbox._resolve_compare_ids(args)
        return {"baseline_report_id": baseline, "candidate_report_id": candidate}

    if tool_name == "run_evaluation":
        dataset = str(args.get("dataset_path") or args.get("dataset") or "").strip()
        if not dataset.endswith(".json"):
            dataset = "evals/sample_eval_dataset.json"
        return {"dataset_path": dataset}

    return args


def _split_request_clauses(message: str) -> list[str]:
    clauses = [
        clause.strip(" ,;")
        for clause in re.split(r"\b(?:and also|also|and then|then|and|et aussi|et puis|puis|ensuite)\b", str(message or ""), flags=re.IGNORECASE)
        if clause.strip(" ,;")
    ]
    return clauses or [str(message or "").strip()]


def _is_chunking_advantages_request(message: str) -> bool:
    for clause in _split_request_clauses(message):
        lowered = clause.lower()
        asks_chunking = bool(
            re.search(r"(chunking|chunk|chunks|decoupage|d[eé]coupage|تقسيم|التقسيم)", lowered)
        )
        asks_advantages = bool(
            re.search(r"(advantage|advantages|benefit|benefits|pros|best for|when to use|avantage|avantages|فائدة|فوائد|ميزة|مزايا|disadvantage|disadvantages|cons|tradeoffs?)", lowered)
        )
        if asks_chunking and asks_advantages:
            return True
    return False


def _is_reranking_advantages_request(message: str) -> bool:
    for clause in _split_request_clauses(message):
        lowered = clause.lower()
        asks_reranking = bool(
            re.search(r"(rerank|reranking|reranker|ranker|ranking|rerankers)", lowered)
        )
        asks_advantages = bool(
            re.search(r"(advantage|advantages|benefit|benefits|pros|best for|when to use|avantage|avantages|فائدة|فوائد|ميزة|مزايا|disadvantage|disadvantages|cons|tradeoffs?)", lowered)
        )
        if asks_reranking and asks_advantages:
            return True
    return False


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

    if "report" in tool_result:
        report = tool_result.get("report")
        if not isinstance(report, dict) or not report:
            return "There are no saved evaluation reports yet."
        report_id = str(report.get("report_id") or "latest")
        sample_count = int(report.get("sample_count") or 0)
        summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
        metrics = ", ".join(
            f"{key}={value}"
            for key, value in summary.items()
            if isinstance(value, (int, float))
        ) or "no summary metrics were recorded"
        return f"The latest evaluation report is `{report_id}` with {sample_count} samples. Summary metrics: {metrics}."

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
        r"chunk[_ ]strategy(?:\s+to)?\s+(late|overlap|semantic|sentence|sementic)",
        r"set\s+chunk[_ ]strategy\s+(?:to\s+)?(late|overlap|semantic|sentence|sementic)",
        r"change\s+chunk[_ ]strategy\s+(?:to\s+)?(late|overlap|semantic|sentence|sementic)",
        r"update\s+chunk[_ ]strategy\s+(?:to\s+)?(late|overlap|semantic|sentence|sementic)",
        r"(?:use|switch to)\s+(late|overlap|semantic|sentence|sementic)(?:\s+chunk(?:ing)?(?:\s+strategy)?)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            strategy = match.group(1)
            return "semantic" if strategy == "sementic" else strategy
    bare = re.search(r"\b(late|overlap|semantic|sentence|sementic)\b", message)
    if bare:
        strategy = bare.group(1)
        return "semantic" if strategy == "sementic" else strategy
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


def _semantic_task_planner(
    message: str,
    settings: Settings,
    toolbox: AdminToolbox,
    session_context: dict | None = None,
) -> SemanticTaskPlan | None:
    model = _make_model(settings)
    if model is None:
        return None

    context = session_context or {}
    capabilities = toolbox.get_capabilities()
    previous_route = str(context.get("last_route") or "none")
    previous_topic = str(context.get("last_topic") or "none")
    pending_action = context.get("pending_action", {})
    if not isinstance(pending_action, dict):
        pending_action = {}

    try:
        structured = model.with_structured_output(SemanticTaskPlan, method="function_calling")
        return structured.invoke(
            [
                SystemMessage(
                    content=(
                        "Convert the user's admin request into an ordered list of normalized admin tasks. "
                        "Understand any language, mixed-language phrasing, non-technical wording, and follow-ups. "
                        "Use only supported services, config keys, tool names, and subjects from the capability map. "
                        "Task types: read_config, list_methods, explain_methods, update_config, workflow_action. "
                        "For update_config, always set service_name plus one normalized config_key/config_value pair when possible. "
                        "For retrieval settings, valid config keys include ranker, top_k_retrieve, top_k_return, fusion, alpha, rrf_k, rerank_top_n. "
                        "For explain_methods and list_methods, prefer subject='reranking' or subject='chunking'. "
                        "For workflow_action, use tool_name only for a supported workflow tool and place required arguments in arguments. "
                        "If the user asks for several things, return all of them in the same order. "
                        "Return an empty task list only if nothing actionable or inspectable can be inferred. "
                        f"Capabilities: {json.dumps(capabilities, ensure_ascii=True)}. "
                        f"Previous route: {previous_route}. Previous topic: {previous_topic}. "
                        f"Pending action: {json.dumps(pending_action, ensure_ascii=True)}."
                    )
                ),
                HumanMessage(content=message),
            ]
        )
    except Exception:
        return None


def _normalize_semantic_service(task: SemanticTask, toolbox: AdminToolbox, session_context: dict | None = None) -> str:
    if isinstance(task.service_name, str) and task.service_name.strip():
        return task.service_name.strip().lower()
    subject = str(task.subject or "").strip().lower()
    capabilities = toolbox.get_capabilities()
    subject_meta = capabilities.get("subjects", {}).get(subject, {})
    if isinstance(subject_meta, dict):
        service_name = str(subject_meta.get("service_name") or "").strip().lower()
        if service_name:
            return service_name
    return _infer_scope_from_context(subject or "", toolbox, session_context)


def _semantic_task_to_step(
    task: SemanticTask,
    toolbox: AdminToolbox,
    session_context: dict | None = None,
) -> dict[str, Any] | None:
    capabilities = toolbox.get_capabilities()
    services = capabilities.get("services", {})
    task_type = str(task.task_type or "").strip().lower()
    subject = str(task.subject or "").strip().lower()
    service_name = _normalize_semantic_service(task, toolbox, session_context)

    if task_type == "workflow_action":
        tool_name = str(task.tool_name or "").strip()
        if tool_name in capabilities.get("workflow_tools", []):
            raw_arguments = task.arguments if isinstance(task.arguments, dict) else {}
            return {
                "tool": tool_name,
                "arguments": _normalize_workflow_step_arguments(tool_name, raw_arguments, toolbox),
            }
        return None

    if task_type in {"read_config"}:
        if service_name in services:
            return {"tool": "get_repo_config", "arguments": {"service_name": service_name}}
        return None

    if task_type in {"list_methods", "explain_methods"}:
        if subject == "reranking":
            return {"tool": "get_reranking_methods", "arguments": {}}
        if subject == "chunking":
            return {"tool": "get_chunking_methods", "arguments": {}}
        if service_name in services:
            return {"tool": "get_repo_config", "arguments": {"service_name": service_name}}
        return None

    if task_type == "update_config":
        if service_name not in services:
            return None
        changes: dict[str, Any] = {}
        if isinstance(task.arguments, dict) and isinstance(task.arguments.get("changes"), dict):
            for key, value in task.arguments["changes"].items():
                if key in services[service_name]["config_keys"]:
                    changes[str(key)] = value
        config_key = str(task.config_key or "").strip()
        if config_key and config_key in services[service_name]["config_keys"]:
            changes[config_key] = task.config_value
        if not changes and isinstance(task.arguments, dict):
            for key, value in task.arguments.items():
                if key in services[service_name]["config_keys"]:
                    changes[key] = value
        if not changes:
            return None
        return {
            "tool": "update_repo_config",
            "arguments": {"service_name": service_name, "changes": changes},
        }

    return None


def _planned_steps_from_semantic_tasks(
    message: str,
    task_plan: SemanticTaskPlan,
    toolbox: AdminToolbox,
    session_context: dict | None = None,
) -> list[dict[str, Any]]:
    tasks = sorted(task_plan.tasks, key=lambda item: int(item.ordering_index or 0))
    planned_steps: list[dict[str, Any]] = []
    for task in tasks:
        step = _semantic_task_to_step(task, toolbox, session_context)
        if step is not None:
            planned_steps.append(step)
    if planned_steps:
        return planned_steps

    # Fallback to per-clause deterministic planning if the semantic planner returned partial data.
    planned_steps = []
    rolling_context = dict(session_context or {})
    for clause in _split_into_clauses(message):
        workflow_action, _ = _plan_workflow(clause, toolbox)
        if workflow_action is not None:
            planned_steps.append({"tool": workflow_action["tool"], "arguments": workflow_action.get("arguments", {})})
            rolling_context["pending_action"] = workflow_action
            continue
        mutation_action, _ = _plan_mutation(clause, toolbox, rolling_context)
        if mutation_action is not None:
            planned_steps.append({"tool": mutation_action["tool"], "arguments": mutation_action.get("arguments", {})})
            rolling_context["pending_action"] = mutation_action
            continue
        inspect_step = _plan_inspection_step(clause, toolbox)
        if inspect_step is not None:
            planned_steps.append(inspect_step)
    return planned_steps


def _pending_action_from_semantic_plan(
    plan: SemanticActionPlan,
    message: str,
    toolbox: AdminToolbox,
    session_context: dict | None = None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    prefers_french = _prefers_french(message)
    if _is_capability_question(message, session_context):
        return "advisory", None, None
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
            "mutate",
            {
                "intent": "mutation",
                "tool": "reindex_validated_documents",
                "arguments": {},
                "steps": [],
                "summary": "Reindex every validated document currently tracked by ingestion.",
            },
            "I am ready to reindex every validated document. Confirm to start it.",
        )

    if plan.action_type == "run_evaluation":
        dataset_path = str(plan.dataset_path or _extract_dataset_path(message))
        return (
            "mutate",
            {
                "intent": "mutation",
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
            "mutate",
            {
                "intent": "mutation",
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
    if _is_capability_question(message, session_context):
        return None, (
            "Je peux decrire les capacites disponibles sans lancer d'action."
            if prefers_french
            else "I can describe the available capabilities without starting an action."
        )
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
        top_k_retrieve = _extract_int_setting(
            lowered,
            [
                r"top[\s-]*k(?:\s+retrieve)?(?:\s+to)?\s+(\d+)",
                r"top[\s-]*k\s+(?:a|à)\s+r[eé]cup[eé]rer(?:\s+(?:a|à))?\s+(\d+)",
                r"(?:changer|modifier|mettre(?:\s+\w+)*)\s+le\s+top[\s-]*k\s+(?:a|à)\s+r[eé]cup[eé]rer(?:\s+(?:a|à))?\s+(\d+)",
                r"top[\s-]*k\s+de\s+r[eé]cup[eé]ration(?:\s+(?:a|à))?\s+(\d+)",
            ],
        )
        if top_k_retrieve is not None:
            changes["top_k_retrieve"] = top_k_retrieve
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
                "arguments": {"document_id": str(target.get("id") or ""), "target_names": [summary]},
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
        "Ce changement n'est pas encore expose par admin-service. Le service actuel peut executer la suppression de documents, le reindexing et les evaluations."
        if prefers_french
        else "That change is not exposed through admin-service yet. The current service can execute document deletion, reindexing, and evaluations."
    )


def _plan_pending_review(
    message: str, toolbox: AdminToolbox, session_context: dict | None = None
) -> tuple[dict[str, Any] | None, str] | None:
    """Plan a confirm/refuse action over pending documents.

    Confirm -> validate then preprocess + embed. Refuse -> status change only.
    Targets a named document (full or partial name, extension optional), the
    documents most recently discussed ("confirm them"), or all pending documents.
    Returns None when the message is not a pending-review request.
    """
    lowered = message.lower()
    is_confirm = bool(re.search(r"\b(confirm|approve|validate|accept|valider|approuver|confirmer|accepter)\b", lowered))
    is_refuse = bool(re.search(r"\b(refuse|reject|decline|deny|rejeter|refuser|décliner)\b", lowered))
    if not (is_confirm or is_refuse):
        return None
    tool_name = "confirm_pending_documents" if is_confirm else "refuse_pending_documents"

    has_doc_keyword = any(
        token in lowered
        for token in ["pending", "document", "documents", "doc", "docs", "file", "files", "en attente", "مستند", "ملف"]
    )
    has_filename = bool(re.search(r"[\w.\-]+\.(pdf|docx?|txt|md|csv|pptx?|xlsx?|json|html?)\b", lowered))
    refers_context = bool(re.search(r"\b(them|those|these|the ones|all of them|ceux|celles)\b", lowered))
    wants_all = bool(re.search(r"\b(all|every|everything|tous|toutes|tout)\b", lowered))

    arguments: dict[str, Any] = {}
    matches: list[dict[str, Any]] = []
    target_label = "all pending documents"

    # 1) "confirm/refuse them" -> the pending documents most recently discussed.
    if refers_context and not has_filename:
        ctx_docs = _documents_by_ids(toolbox, _document_ids_from_context(session_context))
        pending_ctx = [
            d for d in ctx_docs if isinstance(d, dict) and str(d.get("status") or "") == "pending"
        ]
        if pending_ctx:
            matches = pending_ctx
            arguments["document_ids"] = [str(d.get("id") or "") for d in pending_ctx if d.get("id")]
            target_label = (
                f"'{str(pending_ctx[0].get('original_name') or '')}'"
                if len(pending_ctx) == 1
                else f"{len(pending_ctx)} pending documents we discussed"
            )

    # 2) An explicit name/filename (full or partial, extension optional). Prefer a
    # literal filename so verb words inside it are never stripped; otherwise strip
    # the command words and match on what remains.
    if not matches:
        filename_match = re.search(
            r"[\w.\-]+\.(?:pdf|docx?|txt|md|csv|pptx?|xlsx?|json|html?)\b", message, re.IGNORECASE
        )
        if filename_match:
            guess = filename_match.group(0).strip()
        else:
            guess = re.sub(
                r"\b(confirm|approve|validate|accept|refuse|reject|decline|deny|"
                r"valider|approuver|confirmer|accepter|rejeter|refuser|décliner|"
                r"the|a|an|this|that|please|all|every|these|those|them|ones|"
                r"pending|document|documents|doc|docs|file|files|"
                r"named|called|titled|name)\b",
                " ",
                lowered,
            )
            guess = re.sub(r"\s+", " ", guess).strip(" :,'\"").strip()
        if guess and len(guess) >= 3:
            try:
                matches = toolbox.find_documents_by_filter(name_contains=guess, status="pending")
            except Exception:
                matches = []
            arguments["query"] = guess
            if len(matches) == 1:
                target_label = f"'{str(matches[0].get('original_name') or guess)}'"
            elif len(matches) > 1:
                target_label = f"{len(matches)} pending documents matching '{guess}'"
            else:
                target_label = f"pending documents matching '{guess}'"

    # 3) "confirm (all) pending documents" -> every pending document.
    if not matches and not arguments and (has_doc_keyword or wants_all):
        try:
            matches = toolbox.find_documents_by_filter(status="pending")
        except Exception:
            matches = []
        target_label = "all pending documents"

    # Only act when there is a genuine document target, so unrelated requests
    # (e.g. "validate all users") are never treated as a pending-document review.
    has_real_target = (
        bool(matches)
        or bool(arguments.get("document_ids"))
        or has_doc_keyword
        or has_filename
    )
    if not has_real_target:
        return None

    names = _doc_names(matches)
    if names:
        arguments["target_names"] = names[:8]
    arguments["match_count"] = len(matches)

    verb = "confirm" if is_confirm else "refuse"
    extra = " (validate, then preprocess + embed)" if is_confirm else " (status change only)"
    return (
        {
            "intent": "mutation",
            "tool": tool_name,
            "arguments": arguments,
            "steps": [],
            "summary": f"{verb.capitalize()} {target_label}{extra}.",
        },
        f"I am ready to {verb} {target_label}{extra}. Confirm to proceed.",
    )


_BULK_STOPWORDS = {
    "reindex", "reindexe", "rebuild", "reembed",
    "delete", "remove", "drop", "purge", "erase", "supprime", "supprimer", "supprimez",
    "all", "every", "everything", "each", "both", "tous", "toutes", "tout",
    "the", "a", "an", "this", "that", "these", "those", "them", "they", "it", "les", "le", "la",
    "document", "documents", "doc", "docs", "file", "files", "fichier", "fichiers",
    "from", "of", "in", "with", "and", "or", "please", "status", "are", "is", "to", "me", "my",
    "dated", "year", "named", "called", "titled", "name",
    "rejected", "refused", "declined", "denied", "failed", "invalid", "problematic",
    "validated", "approved", "accepted", "valid",
    "pending", "waiting", "queued", "embedded", "unembedded",
}


def _extract_doc_keywords(lowered: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", lowered)
    return [t for t in tokens if t not in _BULK_STOPWORDS and len(t) >= 2]


def _best_name_filter(
    keywords: list[str], toolbox: AdminToolbox, status: str | None, embedded: bool | None
) -> tuple[str | None, int]:
    """Pick the name filter that resolves to the most documents (combined phrase
    first, then individual tokens)."""
    if not keywords:
        return None, 0
    candidates = [" ".join(keywords)] + [k for k in keywords if k != " ".join(keywords)]
    best: str | None = None
    best_count = 0
    for candidate in candidates:
        try:
            matches = toolbox.find_documents_by_filter(
                name_contains=candidate, status=status, embedded=embedded
            )
        except Exception:
            matches = []
        if len(matches) > best_count:
            best, best_count = candidate, len(matches)
    return best, best_count


def _documents_by_ids(toolbox: AdminToolbox, ids: list[str]) -> list[dict[str, Any]]:
    try:
        all_docs = {
            str(d.get("id")): d
            for d in toolbox._fetch_documents()
            if isinstance(d, dict) and d.get("id")
        }
    except Exception:
        return [{"id": i} for i in ids]
    return [all_docs.get(str(i), {"id": i}) for i in ids]


def _document_ids_from_context(session_context: dict | None) -> list[str]:
    ctx = session_context or {}
    last = ctx.get("last_result")
    if not isinstance(last, dict):
        return []
    tool_result = last.get("tool_result")
    docs = tool_result.get("documents") if isinstance(tool_result, dict) else None
    if not isinstance(docs, list):
        return []
    return [str(d.get("id") or "") for d in docs if isinstance(d, dict) and d.get("id")]


def _plan_bulk_document_mutation(
    message: str, toolbox: AdminToolbox, session_context: dict | None = None
) -> tuple[dict[str, Any] | None, str] | None:
    """Plan a reindex/delete over many documents selected by status, name/category,
    embedded flag, an explicit "all", or a contextual "them". Returns None when the
    message is not a bulk document mutation."""
    lowered = message.lower()
    is_reindex = bool(re.search(r"\b(reindex|re-?index|reindexe|rebuild|re-?embed|reembed|réindex\w*|reindexer)\b", lowered))
    is_delete = bool(re.search(r"\b(delete|remove|drop|purge|erase|supprim\w*)\b", lowered))
    if not (is_reindex or is_delete):
        return None
    verb_tool = "bulk_reindex_by_filter" if is_reindex else "bulk_delete_by_filter"
    verb = "reindex" if is_reindex else "delete"

    status = None
    if re.search(r"\b(reject\w*|refus\w*|declin\w*|denied|deny|failed|invalid|problematic)\b", lowered):
        status = "rejected"
    elif re.search(r"\b(validated|approved|accepted)\b", lowered):
        status = "validated"
    elif re.search(r"\b(pending|waiting|queued)\b", lowered):
        status = "pending"

    embedded = None
    if re.search(r"(not embedded|unembedded|non[- ]embedded|without embedding)", lowered):
        embedded = False
    elif re.search(r"\bembedded\b", lowered):
        embedded = True

    wants_all = bool(re.search(r"\b(all|every|everything|each|tous|toutes|tout)\b", lowered))
    refers_them = bool(re.search(r"\b(them|those|these|they)\b", lowered))

    keywords = _extract_doc_keywords(lowered)
    name_filter, _ = _best_name_filter(keywords, toolbox, status, embedded)

    arguments: dict[str, Any] = {}

    matches: list[dict[str, Any]] = []
    # Contextual "reindex/delete them" -> act on the documents most recently shown.
    if refers_them and not name_filter and not status and embedded is None and not wants_all:
        ctx_ids = _document_ids_from_context(session_context)
        if not ctx_ids:
            return None
        arguments["document_ids"] = ctx_ids
        match_count = len(ctx_ids)
        matches = _documents_by_ids(toolbox, ctx_ids)
    else:
        if name_filter:
            arguments["name_contains"] = name_filter
        if status:
            arguments["status"] = status
        if embedded is not None:
            arguments["embedded"] = embedded
        if not arguments and not wants_all:
            return None  # No bulk selector; let single-document planners handle it.
        # A bare "reindex all" (no other selector) maps to the dedicated
        # validated-reindex, since only validated documents are embeddable.
        if is_reindex and wants_all and not arguments:
            return (
                {
                    "intent": "mutation",
                    "tool": "reindex_validated_documents",
                    "arguments": {},
                    "steps": [],
                    "summary": "Reindex every validated document.",
                },
                "I am ready to reindex all validated documents. Confirm to proceed.",
            )
        try:
            matches = toolbox.find_documents_by_filter(
                name_contains=arguments.get("name_contains"),
                status=arguments.get("status"),
                embedded=arguments.get("embedded"),
            )
        except Exception:
            matches = []
        match_count = len(matches)

    arguments["match_count"] = match_count
    names = _doc_names(matches)
    if names:
        arguments["target_names"] = names[:8]

    label_bits: list[str] = []
    if arguments.get("name_contains"):
        label_bits.append(f"matching '{arguments['name_contains']}'")
    if arguments.get("status"):
        label_bits.append(f"with status '{arguments['status']}'")
    if arguments.get("embedded") is True:
        label_bits.append("that are embedded")
    elif arguments.get("embedded") is False:
        label_bits.append("that are not embedded")
    if arguments.get("document_ids"):
        label_bits.append(f"({len(arguments['document_ids'])} selected)")
    scope = " ".join(label_bits) if label_bits else "all"
    target = f"{match_count} document(s) {scope}" if match_count else f"documents {scope}"

    return (
        {
            "intent": "mutation",
            "tool": verb_tool,
            "arguments": arguments,
            "steps": [],
            "summary": f"{verb.capitalize()} {target}.",
        },
        f"I am ready to {verb} {target}. Confirm to proceed.",
    )


def _plan_workflow(message: str, toolbox: AdminToolbox) -> tuple[dict[str, Any] | None, str]:
    lowered = message.lower()
    if _is_capability_question(message):
        return None, "I can summarize the available admin capabilities without starting a workflow."
    pending_plan = _plan_pending_review(message, toolbox)
    if pending_plan is not None:
        return pending_plan
    if "compare" in lowered and "evaluation" in lowered:
        pair = toolbox.resolve_report_pair(message)
        if pair is None:
            return None, "I need two evaluation report IDs to compare, or I can compare the two most recent reports if they exist."
        baseline_report_id, candidate_report_id = pair
        return (
            {
                "intent": "mutation",
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

    if "evaluation" in lowered and any(token in lowered for token in ["read", "show", "summarize", "explain"]):
        dataset_path = _extract_dataset_path(message)
        workflow_tasks = [
            {
                "task_id": "task_1",
                "kind": "mutation",
                "clause": "run evaluation",
                "status": "pending",
                "steps": [{"tool": "run_evaluation", "arguments": {"dataset_path": dataset_path}}],
                "outcome": {},
            },
            {
                "task_id": "task_2",
                "kind": "read",
                "clause": "read latest evaluation report",
                "status": "pending",
                "steps": [{"tool": "read_evaluation_report", "arguments": {"report_id": "latest"}}],
                "outcome": {},
            },
        ]
        return (
            {
                "intent": "mutation",
                "tool": "run_evaluation",
                "arguments": {"dataset_path": dataset_path},
                "steps": [],
                "task_index": 0,
                "workflow_tasks": workflow_tasks,
                "summary": f"Run evaluation with dataset '{dataset_path}' and then read the saved report.",
            },
            f"I am ready to run the evaluation with '{dataset_path}' and then read the saved report. Confirm to start it.",
        )

    if "evaluation" in lowered:
        dataset_path = _extract_dataset_path(message)
        return (
            {
                "intent": "mutation",
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
                "intent": "mutation",
                "tool": "reindex_validated_documents",
                "arguments": {},
                "steps": [],
                "summary": "Reindex every validated document currently tracked by ingestion.",
            },
            "I am ready to reindex every validated document. Confirm to start it.",
        )

    if "reindex" in lowered:
        guess = re.sub("reindex", "", message, flags=re.IGNORECASE).strip(" :")
        target = toolbox.find_document(guess) if guess else None
        if target is None:
            return None, "I can reindex one document if you tell me the exact document name or ID."
        summary = str(target.get("original_name") or target.get("storage_path") or target.get("id") or "document")
        return (
            {
                "intent": "mutation",
                "tool": "reindex_document",
                "arguments": {"document_id": str(target.get("id") or ""), "target_names": [summary]},
                "steps": [],
                "summary": f"Reindex document '{summary}'.",
            },
            f"I found the document '{summary}'. Confirm if you want me to rebuild its embeddings.",
        )

    return None, "I could not map that requested operation to a supported action yet."


def _plan_inspection_step(message: str, toolbox: AdminToolbox) -> dict[str, Any] | None:
    lowered = message.lower()
    if _is_capability_question(message):
        return None
    if _is_chunking_methods_question(message):
        return {"tool": "get_chunking_methods", "arguments": {}}
    if _is_reranking_methods_question(message):
        return {"tool": "get_reranking_methods", "arguments": {}}
    if any(token in lowered for token in ["embedding", "embeddings", "embedding model"]):
        return {"tool": "get_repo_config", "arguments": {"service_name": "embedding"}}
    if any(token in lowered for token in ["generation model", "generation settings"]):
        return {"tool": "get_repo_config", "arguments": {"service_name": "generation"}}
    if any(token in lowered for token in ["rerank", "reranking", "reranker", "ranker"]):
        return {"tool": "get_repo_config", "arguments": {"service_name": "retrieval"}}
    if any(token in lowered for token in ["chunk", "chunking", "chunk overlap", "chunk size"]):
        return {"tool": "get_repo_config", "arguments": {"service_name": "preprocessing"}}
    if "evaluation" in lowered and any(token in lowered for token in ["last", "latest", "recent", "current"]):
        return {"tool": "read_evaluation_report", "arguments": {"report_id": "latest"}}
    if "evaluation" in lowered and any(token in lowered for token in ["report", "reports"]):
        return {"tool": "list_evaluation_reports", "arguments": {}}
    if any(token in lowered for token in ["ingestion", "document status", "status"]) and "document" not in lowered:
        return {"tool": "get_ingestion_status", "arguments": {}}
    _STATUS_SYNONYMS: dict[str, list[str]] = {
        "rejected": ["rejected", "refused", "declined", "denied"],
        "validated": ["validated", "approved", "accepted", "valid"],
        "pending": ["pending", "waiting", "queued", "in progress", "processing"],
        "error": ["error", "failed", "broken", "errored"],
    }
    if "document" in lowered:
        for canonical_status, synonyms in _STATUS_SYNONYMS.items():
            if any(syn in lowered for syn in synonyms):
                return {"tool": "find_documents_by_filter", "arguments": {"status": canonical_status}}
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
    return {
        "intent": "mutation",
        "tool": "compound_action",
        "arguments": {},
        "steps": [{"tool": step["tool"], "arguments": step.get("arguments", {})} for step in steps],
        "summary": "Execute the planned admin actions in order.",
    }


def _task_kind_for_clause(clause: str, tool_name: str) -> str:
    if tool_name in {
        "update_repo_config",
        "delete_document_completely",
        "reindex_document",
        "reindex_validated_documents",
        "run_evaluation",
        "compare_evaluation_reports",
    }:
        return "mutation"
    if _is_chunking_advantages_request(clause) or _is_reranking_advantages_request(clause):
        return "advice"
    return "read"


def _build_workflow_task(task_id: str, clause: str, step: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "kind": _task_kind_for_clause(clause, str(step.get("tool") or "")),
        "clause": clause,
        "status": "pending",
        "steps": [
            {
                "tool": str(step.get("tool") or ""),
                "arguments": step.get("arguments", {}) if isinstance(step.get("arguments"), dict) else {},
            }
        ],
        "outcome": {},
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


def _safe_capability_call(
    tool_name: str,
    loader: Callable[[], dict[str, Any]],
    activity: list[dict[str, Any]],
    progress_callback: ProgressCallback | None,
) -> dict[str, Any] | None:
    started_item = _progress_item(
        phase="tool",
        status="in_progress",
        title=f"Tool started: {tool_name}",
        detail="Collecting live capability data from a backend service.",
        tool=tool_name,
        arguments={},
    )
    activity.append(started_item)
    _emit_progress(progress_callback, started_item)
    try:
        result = loader()
    except Exception as exc:
        failed_item = _progress_item(
            phase="tool",
            status="failed",
            title=f"Tool failed: {tool_name}",
            detail=str(exc),
            tool=tool_name,
            arguments={},
        )
        activity.append(failed_item)
        _emit_progress(progress_callback, failed_item)
        return None

    completed_item = _progress_item(
        phase="tool",
        status="completed",
        title=f"Tool executed: {tool_name}",
        detail="The agent collected live capability data.",
        tool=tool_name,
        arguments={},
    )
    activity.append(completed_item)
    _emit_progress(progress_callback, completed_item)
    return result


def _build_capability_answer(
    message: str,
    toolbox: AdminToolbox,
    activity: list[dict[str, Any]],
    progress_callback: ProgressCallback | None = None,
) -> tuple[str, dict[str, Any]]:
    capabilities = toolbox.get_capabilities()
    live_state: dict[str, Any] = {}

    chunking = _safe_capability_call("get_chunking_methods", toolbox.get_chunking_methods, activity, progress_callback)
    if isinstance(chunking, dict):
        live_state["chunking"] = chunking

    reranking = _safe_capability_call("get_reranking_methods", toolbox.get_reranking_methods, activity, progress_callback)
    if isinstance(reranking, dict):
        live_state["reranking"] = reranking

    preprocessing_config = _safe_capability_call(
        "get_repo_config",
        lambda: toolbox.get_repo_config("preprocessing"),
        activity,
        progress_callback,
    )
    if isinstance(preprocessing_config, dict):
        live_state["preprocessing_config"] = preprocessing_config

    retrieval_config = _safe_capability_call(
        "get_repo_config",
        lambda: toolbox.get_repo_config("retrieval"),
        activity,
        progress_callback,
    )
    if isinstance(retrieval_config, dict):
        live_state["retrieval_config"] = retrieval_config

    embedding_config = _safe_capability_call(
        "get_repo_config",
        lambda: toolbox.get_repo_config("embedding"),
        activity,
        progress_callback,
    )
    if isinstance(embedding_config, dict):
        live_state["embedding_config"] = embedding_config

    generation_config = _safe_capability_call(
        "get_repo_config",
        lambda: toolbox.get_repo_config("generation"),
        activity,
        progress_callback,
    )
    if isinstance(generation_config, dict):
        live_state["generation_config"] = generation_config

    ingestion_status = _safe_capability_call("get_ingestion_status", toolbox.get_ingestion_status, activity, progress_callback)
    if isinstance(ingestion_status, dict):
        live_state["ingestion_status"] = ingestion_status

    documents = _safe_capability_call("list_loaded_documents", toolbox.list_loaded_documents, activity, progress_callback)
    if isinstance(documents, dict):
        live_state["documents"] = documents

    reports = _safe_capability_call("list_evaluation_reports", toolbox.list_evaluation_reports, activity, progress_callback)
    if isinstance(reports, dict):
        live_state["reports"] = reports

    services = capabilities.get("services", {}) if isinstance(capabilities, dict) else {}
    workflow_tools = capabilities.get("workflow_tools", []) if isinstance(capabilities, dict) else []

    read_scopes = ", ".join(sorted(services.keys())) if isinstance(services, dict) else ""
    update_scopes = ", ".join(sorted(services.keys())) if isinstance(services, dict) else ""
    workflow_labels = []
    for tool_name in workflow_tools if isinstance(workflow_tools, list) else []:
        if tool_name == "delete_document_completely":
            workflow_labels.append("delete a document and clean its vectors")
        elif tool_name == "reindex_document":
            workflow_labels.append("reindex one document (by name or id)")
        elif tool_name == "reindex_validated_documents":
            workflow_labels.append("reindex all validated documents")
        elif tool_name == "bulk_reindex_by_filter":
            workflow_labels.append("reindex many documents at once (by name/category, status, or all)")
        elif tool_name == "bulk_delete_by_filter":
            workflow_labels.append("delete many documents at once (by name/category, status, or all)")
        elif tool_name == "confirm_pending_documents":
            workflow_labels.append("confirm pending documents (validate, then preprocess + embed) — one, several, or all")
        elif tool_name == "refuse_pending_documents":
            workflow_labels.append("refuse pending documents (mark as rejected) — one, several, or all")
        elif tool_name == "run_evaluation":
            workflow_labels.append("run an evaluation")
        elif tool_name == "compare_evaluation_reports":
            workflow_labels.append("compare evaluation reports")

    chunking_methods = []
    current_chunking = ""
    if isinstance(chunking, dict):
        chunking_methods = [
            str(item.get("name") or "")
            for item in chunking.get("methods", [])
            if isinstance(item, dict) and item.get("implemented")
        ]
        current_chunking = str(chunking.get("current_strategy") or "")

    reranking_methods = []
    current_reranking = ""
    if isinstance(reranking, dict):
        reranking_methods = [
            str(item.get("name") or "")
            for item in reranking.get("methods", [])
            if isinstance(item, dict) and item.get("implemented")
        ]
        current_reranking = str(reranking.get("current_default_ranker_type") or "")

    live_lines: list[str] = []
    if isinstance(ingestion_status, dict):
        total_documents = ingestion_status.get("total_documents")
        embedded_documents = ingestion_status.get("embedded_documents")
        if total_documents is not None and embedded_documents is not None:
            live_lines.append(f"- Documents in ingestion: {total_documents}; embedded: {embedded_documents}")
    if isinstance(documents, dict):
        docs = documents.get("documents", [])
        if isinstance(docs, list):
            live_lines.append(f"- Loaded documents visible right now: {len(docs)}")
            pending_count = sum(
                1 for d in docs if isinstance(d, dict) and str(d.get("status") or "") == "pending"
            )
            if pending_count:
                live_lines.append(
                    f"- Pending documents awaiting your review (confirm/refuse): {pending_count}"
                )
    if isinstance(reports, dict):
        report_list = reports.get("reports", [])
        if isinstance(report_list, list):
            live_lines.append(f"- Saved evaluation reports: {len(report_list)}")
    if current_chunking:
        live_lines.append(f"- Current chunking strategy: `{current_chunking}`")
    if current_reranking:
        live_lines.append(f"- Current reranking strategy: `{current_reranking}`")

    config_lines: list[str] = []
    for label, payload in [
        ("preprocessing", preprocessing_config),
        ("retrieval", retrieval_config),
        ("embedding", embedding_config),
        ("generation", generation_config),
    ]:
        if not isinstance(payload, dict):
            continue
        config = payload.get("config", {})
        if not isinstance(config, dict):
            continue
        keys = ", ".join(sorted(config.keys()))
        if keys:
            config_lines.append(f"- `{label}` settings: {keys}")

    answer_lines = [
        "My name is `Synapse`.",
        "",
        "I can help with these admin tasks:",
        "",
        "### Read-Only Inspections",
        f"- Inspect current settings for `{read_scopes}`" if read_scopes else "- Inspect current system settings",
        "- Show available chunking and reranking methods",
        "- Check ingestion status, loaded documents, and saved evaluation reports",
        "",
        "### Supported Configuration Changes",
        f"- Update supported settings for `{update_scopes}` after confirmation" if update_scopes else "- Update supported settings after confirmation",
        "",
        "### Document And Evaluation Workflows",
    ]
    answer_lines.extend(f"- {item}" for item in workflow_labels)

    if chunking_methods or reranking_methods:
        answer_lines.extend(
            [
                "",
                "### Live Defaults",
                f"- Available chunking strategies: {', '.join(chunking_methods)}" if chunking_methods else "- Chunking methods are available",
                f"- Available reranking strategies: {', '.join(reranking_methods)}" if reranking_methods else "- Reranking methods are available",
            ]
        )
    if live_lines:
        answer_lines.extend(["", "### Live Status", *live_lines])
    if config_lines:
        answer_lines.extend(["", "### Configuration Areas", *config_lines])

    answer_lines.extend(
        [
            "",
            "I can describe or inspect any of these without starting a change. Mutations only happen after an explicit confirmation.",
        ]
    )

    return "\n".join(answer_lines), {"capabilities": capabilities, "live_state": live_state}


def _plan_request(
    message: str,
    requested_route: str,
    toolbox: AdminToolbox,
    settings: Settings,
    session_context: dict | None = None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    if _is_identity_question(message):
        return "advisory", None, _build_identity_answer(message)

    if _is_capability_question(message, session_context):
        return "advisory", None, None

    # Safety guard: a read-only document listing/status question (e.g. "which
    # documents were rejected or failed?") must be inspected, never routed to a
    # destructive mutation like reindex_validated_documents.
    if _is_document_inspection_question(message):
        return "inspect", None, None

    # Confirm/refuse of pending documents is a mutation, not an inspection.
    # Detect it deterministically before the LLM planners so an ambiguous verb
    # like "confirm <file>.pdf" is never misrouted to a read.
    pending_review = _plan_pending_review(message, toolbox, session_context)
    if pending_review is not None:
        pending_action, pending_answer = pending_review
        if pending_action is not None:
            return "mutate", pending_action, pending_answer

    # Bulk reindex/delete over many documents (by status, name/category, embedded
    # flag, "all", or a contextual "them"). Handled deterministically before the
    # single-document planners so e.g. "reindex cybersecurity files" hits all of
    # them, not just one.
    bulk_review = _plan_bulk_document_mutation(message, toolbox, session_context)
    if bulk_review is not None:
        bulk_action, bulk_answer = bulk_review
        if bulk_action is not None:
            return "mutate", bulk_action, bulk_answer

    clauses = _split_into_clauses(message)
    planned_steps: list[dict[str, Any]] = []
    workflow_tasks: list[dict[str, Any]] = []
    rolling_context: dict[str, Any] = dict(session_context or {})

    semantic_task_plan = _semantic_task_planner(message, settings, toolbox, session_context)
    if semantic_task_plan is not None and semantic_task_plan.tasks:
        planned_steps = _planned_steps_from_semantic_tasks(message, semantic_task_plan, toolbox, session_context)
        if planned_steps:
            for index, step in enumerate(planned_steps):
                clause = clauses[index] if index < len(clauses) else message
                workflow_tasks.append(_build_workflow_task(f"task_{len(workflow_tasks) + 1}", clause, step))

    if not planned_steps and len(clauses) <= 1:
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
        if requested_route == "mutate":
            pending_action, answer = _plan_mutation(message, toolbox, session_context)
            if pending_action is not None:
                return "mutate", pending_action, answer
            pending_action, answer = _plan_workflow(message, toolbox)
            if pending_action is not None:
                return "mutate", pending_action, answer
        pending_action, answer = _plan_workflow(message, toolbox)
        if pending_action is not None:
            return "mutate", pending_action, answer
        pending_action, answer = _plan_mutation(message, toolbox, session_context)
        if pending_action is not None:
            return "mutate", pending_action, answer
        if requested_route in {"mutate"}:
            return "advisory", None, None
        return requested_route, None, None

    if not planned_steps:
        for clause in clauses:
            semantic_plan = _semantic_action_planner(clause, settings, rolling_context)
            if semantic_plan is not None:
                semantic_route, semantic_action, _ = _pending_action_from_semantic_plan(
                    semantic_plan,
                    clause,
                    toolbox,
                    rolling_context,
                )
                if semantic_action is not None:
                    planned_step = {"tool": semantic_action["tool"], "arguments": semantic_action.get("arguments", {})}
                    planned_steps.append(planned_step)
                    workflow_tasks.append(_build_workflow_task(f"task_{len(workflow_tasks) + 1}", clause, planned_step))
                    if semantic_action.get("tool") == "update_repo_config":
                        rolling_context["pending_action"] = semantic_action
                        rolling_context["last_topic"] = "update_repo_config"
                    continue
            workflow_action, _ = _plan_workflow(clause, toolbox)
            if workflow_action is not None:
                planned_step = {"tool": workflow_action["tool"], "arguments": workflow_action.get("arguments", {})}
                planned_steps.append(planned_step)
                workflow_tasks.append(_build_workflow_task(f"task_{len(workflow_tasks) + 1}", clause, planned_step))
                rolling_context["pending_action"] = workflow_action
                continue

            mutation_action, _ = _plan_mutation(clause, toolbox, rolling_context)
            if mutation_action is not None:
                planned_step = {"tool": mutation_action["tool"], "arguments": mutation_action.get("arguments", {})}
                planned_steps.append(planned_step)
                workflow_tasks.append(_build_workflow_task(f"task_{len(workflow_tasks) + 1}", clause, planned_step))
                if mutation_action.get("tool") == "update_repo_config":
                    rolling_context["pending_action"] = mutation_action
                    rolling_context["last_topic"] = "update_repo_config"
                continue

            inspect_step = _plan_inspection_step(clause, toolbox)
            if inspect_step is not None:
                planned_steps.append(inspect_step)
                workflow_tasks.append(_build_workflow_task(f"task_{len(workflow_tasks) + 1}", clause, inspect_step))

    if len(planned_steps) > 1:
        pending_action = _build_compound_pending_action(planned_steps)
        pending_action["workflow_tasks"] = workflow_tasks
        return "mutate", pending_action, _summarize_compound_plan(planned_steps)
    if len(planned_steps) == 1:
        single = planned_steps[0]
        if single.get("tool") in {
            "update_repo_config",
            "delete_document_completely",
            "reindex_document",
            "reindex_validated_documents",
            "run_evaluation",
            "compare_evaluation_reports",
        }:
            return (
                "mutate",
                {
                    "intent": "mutation",
                    "tool": str(single.get("tool") or ""),
                    "arguments": single.get("arguments", {}) if isinstance(single.get("arguments"), dict) else {},
                    "steps": [],
                    "task_index": 0,
                    "workflow_tasks": workflow_tasks or [_build_workflow_task("task_1", clauses[0], single)],
                },
                _summarize_compound_plan(planned_steps),
            )

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
        advisory_started = _progress_item(
            phase="advisory",
            status="in_progress",
            title="Preparing advisory answer",
            detail="Gathering the context needed to answer the request clearly.",
        )
        _emit_progress(progress_callback, advisory_started)
        if _is_capability_question(state["message"], state.get("session_context")):
            activity = list(state.get("activity", []))
            activity.append(advisory_started)
            answer, tool_result = _build_capability_answer(
                state["message"],
                toolbox,
                activity,
                progress_callback,
            )
            advisory_completed = _progress_item(
                phase="advisory",
                status="completed",
                title="Capabilities prepared",
                detail="The available admin capabilities were summarized with safe live checks.",
            )
            activity.append(advisory_completed)
            _emit_progress(progress_callback, advisory_completed)
            return {
                **state,
                "status": "completed",
                "final_answer": _normalize_user_answer(answer),
                "current_step": "summarize",
                "activity": activity,
                "tool_result": tool_result,
                "tool_call_count": len(tool_result.get("live_state", {})) if isinstance(tool_result, dict) else 0,
                "tool_cache_updates": {},
            }

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
    graph.add_node("summarize_llm", summarize)

    graph.add_edge(START, "classify_intent_llm")
    graph.add_conditional_edges(
        "classify_intent_llm",
        route,
        {
            "advisory": "advisory_agent",
            "inspect": "inspect_agent",
            "mutate": "mutate_executor",
        },
    )
    graph.add_edge("advisory_agent", "summarize_llm")
    graph.add_edge("inspect_agent", "summarize_llm")
    graph.add_edge("mutate_executor", "summarize_llm")
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
