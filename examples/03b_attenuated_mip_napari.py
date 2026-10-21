# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "tifffile", "napari[pyqt6]"]
# ///
"""Example 3b: the same image as example 3, in real napari

Opens the same volume, prepared the same way (halved with 2x2x2 averages,
float32), in napari's 3D view with rendering = attenuated_mip. Compare it
with example 3 side by side. Because the array is identical, napari picks
the same default contrast limits as example 3, and its ray steps (0.8 voxel)
cover the same voxels.

The AMIP controls are in napari's layer controls panel: attenuation,
contrast limits and gamma.

The camera angle is napari's default, not example 3's; turn either view to
match.

Data: BrainGlobe atlas kim_dev_mouse_e15-5_lsfm_20um, Kronman et al.,
Nat Commun 2024, https://doi.org/10.1038/s41467-024-53254-w. Run example 3
once first if the data isn't downloaded yet.

Run:  uv run examples/03b_attenuated_mip_napari.py
"""

from pathlib import Path

import napari
import numpy as np
import tifffile

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

# Exactly the same preparation as example 3.
volume = tifffile.imread(DATA_FILE)  # (600, 412, 480), uint16, 20 µm voxels
nz, ny, nx = volume.shape
volume = volume.reshape(nz // 2, 2, ny // 2, 2, nx // 2, 2).mean(axis=(1, 3, 5))
volume = np.ascontiguousarray(volume, dtype=np.float32)


def make_viewer():
    viewer = napari.Viewer(ndisplay=3, title="Example 3b: attenuated MIP in napari")
    layer = viewer.add_image(
        volume,
        name="kim e15.5 (halved)",
        rendering="attenuated_mip",  # attenuation is left at napari's default
    )
    print(f"attenuation:     {layer.attenuation}")
    print(f"contrast limits: {layer.contrast_limits}")
    print(f"gamma:           {layer.gamma}")
    return viewer, layer


def main():
    make_viewer()
    napari.run()


if __name__ == "__main__":
    main()
