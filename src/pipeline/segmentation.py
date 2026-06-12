from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from src.domain.config import SegmentationConfig
try:
    import mediapipe as mp
except ImportError:  # pragma: no cover
    mp = None


class Segmenter:
    def segment(self, frame: np.ndarray) -> np.ndarray:
        raise NotImplementedError


@dataclass
class MockSegmenter(Segmenter):
    def segment(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.float32)
        center = (width // 2, height // 2)
        axes = (max(1, width // 4), max(1, height // 3))
        cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)
        return mask


@dataclass
class UnsupportedSegmenter(Segmenter):
    backend: str

    def segment(self, frame: np.ndarray) -> np.ndarray:
        raise NotImplementedError(
            f"Segmentation backend '{self.backend}' is not implemented yet. "
            "Use 'mock' for pipeline smoke tests."
        )


class MediaPipeSelfieSegmenter(Segmenter):
    def __init__(self, config: SegmentationConfig) -> None:
        print("[seg] selfie backend: checking mediapipe dependency...")
        if mp is None:
            raise RuntimeError(
                "mediapipe is not installed. Install dependencies to use segmentation.backend=selfie."
            )
        if not hasattr(mp, "solutions"):
            version = getattr(mp, "__version__", "unknown")
            raise RuntimeError(
                "Installed mediapipe package is incompatible (missing mediapipe.solutions). "
                f"Detected version: {version}. "
                "Run './bin/avc setup' to install the pinned compatible version."
            )
        print("[seg] selfie backend: initializing MediaPipe SelfieSegmentation model...")
        self._segmenter = mp.solutions.selfie_segmentation.SelfieSegmentation(
            model_selection=int(config.selfieModelSelection)
        )
        self._warmup_done = False
        self._smoothing = float(config.selfieTemporalSmoothing)
        if "temporalAlpha" in config.engineOptions:
            try:
                self._smoothing = float(config.engineOptions["temporalAlpha"])
            except (TypeError, ValueError):
                pass
        self._opts = dict(config.engineOptions)
        self._prev_mask: np.ndarray | None = None
        print("[seg] selfie backend: model initialized")

    def segment(self, frame: np.ndarray) -> np.ndarray:
        if not self._warmup_done:
            print("[seg] selfie backend: running first inference (warm-up)...")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._segmenter.process(rgb)
        if not self._warmup_done:
            self._warmup_done = True
            print("[seg] selfie backend: warm-up complete")
        if result.segmentation_mask is None:
            return np.zeros(frame.shape[:2], dtype=np.float32)
        mask = result.segmentation_mask.astype(np.float32)
        if self._prev_mask is not None and self._smoothing > 0.0:
            mask = cv2.addWeighted(mask, 1.0 - self._smoothing, self._prev_mask, self._smoothing, 0.0)
        mask = _apply_engine_options(mask, self._opts)
        self._prev_mask = mask
        return mask


class OnnxRuntimeCompatSegmenter(Segmenter):
    def __init__(self, config: SegmentationConfig) -> None:
        print(
            "[seg] onnxruntime backend: ONNX model runtime is not wired yet. "
            "Using selfie-compatible segmentation path as fallback."
        )
        self._delegate = MediaPipeSelfieSegmenter(config)

    def segment(self, frame: np.ndarray) -> np.ndarray:
        return self._delegate.segment(frame)


class TensorRtSegmenter(Segmenter):
    def __init__(self, config: SegmentationConfig) -> None:
        engine_path = str(config.engineOptions.get("enginePath") or "").strip()
        if not engine_path:
            raise RuntimeError(
                "segmentation.backend=tensorrt requires segmentation.engineOptions.tensorrt.enginePath. "
                "Select a serialized TensorRT engine file in config."
            )
        from pathlib import Path

        self._engine_path = Path(engine_path).expanduser()
        if not self._engine_path.exists():
            raise RuntimeError(f"TensorRT engine file not found: {self._engine_path}")

        try:
            import tensorrt as trt
            from cuda import cudart
        except Exception as exc:
            raise RuntimeError(
                "TensorRT Python runtime is required for segmentation.backend=tensorrt. "
                "Install NVIDIA TensorRT and cuda-python bindings, then rerun ./bin/avc setup if needed."
            ) from exc

        self._trt = trt
        self._cudart = cudart
        self._opts = dict(config.engineOptions)
        self._prev_mask: np.ndarray | None = None
        self._logger = trt.Logger(trt.Logger.WARNING)
        self._runtime = trt.Runtime(self._logger)
        engine_bytes = self._engine_path.read_bytes()
        self._engine = self._runtime.deserialize_cuda_engine(engine_bytes)
        if self._engine is None:
            raise RuntimeError(f"Failed to deserialize TensorRT engine: {self._engine_path}")
        self._context = self._engine.create_execution_context()
        if self._context is None:
            raise RuntimeError("Failed to create TensorRT execution context")
        self._stream = self._cuda_check(cudart.cudaStreamCreate())[1]
        self._bindings: dict[str, int] = {}
        self._buffer_sizes: dict[str, int] = {}
        self._input_name, self._output_name = self._select_io_names()
        print(f"[seg] tensorrt backend: loaded engine {self._engine_path}")

    def __del__(self) -> None:  # pragma: no cover - best-effort CUDA cleanup
        try:
            for ptr in self._bindings.values():
                self._cudart.cudaFree(ptr)
            if getattr(self, "_stream", None) is not None:
                self._cudart.cudaStreamDestroy(self._stream)
        except Exception:
            pass

    def _cuda_check(self, result):
        err = result[0]
        if err != self._cudart.cudaError_t.cudaSuccess:
            raise RuntimeError(f"CUDA call failed: {err}")
        return result

    def _select_io_names(self) -> tuple[str, str]:
        input_name = str(self._opts.get("inputName") or "").strip()
        output_name = str(self._opts.get("outputName") or "").strip()
        inputs: list[str] = []
        outputs: list[str] = []
        trt = self._trt
        if hasattr(self._engine, "num_io_tensors"):
            for index in range(int(self._engine.num_io_tensors)):
                name = self._engine.get_tensor_name(index)
                mode = self._engine.get_tensor_mode(name)
                if mode == trt.TensorIOMode.INPUT:
                    inputs.append(name)
                else:
                    outputs.append(name)
        else:
            for index in range(int(self._engine.num_bindings)):
                name = self._engine.get_binding_name(index)
                if self._engine.binding_is_input(index):
                    inputs.append(name)
                else:
                    outputs.append(name)
        if not input_name:
            if len(inputs) != 1:
                raise RuntimeError(f"TensorRT engine must have exactly one input or set inputName: {inputs}")
            input_name = inputs[0]
        if not output_name:
            if len(outputs) != 1:
                raise RuntimeError(f"TensorRT engine must have exactly one output or set outputName: {outputs}")
            output_name = outputs[0]
        return input_name, output_name

    def _tensor_shape(self, name: str) -> tuple[int, ...]:
        if hasattr(self._engine, "get_tensor_shape"):
            shape = tuple(int(dim) for dim in self._engine.get_tensor_shape(name))
        else:
            index = self._engine.get_binding_index(name)
            shape = tuple(int(dim) for dim in self._engine.get_binding_shape(index))
        return shape

    def _tensor_np_dtype(self, name: str) -> np.dtype:
        if hasattr(self._engine, "get_tensor_dtype"):
            trt_dtype = self._engine.get_tensor_dtype(name)
        else:
            index = self._engine.get_binding_index(name)
            trt_dtype = self._engine.get_binding_dtype(index)
        try:
            return np.dtype(self._trt.nptype(trt_dtype))
        except Exception:
            dtype_name = str(trt_dtype).lower()
            if "float16" in dtype_name or "half" in dtype_name:
                return np.dtype(np.float16)
            if "float32" in dtype_name or "float" in dtype_name:
                return np.dtype(np.float32)
            raise RuntimeError(f"Unsupported TensorRT tensor dtype for {name}: {trt_dtype}")

    def _set_input_shape(self, name: str, shape: tuple[int, ...]) -> None:
        if hasattr(self._context, "set_input_shape"):
            self._context.set_input_shape(name, shape)
        else:
            index = self._engine.get_binding_index(name)
            self._context.set_binding_shape(index, shape)

    def _context_tensor_shape(self, name: str) -> tuple[int, ...]:
        if hasattr(self._context, "get_tensor_shape"):
            return tuple(int(dim) for dim in self._context.get_tensor_shape(name))
        index = self._engine.get_binding_index(name)
        return tuple(int(dim) for dim in self._context.get_binding_shape(index))

    def _ensure_device_buffer(self, name: str, nbytes: int) -> int:
        current_size = self._buffer_sizes.get(name, 0)
        if name in self._bindings and current_size >= nbytes:
            return self._bindings[name]
        if name in self._bindings:
            self._cudart.cudaFree(self._bindings[name])
        ptr = self._cuda_check(self._cudart.cudaMalloc(nbytes))[1]
        self._bindings[name] = ptr
        self._buffer_sizes[name] = nbytes
        return ptr

    def _prepare_input(self, frame: np.ndarray) -> np.ndarray:
        shape = self._tensor_shape(self._input_name)
        if len(shape) != 4:
            raise RuntimeError(f"TensorRT input must be 4D NCHW/NHWC, got {shape}")
        n, a, b, c = shape
        if n < 0:
            n = 1
        if c in {1, 3}:
            height = frame.shape[0] if a < 0 else a
            width = frame.shape[1] if b < 0 else b
            layout = "NHWC"
        else:
            channels = 3 if a < 0 else a
            height = frame.shape[0] if b < 0 else b
            width = frame.shape[1] if c < 0 else c
            layout = "NCHW"
            if channels not in {1, 3}:
                raise RuntimeError(f"TensorRT input channel count must be 1 or 3, got {channels}")
        resized = cv2.resize(frame, (int(width), int(height)), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        if layout == "NCHW":
            data = np.transpose(rgb, (2, 0, 1))[None, ...]
        else:
            data = rgb[None, ...]
        return np.ascontiguousarray(data.astype(self._tensor_np_dtype(self._input_name)))

    def _execute(self, input_data: np.ndarray) -> np.ndarray:
        self._set_input_shape(self._input_name, tuple(input_data.shape))
        input_ptr = self._ensure_device_buffer(self._input_name, int(input_data.nbytes))
        self._cuda_check(
            self._cudart.cudaMemcpyAsync(
                input_ptr,
                input_data.ctypes.data,
                int(input_data.nbytes),
                self._cudart.cudaMemcpyKind.cudaMemcpyHostToDevice,
                self._stream,
            )
        )
        output_shape = self._context_tensor_shape(self._output_name)
        if any(dim < 0 for dim in output_shape):
            raise RuntimeError(f"TensorRT output shape is not fully resolved: {output_shape}")
        output = np.empty(output_shape, dtype=self._tensor_np_dtype(self._output_name))
        output_ptr = self._ensure_device_buffer(self._output_name, int(output.nbytes))
        if hasattr(self._context, "set_tensor_address"):
            self._context.set_tensor_address(self._input_name, int(input_ptr))
            self._context.set_tensor_address(self._output_name, int(output_ptr))
            ok = self._context.execute_async_v3(self._stream)
        else:
            bindings = [0] * int(self._engine.num_bindings)
            bindings[self._engine.get_binding_index(self._input_name)] = int(input_ptr)
            bindings[self._engine.get_binding_index(self._output_name)] = int(output_ptr)
            ok = self._context.execute_async_v2(bindings, self._stream)
        if not ok:
            raise RuntimeError("TensorRT execution failed")
        self._cuda_check(
            self._cudart.cudaMemcpyAsync(
                output.ctypes.data,
                output_ptr,
                int(output.nbytes),
                self._cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,
                self._stream,
            )
        )
        self._cuda_check(self._cudart.cudaStreamSynchronize(self._stream))
        return output

    def segment(self, frame: np.ndarray) -> np.ndarray:
        output = self._execute(self._prepare_input(frame))
        mask = np.squeeze(output).astype(np.float32)
        if mask.ndim == 3:
            mask = mask[0] if mask.shape[0] == 1 else mask[..., 0]
        if mask.shape[:2] != frame.shape[:2]:
            mask = cv2.resize(mask, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_LINEAR)
        mask = _apply_engine_options(mask, self._opts)
        if "temporalAlpha" in self._opts and self._prev_mask is not None:
            alpha = max(0.0, min(0.95, _to_float_option(self._opts, "temporalAlpha", 0.0)))
            if alpha > 0.0:
                mask = cv2.addWeighted(mask, 1.0 - alpha, self._prev_mask, alpha, 0.0)
        self._prev_mask = mask
        return np.clip(mask, 0.0, 1.0).astype(np.float32)


class MediaPipeSelfieEnsembleSegmenter(Segmenter):
    def __init__(self, config: SegmentationConfig) -> None:
        print("[seg] selfie_ensemble backend: checking mediapipe dependency...")
        if mp is None:
            raise RuntimeError(
                "mediapipe is not installed. Install dependencies to use segmentation.backend=selfie_ensemble."
            )
        if not hasattr(mp, "solutions"):
            version = getattr(mp, "__version__", "unknown")
            raise RuntimeError(
                "Installed mediapipe package is incompatible (missing mediapipe.solutions). "
                f"Detected version: {version}. "
                "Run './bin/avc setup' to install the pinned compatible version."
            )
        print("[seg] selfie_ensemble backend: initializing model_selection=0/1 pair...")
        self._segmenter0 = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=0)
        self._segmenter1 = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
        self._warmup_done = False
        self._smoothing = float(config.selfieTemporalSmoothing)
        if "temporalAlpha" in config.engineOptions:
            try:
                self._smoothing = float(config.engineOptions["temporalAlpha"])
            except (TypeError, ValueError):
                pass
        self._blend = 0.5
        if "modelBlend" in config.engineOptions:
            try:
                self._blend = float(config.engineOptions["modelBlend"])
            except (TypeError, ValueError):
                self._blend = 0.5
        self._blend = max(0.0, min(1.0, self._blend))
        self._opts = dict(config.engineOptions)
        self._prev_mask: np.ndarray | None = None
        print(f"[seg] selfie_ensemble backend: model initialized (blend={self._blend:.2f})")

    def segment(self, frame: np.ndarray) -> np.ndarray:
        if not self._warmup_done:
            print("[seg] selfie_ensemble backend: running first inference (warm-up)...")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res0 = self._segmenter0.process(rgb)
        res1 = self._segmenter1.process(rgb)
        if not self._warmup_done:
            self._warmup_done = True
            print("[seg] selfie_ensemble backend: warm-up complete")
        if res0.segmentation_mask is None or res1.segmentation_mask is None:
            return np.zeros(frame.shape[:2], dtype=np.float32)
        mask0 = res0.segmentation_mask.astype(np.float32)
        mask1 = res1.segmentation_mask.astype(np.float32)
        mask = cv2.addWeighted(mask0, 1.0 - self._blend, mask1, self._blend, 0.0)
        if self._prev_mask is not None and self._smoothing > 0.0:
            mask = cv2.addWeighted(mask, 1.0 - self._smoothing, self._prev_mask, self._smoothing, 0.0)
        mask = _apply_engine_options(mask, self._opts)
        self._prev_mask = mask
        return mask


def _to_int_option(options: dict[str, object], key: str, default: int = 0) -> int:
    raw = options.get(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _to_float_option(options: dict[str, object], key: str, default: float = 0.0) -> float:
    raw = options.get(key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _apply_engine_options(mask: np.ndarray, options: dict[str, object]) -> np.ndarray:
    out = np.clip(mask, 0.0, 1.0).astype(np.float32)
    blur_kernel = _to_int_option(options, "maskBlur", 0)
    if blur_kernel > 0:
        if blur_kernel % 2 == 0:
            blur_kernel += 1
        out = cv2.GaussianBlur(out, (blur_kernel, blur_kernel), 0)
    morph_open = max(0, _to_int_option(options, "morphOpen", 0))
    morph_close = max(0, _to_int_option(options, "morphClose", 0))
    if morph_open > 0:
        k = np.ones((morph_open, morph_open), np.uint8)
        out = cv2.morphologyEx(out, cv2.MORPH_OPEN, k)
    if morph_close > 0:
        k = np.ones((morph_close, morph_close), np.uint8)
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, k)
    gamma = _to_float_option(options, "maskGamma", 1.0)
    if gamma > 0.01 and abs(gamma - 1.0) > 1e-3:
        out = np.power(np.clip(out, 0.0, 1.0), gamma).astype(np.float32)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def build_segmenter(config: SegmentationConfig) -> Segmenter:
    if config.backend == "selfie":
        return MediaPipeSelfieSegmenter(config)
    if config.backend == "selfie_ensemble":
        return MediaPipeSelfieEnsembleSegmenter(config)
    if config.backend == "onnxruntime":
        return OnnxRuntimeCompatSegmenter(config)
    if config.backend == "mock":
        return MockSegmenter()
    if config.backend == "tensorrt":
        return TensorRtSegmenter(config)
    raise ValueError(f"Unsupported segmentation backend: {config.backend}")
