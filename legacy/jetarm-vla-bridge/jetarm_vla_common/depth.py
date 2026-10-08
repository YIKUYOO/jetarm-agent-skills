import numpy as np


def depth_to_vis(depth_raw_mm: np.ndarray, max_depth_mm: int = 4000) -> np.ndarray:
    """Convert a uint16 millimeter depth image into an RGB uint8 visualization."""

    if depth_raw_mm.ndim != 2:
        raise ValueError("depth_raw_mm must be a 2-D array")
    if max_depth_mm <= 0:
        raise ValueError("max_depth_mm must be positive")

    depth = depth_raw_mm.astype(np.float32, copy=False)
    valid = depth > 0
    scaled = np.zeros(depth.shape, dtype=np.uint8)
    scaled[valid] = np.clip(depth[valid], 0, max_depth_mm) / float(max_depth_mm) * 255.0
    return np.repeat(scaled[:, :, None], 3, axis=2)
