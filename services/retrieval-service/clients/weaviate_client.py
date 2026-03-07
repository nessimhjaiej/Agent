import json

import httpx

from app.errors import RetrievalProviderError


class WeaviateClient:
    def __init__(self, base_url: str, collection: str, timeout_seconds: float = 20.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._collection = collection
        self._client = httpx.Client(timeout=timeout_seconds, trust_env=False)

    def bm25_search(self, query: str, top_k: int, filters: dict) -> list[dict]:
        where_clause = self._build_where_clause(filters)
        filter_segment = f", where: {where_clause}" if where_clause else ""
        gql = f"""
        {{
          Get {{
            {self._collection}(
              bm25: {{ query: {json.dumps(query)} }}
              limit: {top_k}
              {filter_segment}
            ) {{
              chunk_id
              document_id
              chunk_text
              source_type
              source_uri
              source_filename
              language
              chunk_index
              start_char
              end_char
              char_count
              token_count_estimate
              chunking_strategy
              document_checksum
              normalization_version
              pipeline_version
              created_at
              _additional {{
                score
              }}
            }}
          }}
        }}
        """

        try:
            response = self._client.post(f"{self._base_url}/v1/graphql", json={"query": gql})
        except httpx.HTTPError as exc:
            raise RetrievalProviderError(f"Weaviate BM25 request failed: {exc}") from exc

        if response.status_code >= 400:
            raise RetrievalProviderError(
                f"Weaviate BM25 request failed {response.status_code}: {response.text}"
            )

        payload = response.json()
        errors = payload.get("errors")
        if errors:
            raise RetrievalProviderError(f"Weaviate BM25 GraphQL error: {errors}")

        data = payload.get("data", {}).get("Get", {}).get(self._collection, [])
        if not isinstance(data, list):
            raise RetrievalProviderError("Unexpected Weaviate BM25 response shape")
        return data

    def vector_search(self, query_vector: list[float], top_k: int, filters: dict) -> list[dict]:
        where_clause = self._build_where_clause(filters)
        filter_segment = f", where: {where_clause}" if where_clause else ""
        gql = f"""
        {{
          Get {{
            {self._collection}(
              nearVector: {{ vector: {json.dumps(query_vector)} }}
              limit: {top_k}
              {filter_segment}
            ) {{
              chunk_id
              document_id
              chunk_text
              source_type
              source_uri
              source_filename
              language
              chunk_index
              start_char
              end_char
              char_count
              token_count_estimate
              chunking_strategy
              document_checksum
              normalization_version
              pipeline_version
              created_at
              _additional {{
                distance
              }}
            }}
          }}
        }}
        """

        try:
            response = self._client.post(f"{self._base_url}/v1/graphql", json={"query": gql})
        except httpx.HTTPError as exc:
            raise RetrievalProviderError(f"Weaviate vector request failed: {exc}") from exc

        if response.status_code >= 400:
            raise RetrievalProviderError(
                f"Weaviate vector request failed {response.status_code}: {response.text}"
            )

        payload = response.json()
        errors = payload.get("errors")
        if errors:
            raise RetrievalProviderError(f"Weaviate vector GraphQL error: {errors}")

        data = payload.get("data", {}).get("Get", {}).get(self._collection, [])
        if not isinstance(data, list):
            raise RetrievalProviderError("Unexpected Weaviate vector response shape")
        return data

    def _build_where_clause(self, filters: dict) -> str:
        if not filters:
            return ""

        supported_text_keys = {"document_id", "source_type", "language"}
        operands: list[str] = []
        for key, value in filters.items():
            if key not in supported_text_keys:
                continue
            if not isinstance(value, str) or not value:
                continue
            operands.append(
                "{ path: [%s], operator: Equal, valueText: %s }"
                % (json.dumps(key), json.dumps(value))
            )

        if not operands:
            return ""
        if len(operands) == 1:
            return operands[0]
        return "{ operator: And, operands: [%s] }" % ", ".join(operands)
