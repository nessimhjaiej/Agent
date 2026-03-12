from __future__ import annotations

import subprocess
from pathlib import Path

from app.models import ToolExecutionResult
from app.tools.base import ToolMetadata


class RestartServicesTool:
    name = "restart_services"
    metadata = ToolMetadata(
        name=name,
        description="Restart one or more backend services either in the local process setup or with Docker Compose.",
        arguments_schema={
            "services": {
                "type": "array",
                "required": True,
                "items": {"type": "string"},
                "description": "Service names to restart.",
            },
            "delay_seconds": {
                "type": "integer",
                "required": False,
                "description": "Delay before the local restart script runs.",
            },
            "runtime": {
                "type": "string",
                "required": False,
                "enum": ["local", "docker_compose"],
                "description": "Runtime used to restart services.",
            },
        },
        output_description="Returns the selected runtime, services scheduled for restart, and script or compose path details.",
        requires_confirmation=True,
    )

    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path(__file__).resolve().parents[4]
        self._local_script_path = self._project_root / "scripts" / "restart-local-services.ps1"
        self._compose_file_path = self._project_root / "docker-compose.yml"

    def execute(self, arguments: dict) -> ToolExecutionResult:
        services_raw = arguments.get("services", [])
        services = [str(service).strip() for service in services_raw if str(service).strip()]
        if not services:
            raise ValueError("services must contain at least one service name")

        runtime = str(arguments.get("runtime", "local")).strip().lower() or "local"
        if runtime == "local":
            return self._execute_local(services, delay_seconds=int(arguments.get("delay_seconds", 2)))
        if runtime == "docker_compose":
            return self._execute_docker_compose(services)
        raise ValueError("runtime must be one of: local, docker_compose")

    def _execute_local(self, services: list[str], delay_seconds: int) -> ToolExecutionResult:
        command = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self._local_script_path),
            "-Services",
            *services,
            "-DelaySeconds",
            str(delay_seconds),
        ]
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            command,
            cwd=self._project_root,
            creationflags=creationflags,
        )
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Scheduled local restart for services: {', '.join(services)}. "
                f"The restart script will begin in about {delay_seconds} seconds."
            ),
            result={
                "runtime": "local",
                "services": services,
                "delay_seconds": delay_seconds,
                "script_path": str(self._local_script_path),
            },
        )

    def _execute_docker_compose(self, services: list[str]) -> ToolExecutionResult:
        command = [
            "docker",
            "compose",
            "-f",
            str(self._compose_file_path),
            "restart",
            *services,
        ]
        subprocess.Popen(
            command,
            cwd=self._project_root,
        )
        return ToolExecutionResult(
            status="ok",
            answer=f"Scheduled Docker Compose restart for services: {', '.join(services)}.",
            result={
                "runtime": "docker_compose",
                "services": services,
                "compose_file": str(self._compose_file_path),
            },
        )
