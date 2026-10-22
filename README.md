# RecoveryPact

**Business-aware autonomous incident recovery** for PostgreSQL.

> Recovery isn't real until the business is back.

Open Agent Hackathon 2026 — Reasoning Architecture track.

## Status

Initial scaffold in progress: Recovery Contract schemas, authority gate, restricted executor, checkout service, incident injector, Docker Compose baseline, and NVIDIA Nemotron inference client (fixture + live modes).

See `docs/implementation-plan.md` for the build plan.

## Quick start (when vertical slice is complete)

```bash
cp .env.example .env
docker compose up --build -d
```

## License

MIT
