# OpenAI Usage Script

This folder includes a PowerShell helper for checking OpenAI organization usage and costs from the terminal.

Script:

- `check-usage.ps1`

It calls the official OpenAI organization usage endpoints:

- `/v1/organization/costs`
- `/v1/organization/usage/completions`
- `/v1/organization/usage/embeddings`
- `/v1/organization/usage/audio_transcriptions`

## Requirements

- PowerShell
- an OpenAI key with permission to read organization usage data

The OpenAI docs show these usage endpoints with `OPENAI_ADMIN_KEY`, so a standard project key may not be sufficient.

## Usage

From the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\openai\check-usage.ps1
```

Custom window:

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\openai\check-usage.ps1 -Days 30
```

Explicit key:

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\openai\check-usage.ps1 -OpenAIAdminKey "<your-key>"
```

Optional org or project headers:

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\openai\check-usage.ps1 `
  -Days 14 `
  -OrganizationId "org_..." `
  -ProjectId "proj_..."
```

## Environment Variables

The script checks these in order:

- `OPENAI_ADMIN_KEY`
- `OPENAI_KEY`

If neither is set in the current shell, it automatically tries to read them from the repo root `.env`.

## Notes

- Costs are the best source for billing-style totals.
- Usage and costs may not reconcile perfectly at fine granularity.
- If the script fails with a permissions error, the key likely does not have organization usage access.
