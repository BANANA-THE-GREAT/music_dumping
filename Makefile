SHELL := /bin/bash

COMPOSE := docker compose -f infra/compose.yaml
GPU_COMPOSE := $(COMPOSE) -f infra/compose.gpu.yaml
QUALITY_DOCKERFILE := infra/docker/Dockerfile.worker-quality

.PHONY: help config status images up restart down logs \
	build-web build-api build-renderer build-worker build-worker-gpu rebuild \
	quality-build quality-up quality-smoke \
	quality-build-gpu quality-up-gpu gpu-check \
	check-web check-api

help: ## Show common Docker commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "%-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

config: ## Validate the Docker Compose configuration
	$(COMPOSE) config

status: ## Show all project containers
	$(COMPOSE) ps -a

images: ## Show images used by the project
	$(COMPOSE) images

up: ## Start the standard Web and CPU Worker stack without rebuilding
	$(COMPOSE) up -d --wait web worker

restart: ## Recreate Web and Worker containers without rebuilding or deleting volumes
	$(COMPOSE) up -d --force-recreate --wait web worker

down: ## Stop project containers without deleting persistent volumes
	$(COMPOSE) down

logs: ## Follow logs; optionally use SERVICE=api|worker|web
	$(COMPOSE) logs -f $(SERVICE)

build-web: ## Rebuild Web after frontend, contract, or Nginx changes
	$(COMPOSE) build web

build-api: ## Rebuild API after backend or migration changes
	scripts/build-api-image.sh

build-renderer: ## Build renderer; set VSS_RENDERER_BASE_IMAGE to reuse a local Python image
	$(COMPOSE) build renderer

build-worker: ## Rebuild the standard CPU Worker
	scripts/build-worker-image.sh

build-worker-gpu: ## Rebuild the standard CUDA Worker dependency and app layers
	VSS_PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu128 \
	VSS_PYTORCH_PACKAGE=torch==2.8.0+cu128 \
	VSS_PYTORCH_EXPECT_CUDA=1 \
	scripts/build-worker-image.sh

rebuild: ## Rebuild API, CPU Worker, and Web, then start Web and Worker
	$(MAKE) build-api
	$(MAKE) build-renderer
	$(MAKE) build-worker
	$(MAKE) build-web
	$(COMPOSE) up -d --wait web worker

quality-build: ## Build the experimental GAME + F0 quality Worker
	scripts/build-quality-worker.sh

quality-up: ## Start the CPU quality Worker using the quality Dockerfile
	VSS_WORKER_DOCKERFILE=$(QUALITY_DOCKERFILE) $(COMPOSE) up -d --no-build --wait worker

quality-smoke: ## Run the GAME segmentation smoke test
	scripts/run-quality-segmentation-smoke.sh

quality-build-gpu: ## Build the CUDA quality Worker
	scripts/build-quality-worker-gpu.sh

quality-up-gpu: ## Start the GPU quality Worker; requires NVIDIA Container Toolkit
	VSS_WORKER_DOCKERFILE=$(QUALITY_DOCKERFILE) $(GPU_COMPOSE) up -d --no-build --wait worker

gpu-check: ## Check CUDA visibility inside the standard Worker image
	docker run --rm --gpus all vocal-score-studio-worker:latest \
		python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no CUDA')"

check-web: ## Check the Web endpoint on port 8888
	curl --fail --silent --show-error -I http://127.0.0.1:8888/

check-api: ## Check API readiness and project catalog
	curl --fail --silent --show-error http://127.0.0.1:8000/health/ready
	@printf '\n'
	curl --fail --silent --show-error http://127.0.0.1:8000/v1/project-catalog
	@printf '\n'
