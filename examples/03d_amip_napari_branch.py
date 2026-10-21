# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "tifffile", "napari[pyqt6]", "vispy", "superqt"]
#
# [tool.uv.sources]
# napari = { path = "../../napari", editable = true }
# vispy = { path = "../../vispy", editable = true }
# superqt = { path = "../../superqt", editable = true }
# ///
"""Example 3d: the napari amip-sliders branch with the vispy and superqt branches

Same image as examples 3 and 3b, in napari from your local clones:
napari (~/code/i2k/napari/napari, branch amip-sliders), vispy
(~/code/i2k/napari/vispy, branch amip-empty-attenuation) and superqt
(~/code/i2k/napari/superqt, branch mapped-slider).

The layer controls show two AMIP sliders:
    attenuation        superqt's QLabeledMappedSlider, power curve, 0 to 0.5
    base attenuation   vispy's new base_attenuation, 0 to 0.2

Data: BrainGlobe atlas kim_dev_mouse_e15-5_lsfm_20um, Kronman et al.,
Nat Commun 2024, https://doi.org/10.1038/s41467-024-53254-w. Run example 3
once first if the data isn't downloaded yet.

Run:  uv run examples/03d_amip_napari_branch.py
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
    viewer = napari.Viewer(ndisplay=3, title="Example 3d: napari amip-sliders branch")
    layer = viewer.add_image(
        volume,
        name="kim e15.5 (halved)",
        rendering="attenuated_mip",  # attenuation is left at napari's default
    )
    print(f"napari {napari.__version__} from {Path(napari.__file__).parent}")
    print(f"attenuation:     {layer.attenuation}")
    print(f"contrast limits: {layer.contrast_limits}")
    print(f"gamma:           {layer.gamma}")
    return viewer, layer


def main():
    make_viewer()
    napari.run()


if __name__ == "__main__":
    main()
