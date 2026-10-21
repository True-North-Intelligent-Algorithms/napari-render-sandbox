# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scikit-image", "pooch", "PyQt6", "pygfx", "rendercanvas"]
# ///
"""Example 1b: the same volume MIP as example 1, with pygfx (WebGPU)

pygfx draws with WebGPU (through wgpu-py) instead of OpenGL. Here we use
its ready-made volume MIP, so there is no shader code to write: the WGSL
shader lives inside pygfx (pygfx/renderers/wgpu/wgsl/volume_ray.wgsl).

pygfx has mip, minip and iso volume modes, but no average or sum, so
this shows the MIP version of example 1.

Drag with the left mouse button to turn, right button or wheel to zoom.

Run:  uv run examples/01b_pygfx_mip.py
"""

import numpy as np
import pygfx as gfx
import PyQt6  # noqa: F401  (rendercanvas.qt uses whichever Qt is imported)
from rendercanvas.qt import RenderCanvas, loop
from skimage import data

# ---------------------------------------------------------------------------
# The data: the nuclei channel of cells3d, rescaled to 0..1 as in example 1
# ---------------------------------------------------------------------------

cells = data.cells3d()  # shape (z, channel, y, x) = (60, 2, 256, 256), uint16
nuclei = cells[:, 1, :, :]
low, high = np.percentile(nuclei, [1, 99.5])
nuclei = np.clip((nuclei - low) / (high - low), 0, 1).astype(np.float32)

# ---------------------------------------------------------------------------
# The scene
# ---------------------------------------------------------------------------

canvas = RenderCanvas(size=(600, 600), title="Example 1b: pygfx MIP (drag to turn)")
renderer = gfx.renderers.WgpuRenderer(canvas)
scene = gfx.Scene()
# pygfx's gray colormap also fades alpha from 0 to 1, so give it black behind
scene.add(gfx.Background.from_color("#000"))

# numpy's (z, y, x) order becomes the texture's (width=x, height=y, depth=z)
texture = gfx.Texture(nuclei, dim=3)
volume = gfx.Volume(
    gfx.Geometry(grid=texture),
    gfx.VolumeMipMaterial(clim=(0, 1), map=gfx.cm.gray),
)
volume.local.scale = (0.26, 0.26, 0.29)  # voxel size in µm, x y z order
scene.add(volume)

# Orthographic: rays go straight back, like example 1
camera = gfx.OrthographicCamera()
camera.show_object(volume, view_dir=(-1, -1, -1), up=(0, 1, 0))
controller = gfx.OrbitController(camera, register_events=renderer)

if __name__ == "__main__":
    canvas.request_draw(lambda: renderer.render(scene, camera))
    loop.run()
