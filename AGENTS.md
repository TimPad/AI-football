<claude-mem-context>
# Memory Context

# [AI-football] recent context, 2026-10-15 12:08pm GMT+3

No previous sessions found.
</claude-mem-context>
# Project guidance

- See README.md for the current implementation and setup; docs/README.md indexes detailed and historical documents.
- Python dependencies are locked in uv.lock; frontend dependencies in web/package-lock.json. Use `uv sync --locked --all-extras` and `npm --prefix web ci`.
- Format and lint before finishing: `ruff format` + `ruff check` for Python, `npm --prefix web run format` for the frontend; CI enforces both. Details are in CONTRIBUTING.md.
- Run backend tests against the dedicated test databases, never clear organizer data. Test commands are in CONTRIBUTING.md.
- Keep manual protocol and CV analytics separate. Player identity is a stable UUID; track IDs and shirt numbers are review hints.
- Add new Alembic migrations for schema changes. Preserve confirmed versions, request idempotency and independent publication.
- Do not add local video, participant photos, model weights, .env, databases, backups or result archives to Git. Use synthetic fixtures for ordinary tests.
- Connected Processor, OCR, masks, S3 and the Colab notebook remain future work until implemented and verified.
