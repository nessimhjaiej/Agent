from __future__ import annotations

import re
from pathlib import Path


_ENV_LINE_RE = re.compile(r"^([A-Z0-9_]+)=(.*)$")


class EnvConfigStore:
    def __init__(
        self,
        project_root: Path | None = None,
        env_path: Path | None = None,
        env_local_path: Path | None = None,
    ) -> None:
        self._project_root = project_root or Path(__file__).resolve().parents[4]
        self._env_path = env_path or (self._project_root / ".env")
        self._env_local_path = env_local_path or (self._project_root / ".env.local")

    def get(self, key: str, default: str | None = None) -> str | None:
        local_values = self._read_env_file(self._env_local_path)
        if key in local_values:
            return local_values[key]

        base_values = self._read_env_file(self._env_path)
        if key in base_values:
            return base_values[key]
        return default

    def set_many(self, values: dict[str, str]) -> Path:
        existing_lines = []
        if self._env_local_path.exists():
            existing_lines = self._env_local_path.read_text(encoding="utf-8").splitlines()

        remaining = dict(values)
        updated_lines: list[str] = []
        for line in existing_lines:
            match = _ENV_LINE_RE.match(line.strip())
            if not match:
                updated_lines.append(line)
                continue

            key = match.group(1)
            if key in remaining:
                updated_lines.append(f"{key}={remaining.pop(key)}")
            else:
                updated_lines.append(line)

        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")

        for key, value in remaining.items():
            updated_lines.append(f"{key}={value}")

        payload = "\n".join(updated_lines).rstrip() + "\n"
        self._env_local_path.parent.mkdir(parents=True, exist_ok=True)
        self._env_local_path.write_text(payload, encoding="utf-8")
        return self._env_local_path

    def _read_env_file(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}

        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _ENV_LINE_RE.match(stripped)
            if match:
                values[match.group(1)] = match.group(2)
        return values
