# Architecture

Vocal Score Studio is a monorepo with independently deployable boundaries:

- `apps/web`: browser UI, score editing, notation rendering, and playback.
- `apps/api`: FastAPI validation, persistence, uploads, job coordination, and contracts.
- `workers/transcription`: CPU/GPU audio and model computation.
- `packages/contracts`: generated client types and canonical schemas.

The API process never performs heavy model inference. A job is durable before it
is dispatched, and model outputs are recorded with versions and parameters.
