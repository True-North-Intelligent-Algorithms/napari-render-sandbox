# /// script
# requires-python = ">=3.11"
# dependencies = ["napari[pyqt6]", "vispy", "superqt", "numpy", "tifffile"]
#
# [tool.uv.sources]
# napari = { git = "https://github.com/bnorthan/napari", branch = "amip-sliders" }
# vispy = { git = "https://github.com/bnorthan/vispy", branch = "amip-empty-attenuation" }
# superqt = { git = "https://github.com/bnorthan/superqt", branch = "mapped-slider" }
# ///
"""Attenuated MIP demo for the napari base_attenuation change

Opens a light-sheet volume (the mouse embryo brain used in napari#8241) in
napari's 3D view with all default settings. On this branch the default
rendering is attenuated_mip, and the layer controls show the attenuation
and base attenuation sliders.

    uv run amip_napari_demo.py

uv builds napari, vispy and superqt from the branches named at the top.

Data: BrainGlobe atlas kim_dev_mouse_e15-5_lsfm_20um (Kronman et al.,
Nat Commun 2024, https://doi.org/10.1038/s41467-024-53254-w). If you have
it in your BrainGlobe folder (~/.brainglobe) it is used from there;
otherwise the reference image is downloaded once (111 MB archive) to
~/.cache/vispy-amip-demo.
"""

import tarfile
import urllib.request
from pathlib import Path

import napari
import numpy as np
import tifffile

ATLAS = "kim_dev_mouse_e15-5_lsfm_20um_v1.3"
ATLAS_URL = f"https://gin.g-node.org/brainglobe/atlases/raw/master/{ATLAS}.tar.gz"
BRAINGLOBE_FILE = Path.home() / ".brainglobe" / ATLAS / "reference.tiff"
CACHE_FILE = Path.home() / ".cache" / "vispy-amip-demo" / "reference.tiff"


def find_or_download():
    """Use the BrainGlobe copy if there is one, else download once."""
    if BRAINGLOBE_FILE.exists():
        return BRAINGLOBE_FILE
    if not CACHE_FILE.exists():
        print(f"Downloading {ATLAS} (111 MB), keeping only reference.tiff")
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(ATLAS_URL) as response:
            with tarfile.open(fileobj=response, mode="r|gz") as archive:
                for member in archive:
                    if member.name.endswith("reference.tiff"):
                        with archive.extractfile(member) as source:
                            CACHE_FILE.write_bytes(source.read())
                        break
    return CACHE_FILE


volume = tifffile.imread(find_or_download())  # (600, 412, 480), uint16

# Halve the size in every direction (average each 2x2x2 block).
nz, ny, nx = volume.shape
volume = volume.reshape(nz // 2, 2, ny // 2, 2, nx // 2, 2).mean(axis=(1, 3, 5))
volume = volume.astype(np.float32)

viewer = napari.Viewer(ndisplay=3)
viewer.add_image(volume, name="kim e15.5")

if __name__ == "__main__":
    napari.run()
