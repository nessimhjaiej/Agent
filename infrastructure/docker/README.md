# Docker Infrastructure

Docker is used to run the local multi-service stack and supporting dependencies.

Primary entrypoint:

- project root `docker-compose.yml`
- `start-stack.ps1`
- `stop-stack.ps1`
- `logs.ps1`
- `restart-services.ps1`
- `status.ps1`

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
This builds images when needed and starts all services defined in the root compose file.

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\start-stack.ps1
```

Stop the full stack:
This stops and removes the compose-managed containers for the project.

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\stop-stack.ps1
```

Show running container status:
This shows which project containers are up, their current status, and exposed ports.

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\status.ps1
```

Restart selected services:
This restarts only the specified services without tearing down the whole stack.

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\restart-services.ps1 -Services retrieval-service,generation-service
```

Show logs:
This prints recent container output for the whole compose stack. Use it to inspect runtime messages, errors, warnings, startup failures, or request traces written by the services.

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\logs.ps1
```

Show logs for selected services:
This prints recent container output only for the services you name, which is useful when you want to debug one backend service without the noise from the rest of the stack.

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\logs.ps1 -Services retrieval-service,generation-service -Tail 200
```

Follow logs:
This streams live container output for the selected service until you stop it. Use it while reproducing an issue so you can watch new log lines appear in real time.

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\logs.ps1 -Services generation-service -Follow
```
