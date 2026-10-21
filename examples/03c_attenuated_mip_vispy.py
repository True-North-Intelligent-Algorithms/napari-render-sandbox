# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "tifffile", "vispy", "PyQt6", "PyOpenGL"]
#
# [tool.uv.sources]
# vispy = { path = "../../vispy", editable = true }   # your local clone
# ///
"""Example 3c: the same image as example 3, rendered by vispy itself

Uses vispy's real Volume visual (method = attenuated_mip), set up the way
napari sets it up. It renders with whichever vispy is installed, so it is a
quick way to SEE a change to vispy's shader: edit vispy/visuals/volume.py in
your vispy checkout, then run this again. The first line printed says which
vispy is in use.

Three-way comparison:
    03   our GLSL copy of the shader (plain OpenGL)
    03b  napari (napari -> vispy -> OpenGL)
    03c  vispy alone (vispy -> OpenGL)       <- this file

Same controls as example 3 and napari: attenuation, contrast limits, gamma.
Plus "base attenuation", vispy's new base_attenuation (napari#8241),
0 to 0.2, default 0 (no change). It needs the vispy branch that adds it.
Drag to turn, wheel to zoom.

With `uv run`, vispy comes from your local clone (~/code/i2k/napari/vispy),
installed in editable mode by the [tool.uv.sources] line at the top, so your
edits show up the next time you run it.

Data: BrainGlobe atlas kim_dev_mouse_e15-5_lsfm_20um, Kronman et al.,
Nat Commun 2024, https://doi.org/10.1038/s41467-024-53254-w. Run example 3
once first if the data isn't downloaded yet.

Run:  uv run examples/03c_attenuated_mip_vispy.py
"""

from pathlib import Path

import numpy as np
import tifffile
import vispy
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from vispy import scene

vispy.use("pyqt6")
version = getattr(vispy, "__version__", "(local checkout, not installed)")
print(f"vispy {version} from {Path(vispy.__file__).parent}")

# ---------------------------------------------------------------------------
# The data: exactly the same preparation as example 3
# ---------------------------------------------------------------------------

ATLAS = "kim_dev_mouse_e15-5_lsfm_20um_v1.3"
DATA_FILE = (
    Path(__file__).parent.parent
    / "data"
    / "kim_e15-5_lsfm_20um"
    / ATLAS
    / "reference.tiff"
)
if not DATA_FILE.exists():
    raise SystemExit(f"No {DATA_FILE}; run example 3 once to download it")

volume = tifffile.imread(DATA_FILE)  # (600, 412, 480), uint16, 20 µm voxels
nz, ny, nx = volume.shape
volume = volume.reshape(nz // 2, 2, ny // 2, 2, nx // 2, 2).mean(axis=(1, 3, 5))
volume = np.ascontiguousarray(volume, dtype=np.float32)

# napari's automatic contrast limits (see example 3)
three_slices = volume[[0, volume.shape[0] // 2, -1]]
CLIM_DEFAULT = (float(three_slices.min()), float(three_slices.max()))

NAPARI_DEFAULT_ATTENUATION = 0.05
NAPARI_DEFAULT_GAMMA = 1.0
BASE_ATTENUATION_DEFAULT = 0.0  # new in the vispy branch; 0 = today's behaviour

# ---------------------------------------------------------------------------
# The vispy scene, set up like napari's 3D view
# ---------------------------------------------------------------------------

canvas = scene.SceneCanvas(size=(600, 600), bgcolor="black")
view = canvas.central_widget.add_view()
view.camera = scene.ArcballCamera(fov=0)  # napari: arcball, no perspective

vol = scene.visuals.Volume(
    volume,
    method="attenuated_mip",
    clim=CLIM_DEFAULT,
    cmap="grays",
    gamma=NAPARI_DEFAULT_GAMMA,
    attenuation=NAPARI_DEFAULT_ATTENUATION,
    texture_format="auto",  # napari's choice: keep floats, scale on the GPU
    parent=view.scene,
)
view.camera.set_range()


def update_mip_cutoff():
    # napari does this for its default (translucent) blending: ignore
    # anything below the low contrast limit. Must follow every clim change.
    vol.mip_cutoff = vol._texture.clim_normalized[0]


update_mip_cutoff()

# ---------------------------------------------------------------------------
# The window: the canvas, plus napari's controls underneath
# ---------------------------------------------------------------------------


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Example 3c: attenuated MIP, vispy alone")
        layout = QVBoxLayout(self)
        layout.addWidget(canvas.native)

        # Same sliders as example 3 (QSlider counts in whole numbers).
        self.attenuation_slider, self.attenuation_label = self.add_slider_row(
            layout, "attenuation:", 0, 500, round(NAPARI_DEFAULT_ATTENUATION * 1000)
        )
        low, high = round(CLIM_DEFAULT[0]), round(CLIM_DEFAULT[1])
        self.clim_low_slider, self.clim_low_label = self.add_slider_row(
            layout, "contrast low:", low, high, low
        )
        self.clim_high_slider, self.clim_high_label = self.add_slider_row(
            layout, "contrast high:", low, high, high
        )
        self.gamma_slider, self.gamma_label = self.add_slider_row(
            layout, "gamma:", 20, 200, round(NAPARI_DEFAULT_GAMMA * 100)
        )
        self.gamma_slider.setSingleStep(2)
        # base attenuation: 0 to 0.2, steps of 0.001 (counts in
        # thousandths). Above about 0.2 nearly everything goes dark.
        self.base_slider, self.base_label = self.add_slider_row(
            layout, "base attenuation:", 0, 200, round(BASE_ATTENUATION_DEFAULT * 1000)
        )
        self.on_change()

    def add_slider_row(self, layout, name, minimum, maximum, value):
        """A row: name, slider, current value. Returns (slider, value label)."""
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.valueChanged.connect(self.on_change)
        value_label = QLabel()
        value_label.setMinimumWidth(60)
        row = QHBoxLayout()
        name_label = QLabel(name)
        name_label.setMinimumWidth(100)
        row.addWidget(name_label)
        row.addWidget(slider)
        row.addWidget(value_label)
        layout.addLayout(row)
        return slider, value_label

    def on_change(self):
        """Any slider moved: set the vispy properties (vispy redraws)."""
        vol.attenuation = self.attenuation_slider.value() / 1000
        vol.clim = (self.clim_low_slider.value(), self.clim_high_slider.value())
        update_mip_cutoff()
        vol.gamma = self.gamma_slider.value() / 100
        vol.base_attenuation = self.base_slider.value() / 1000
        self.update_labels()

    def update_labels(self):
        self.attenuation_label.setText(f"{vol.attenuation:.3f}")
        self.clim_low_label.setText(f"{vol.clim[0]:.0f}")
        self.clim_high_label.setText(f"{vol.clim[1]:.0f}")
        self.gamma_label.setText(f"{vol.gamma:.2f}")
        self.base_label.setText(f"{vol.base_attenuation:.3f}")


def main():
    app = QApplication.instance() or QApplication([])
    window = Window()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
