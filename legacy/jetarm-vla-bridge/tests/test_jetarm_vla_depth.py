import numpy as np

from jetarm_vla_common.depth import depth_to_vis


def test_depth_to_vis_returns_rgb_uint8_and_preserves_shape():
    depth = np.array([[0, 1000], [2000, 4000]], dtype=np.uint16)

    vis = depth_to_vis(depth, max_depth_mm=4000)

    assert vis.shape == (2, 2, 3)
    assert vis.dtype == np.uint8
    assert tuple(vis[0, 0]) == (0, 0, 0)
    assert vis[1, 1].max() > vis[0, 1].max()


def test_depth_to_vis_rejects_non_2d_depth():
    depth = np.zeros((2, 2, 1), dtype=np.uint16)

    try:
        depth_to_vis(depth)
    except ValueError as exc:
        assert "2-D" in str(exc)
    else:
        raise AssertionError("depth_to_vis should reject non-2D arrays")
