import numpy as np

from jetarm_vla_common.images import crop_rgb_depth_front


def test_crop_rgb_depth_front_uses_same_vertical_bounds_for_rgb_and_depth():
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    depth = np.arange(480 * 640, dtype=np.uint16).reshape(480, 640)

    cropped_rgb, cropped_depth = crop_rgb_depth_front(rgb, depth)

    assert cropped_rgb.shape == (400, 640, 3)
    assert cropped_depth.shape == (400, 640)
    assert cropped_depth[0, 0] == depth[40, 0]
    assert cropped_depth[-1, -1] == depth[439, 639]


def test_crop_rgb_depth_front_falls_back_when_images_are_short():
    rgb = np.zeros((10, 8, 3), dtype=np.uint8)
    depth = np.zeros((9, 7), dtype=np.uint16)

    cropped_rgb, cropped_depth = crop_rgb_depth_front(rgb, depth)

    assert cropped_rgb.shape == (9, 7, 3)
    assert cropped_depth.shape == (9, 7)
