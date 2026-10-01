import os
from collections.abc import Callable

INFERENCE_DEVICE_ENV = "VSS_INFERENCE_DEVICE"
SUPPORTED_DEVICES = {"auto", "cpu", "cuda"}


class InferenceDeviceError(RuntimeError):
    pass


def resolve_inference_device(
    requested: str | None = None,
    *,
    cuda_available: Callable[[], bool] | None = None,
) -> str:
    configured = requested if requested is not None else os.getenv(INFERENCE_DEVICE_ENV)
    value = (configured or "auto").strip().lower()
    if value not in SUPPORTED_DEVICES:
        choices = ", ".join(sorted(SUPPORTED_DEVICES))
        raise InferenceDeviceError(
            f"{INFERENCE_DEVICE_ENV} must be one of {choices}; got {value!r}"
        )
    if value == "cpu":
        return "cpu"

    if cuda_available is None:
        try:
            import torch  # type: ignore[import-not-found]
        except ImportError as error:
            if value == "cuda":
                raise InferenceDeviceError(
                    "CUDA was requested but PyTorch is not installed"
                ) from error
            return "cpu"
        cuda_available = torch.cuda.is_available

    available = cuda_available()
    if value == "cuda" and not available:
        raise InferenceDeviceError(
            "CUDA was requested but torch.cuda.is_available() is false; "
            "check the CUDA PyTorch build and Docker GPU runtime"
        )
    return "cuda" if available else "cpu"
