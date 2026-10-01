# Python dependency locks

The Docker runtime separates stable third-party dependencies from frequently changing
application code:

- `api.lock` records the complete validated API environment.
- `worker.lock` records the complete validated CPU Worker environment except PyTorch,
  whose exact CPU or CUDA wheel is selected by the Worker build arguments.

The build scripts hash these files together with their dependency Dockerfiles. An existing
hash-tagged dependency image is reused without contacting Docker Hub, PyPI, APT, or the
PyTorch wheel index. Changing a lock file, dependency Dockerfile, Python base, or PyTorch
selection deliberately creates a new dependency image and may require network access once.

When dependencies change:

1. Update `pyproject.toml`.
2. Resolve and test the candidate environment in Docker.
3. Regenerate the relevant lock from that validated image with `pip freeze --all`, excluding
   `pip`, `torch`, and the local `vocal-score-studio @ file:///app` entry as appropriate.
4. Run the API and Worker tests before replacing the previous dependency image.

Do not delete `vocal-score-studio-api-deps:*` or `vocal-score-studio-worker-deps:*` during a
normal source-code rebuild. These images are the reusable Python environments.
