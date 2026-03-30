# Docker Infrastructure

Docker is used to run the local multi-service stack and supporting dependencies.

Primary entrypoint:

- project root `docker-compose.yml`
- `start-stack.ps1`
- `stop-stack.ps1`

Main containers:

- `weaviate`
- `auth-service`
- `preprocessing-service`
- `embedding-service`
- `retrieval-service`
- `generation-service`
- `ingestion-service`
- `admin-service`

Typical commands:

```powershell
docker compose up -d --build
docker compose down
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Helper scripts:

Start the full stack:

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\start-stack.ps1
```

Stop the full stack:

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\stop-stack.ps1
```
