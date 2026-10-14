<claude-mem-context>
# Memory Context

# [AI-football] recent context, 2026-10-13 7:01pm GMT+3

No previous sessions found.
</claude-mem-context>
# Project guidance

- See README.md for the current implementation and setup; docs/README.md indexes detailed and historical documents.
- Python dependencies are locked in uv.lock; frontend dependencies in web/package-lock.json. Use `uv sync --locked --all-extras` and `npm --prefix web ci`.
- Run backend tests against the dedicated test databases, never clear organizer data. Test commands are in CONTRIBUTING.md.
- Keep manual protocol and CV analytics separate. Player identity is a stable UUID; track IDs and shirt numbers are review hints.
- Add new Alembic migrations for schema changes. Preserve confirmed versions, request idempotency and independent publication.
- Do not add local video, participant photos, model weights, .env, databases, backups or result archives to Git. Use synthetic fixtures for ordinary tests.
- Connected Processor, OCR, masks, S3 and the Colab notebook remain future work until implemented and verified.
