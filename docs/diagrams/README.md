# Diagrams

This folder contains the first UML-style diagrams for the Agentic RAG platform.

Current diagrams:

- `authentication-sequence-diagram.md`: user and admin authentication flow
- `general-use-case-diagram.puml`: general PlantUML use case diagram
- `system-component-diagram.md`: high-level component/service view
- `ingestion-sequence-diagram.md`: document upload and indexing workflow
- `query-generation-sequence-diagram.md`: grounded question-answer workflow

These diagrams use Mermaid so they can be previewed directly in editors that support Markdown diagram rendering.

Recommended workflow:

1. Start with the system component diagram.
2. Review the two sequence diagrams.
3. Add service-level class diagrams only for the services you need to explain in detail.

Primary source files used:

- `README.md`
- `docker-compose.yml`
- `docs/api_spec/*.openapi.yaml`
- service-level `README.md` files
