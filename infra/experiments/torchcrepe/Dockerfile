FROM vocal-score-studio-worker:latest

ARG TORCHCREPE_COMMIT=19e2ec3d494c0797a5ff2a11408ec5838fba6681
ENV CUDA_VISIBLE_DEVICES="" \
    TORCHCREPE_COMMIT=${TORCHCREPE_COMMIT}

COPY infra/experiments/sources/torchcrepe-19e2ec3d494c0797a5ff2a11408ec5838fba6681.tar.gz /tmp/torchcrepe.tar.gz
# The runner uses soundfile directly; remove torchcrepe's unused torchaudio import
# because the base image's CPU-only Torch version has no matching torchaudio wheel.
RUN mkdir -p /opt/torchcrepe \
    && tar -xzf /tmp/torchcrepe.tar.gz -C /opt/torchcrepe --strip-components=1 \
    && rm /tmp/torchcrepe.tar.gz \
    && sed -i '/^import torchaudio$/d' /opt/torchcrepe/torchcrepe/load.py \
    && pip install --no-cache-dir --no-deps /opt/torchcrepe

WORKDIR /opt/torchcrepe
ENTRYPOINT ["python", "/workspace/scripts/experiments/run-torchcrepe-benchmark.py"]
CMD []
