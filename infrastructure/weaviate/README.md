# Weaviate Local Infrastructure

This folder contains local infrastructure assets for Weaviate used by the embedding service.

## Files

- `docker-compose.yml`: local Weaviate instance (HTTP + gRPC, persistent volume).
- `schema.chunk.json`: `Chunk` class schema for manual vectors with cosine distance.
- `bootstrap-schema.ps1`: idempotent class creation script.
- `.env.example`: environment variables used by embedding service.

## Start Weaviate

```powershell
docker compose -f infrastructure/weaviate/docker-compose.yml up -d
```

## Verify readiness

```powershell
Invoke-RestMethod http://localhost:8080/v1/.well-known/ready
```

Expected response: `READY`

## Bootstrap `Chunk` schema

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/weaviate/bootstrap-schema.ps1 `
  -BaseUrl "http://localhost:8080" `
  -SchemaPath "infrastructure/weaviate/schema.chunk.json"
```

## Check schema

```powershell
Invoke-RestMethod http://localhost:8080/v1/schema
```

## Stop Weaviate

```powershell
docker compose -f infrastructure/weaviate/docker-compose.yml down
```
