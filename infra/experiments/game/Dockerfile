FROM vocal-score-studio-worker:latest

ARG GAME_COMMIT=e66c31251605e334b1bf0f565252d4987a9065c0
ENV PIP_DEFAULT_TIMEOUT=180 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PIP_TRUSTED_HOST="download.pytorch.org pypi.org files.pythonhosted.org" \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    CUDA_VISIBLE_DEVICES="" \
    GAME_COMMIT=${GAME_COMMIT}

COPY infra/experiments/sources/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY infra/experiments/sources/game-e66c31251605e334b1bf0f565252d4987a9065c0.tar.gz /tmp/game.tar.gz
RUN mkdir -p /opt/game \
    && tar -xzf /tmp/game.tar.gz -C /opt/game --strip-components=1 \
    && rm /tmp/game.tar.gz
RUN pip install --no-cache-dir --force-reinstall \
      --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 \
    && pip install --no-cache-dir \
      lightning==2.6.1 loguru==0.7.3 omegaconf==2.3.0 torchmetrics==1.8.2
RUN pip install --no-cache-dir colorednoise==2.2.0

WORKDIR /opt/game
ENTRYPOINT ["python", "/workspace/scripts/experiments/run-game-benchmark.py"]
CMD []
