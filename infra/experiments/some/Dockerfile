FROM vocal-score-studio-worker:latest

ARG SOME_COMMIT=dcfd40f9bfaa7c9649aae01a2795af73946ec5e7
ENV PIP_DEFAULT_TIMEOUT=180 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PIP_TRUSTED_HOST="download.pytorch.org pypi.org files.pythonhosted.org" \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    CUDA_VISIBLE_DEVICES="" \
    SOME_COMMIT=${SOME_COMMIT}

COPY infra/experiments/sources/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY infra/experiments/sources/some-dcfd40f9bfaa7c9649aae01a2795af73946ec5e7.tar.gz /tmp/some.tar.gz
RUN mkdir -p /opt/some \
    && tar -xzf /tmp/some.tar.gz -C /opt/some --strip-components=1 \
    && rm /tmp/some.tar.gz
RUN pip install --no-cache-dir --force-reinstall \
      --index-url https://download.pytorch.org/whl/cpu \
      torch==2.1.2 torchaudio==2.1.2
RUN sed -i '/from utils.training_utils import get_latest_checkpoint_path/d' \
      /opt/some/utils/__init__.py \
    && pip install --no-cache-dir librosa==0.9.2 praat-parselmouth==0.4.3

WORKDIR /opt/some
ENTRYPOINT ["python", "/workspace/scripts/experiments/run-some-benchmark.py"]
CMD []
