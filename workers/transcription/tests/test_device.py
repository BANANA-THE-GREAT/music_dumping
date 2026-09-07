import pytest
from vss_worker.device import InferenceDeviceError, resolve_inference_device


def test_device_selection_supports_cpu_cuda_and_auto() -> None:
    assert resolve_inference_device("cpu", cuda_available=lambda: True) == "cpu"
    assert resolve_inference_device("auto", cuda_available=lambda: False) == "cpu"
    assert resolve_inference_device("auto", cuda_available=lambda: True) == "cuda"
    assert resolve_inference_device("cuda", cuda_available=lambda: True) == "cuda"


def test_explicit_cuda_requires_available_runtime() -> None:
    with pytest.raises(InferenceDeviceError, match="torch.cuda.is_available"):
        resolve_inference_device("cuda", cuda_available=lambda: False)


def test_device_selection_rejects_unknown_value() -> None:
    with pytest.raises(InferenceDeviceError, match="VSS_INFERENCE_DEVICE"):
        resolve_inference_device("metal", cuda_available=lambda: False)
