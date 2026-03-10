MUTATING_TOOLS = {
    "delete_document",
    "delete_documents_batch",
    "delete_validated_documents",
    "embed_document",
    "embed_validated_documents",
    "reindex_corpus",
    "update_chunking_config",
    "update_embedding_model",
    "update_reranker_config",
    "run_rag_evaluation",
    "restart_services",
}


def needs_confirmation(tool_name: str, require_confirmation_for_mutations: bool) -> bool:
    return require_confirmation_for_mutations and tool_name in MUTATING_TOOLS
