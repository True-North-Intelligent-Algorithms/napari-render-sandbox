# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "vispy", "PyQt6", "PyOpenGL", "plyfile", "scipy"]
# ///
"""Example 2c: the GaussianSplat visual from vispy PR #2761

Runs the visual unchanged (copied into splat_visual.py next to this file),
on one of two datasets:

    fly    the PR's sample: a 3D Gaussian Splatting scene of a cluster fly
           (from the vispy demo-data repository, downloaded once)
    smlm   the nuclear pore localizations from examples 2 and 2b, as
           axis-aligned Gaussians (sigma x, y, z from the precision)

No SMLM-specific changes yet: the SMLM data goes through the visual as it
is ("over" blending with depth sorting, one color, one opacity), so we can
see what it does with density data before changing anything.

    drag          turn
    wheel         zoom
    a             toggle the anti-aliasing compensation
    sliders       how many splats to show (0 to all), and an opacity scale

Run:  uv run examples/02c_gaussian_splats.py fly
      uv run examples/02c_gaussian_splats.py smlm
      uv run examples/02c_gaussian_splats.py fly --opacity-scale 0.2
      uv run examples/02c_gaussian_splats.py fly --fraction 0.05
"""

import argparse
import json
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget
from vispy import scene, use
from vispy.io import load_data_file
from vispy.scene.visuals import create_visual_node

from splat_visual import GaussianSplatVisual

# The visual needs a full gl+ context for instanced rendering; the canvas is
# embedded in a Qt window with sliders.
use(app="pyqt6", gl="gl+")

GaussianSplat = create_visual_node(GaussianSplatVisual)

# ---------------------------------------------------------------------------
# Data a: the cluster fly, loaded the way the PR's example loads it
# ---------------------------------------------------------------------------

FLY_PLY = "gaussian_splatting/cluster/cluster_fly_S.ply"


def load_fly():
    """load_splats() from the PR's examples/scene/gaussian_splatting.py."""
    from plyfile import PlyData
    from scipy.spatial.transform import Rotation

    ply = PlyData.read(load_data_file(FLY_PLY))
    v = ply.elements[0].data
    comments = ply.comments + [c for el in ply.elements for c in el.comments]
    antialias = "postshot.anti_aliasing=1" in comments

    xyz = np.stack([v["x"], v["y"], v["z"]], axis=-1).astype(np.float64)

    # scale_* are log-space standard deviations
    scales = np.exp(np.stack([v[f"scale_{i}"] for i in range(3)], axis=-1))

    # rot_* is a (w, x, y, z) quaternion; scipy wants (x, y, z, w)
    quats = np.stack([v[f"rot_{i}"] for i in range(4)], axis=-1)
    R = Rotation.from_quat(quats[:, [1, 2, 3, 0]]).as_matrix()

    # Sigma = R S S^T R^T, built as M @ M^T with M = R @ diag(scales)
    M = R * scales[:, None, :]
    sigma = M @ M.swapaxes(-1, -2)

    # only the base color (f_dc_*) of the spherical harmonics
    SH_C0 = 1 / (2 * np.sqrt(np.pi))
    rgb = 0.5 + SH_C0 * np.stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]], axis=-1)
    rgb = np.clip(rgb, 0.0, 1.0)
    alpha = 1.0 / (1.0 + np.exp(-v["opacity"].astype(np.float64)))
    rgba = np.concatenate([rgb, alpha[:, None]], axis=-1)

    return xyz, sigma, rgba, antialias, "-y"


# ---------------------------------------------------------------------------
# Data b: the SMLM nuclear pores, as axis-aligned Gaussians
# ---------------------------------------------------------------------------

SMLM_FILE = (
    Path(__file__).parent.parent
    / "data"
    / "shareloc_zola3d_nup"
    / "sample-1"
    / "data.smlm"
)
SMLM_URL = "https://zenodo.org/api/records/7233696/files/sample-1/data.smlm/content"


def load_smlm(opacity):
    """Positions and precisions in nm, from the ShareLoc .smlm file."""
    if not SMLM_FILE.exists():
        print(f"Downloading the dataset (12 MB) to {SMLM_FILE}")
        SMLM_FILE.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(SMLM_URL, SMLM_FILE)

    with zipfile.ZipFile(SMLM_FILE) as smlm:
        manifest = json.loads(smlm.read("manifest.json"))
        raw = np.frombuffer(smlm.read("default.bin"), dtype="<f4")
    headers = manifest["formats"]["smlm-table(binary)-0"]["headers"]
    table = raw.reshape(-1, len(headers))
    column = {name: table[:, i] for i, name in enumerate(headers)}

    xyz = np.stack([column["x"], column["y"], column["z"]], axis=-1)
    xyz = xyz - xyz.mean(axis=0)

    # Axis-aligned covariance: sigma squared on the diagonal, zeros elsewhere.
    sigma_xyz = np.stack([column["crlbX"], column["crlbY"], column["crlbZ"]], axis=-1)
    sigma = np.zeros((len(xyz), 3, 3))
    for i in range(3):
        sigma[:, i, i] = sigma_xyz[:, i] ** 2

    # One color and one opacity for every localization.
    rgba = np.tile([1.0, 0.45, 0.15, opacity], (len(xyz), 1))

    return xyz, sigma, rgba, False, "+z"


# ---------------------------------------------------------------------------
# Show it
# ---------------------------------------------------------------------------


class Window(QWidget):
    """The splat view, with sliders for the fraction shown and the opacity."""

    def __init__(self, positions, covariances, colors, antialias, up, title,
                 fraction, opacity_scale):
        super().__init__()
        self.setWindowTitle(title)

        # Shuffle once (fixed seed), so "the first k splats" is a random
        # subset that only grows or shrinks as the fraction slider moves.
        order = np.random.default_rng(0).permutation(len(positions))
        self.positions = np.ascontiguousarray(positions[order], np.float32)
        self.covariances = np.ascontiguousarray(covariances[order], np.float32)
        self.colors = np.ascontiguousarray(colors[order], np.float32)
        self.opacities = self.colors[:, 3].copy()

        self.canvas = scene.SceneCanvas(keys="interactive", size=(800, 600), bgcolor="black")
        view = self.canvas.central_widget.add_view()
        view.camera = scene.cameras.TurntableCamera(fov=45.0, up=up)
        self.splats = GaussianSplat(
            self.positions, self.covariances, self.colors,
            antialias=antialias, parent=view.scene,
        )
        view.camera.set_range()
        self.canvas.events.key_press.connect(self.on_key_press)

        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas.native)
        self.fraction_slider, self.fraction_label = self.add_slider_row(
            layout, "splats shown:", round(fraction * 1000)
        )
        self.opacity_slider, self.opacity_label = self.add_slider_row(
            layout, "opacity scale:", round(opacity_scale * 1000)
        )
        self.update_splats()

    def add_slider_row(self, layout, name, value):
        """A row: name, slider (0 to 1000, read as 0 to 1), current value."""
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 1000)
        slider.setValue(value)
        slider.valueChanged.connect(self.update_splats)
        value_label = QLabel()
        value_label.setMinimumWidth(170)
        row = QHBoxLayout()
        row.addWidget(QLabel(name))
        row.addWidget(slider)
        row.addWidget(value_label)
        layout.addLayout(row)
        return slider, value_label

    def update_splats(self):
        fraction = self.fraction_slider.value() / 1000
        scale = self.opacity_slider.value() / 1000
        n = round(fraction * len(self.positions))
        self.fraction_label.setText(f"{fraction:.1%} ({n:,} splats)")
        self.opacity_label.setText(f"x {scale:.3f}")

        if n == 0:
            self.splats.visible = False
            return
        colors = self.colors[:n].copy()
        colors[:, 3] = self.opacities[:n] * scale
        self.splats.set_data(self.positions[:n], self.covariances[:n], colors)
        self.splats.visible = True

    def on_key_press(self, event):
        if event.text == "a":
            self.splats.antialias = not self.splats.antialias
            print(f'anti-aliasing {"on" if self.splats.antialias else "off"}')


def main():
    parser = argparse.ArgumentParser(description="GaussianSplat visual")
    parser.add_argument("data", choices=["fly", "smlm"], nargs="?", default="fly")
    parser.add_argument(
        "--opacity", type=float, default=0.5, help="SMLM splat opacity (default 0.5)"
    )
    parser.add_argument(
        "--opacity-scale", type=float, default=1.0,
        help="starting opacity scale, 0 to 1 (default 1)",
    )
    parser.add_argument(
        "--fraction", type=float, default=1.0,
        help="starting fraction of splats shown, 0 to 1 (default 1)",
    )
    args = parser.parse_args()

    if args.data == "fly":
        positions, covariances, colors, antialias, up = load_fly()
    else:
        positions, covariances, colors, antialias, up = load_smlm(args.opacity)
    print(f"loaded {len(positions):,} gaussians ({args.data})")

    qt_app = QApplication.instance() or QApplication([])
    window = Window(
        positions, covariances, colors, antialias, up,
        title=f"Example 2c: GaussianSplat ({args.data})",
        fraction=args.fraction, opacity_scale=args.opacity_scale,
    )
    window.show()
    qt_app.exec()


if __name__ == "__main__":
    main()
