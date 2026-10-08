import numpy as np


def crop_rgb_depth_front(rgb, depth, crop_top=40, crop_bottom=440):
    """Crop RGB and depth with identical vertical bounds for RGB-D alignment."""

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be an HxWx3 image")
    if depth.ndim != 2:
        raise ValueError("depth must be a 2-D image")
    top = crop_top if rgb.shape[0] >= crop_bottom and depth.shape[0] >= crop_bottom else 0
    bottom = crop_bottom if top else min(rgb.shape[0], depth.shape[0])
    width = min(rgb.shape[1], depth.shape[1])
    rgb_cropped = rgb[top:bottom, :width]
    depth_cropped = depth[top:bottom, :width]
    return np.ascontiguousarray(rgb_cropped), np.ascontiguousarray(depth_cropped)
