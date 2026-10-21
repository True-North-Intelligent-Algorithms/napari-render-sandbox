# napari-render-sandbox

Pre-work and testing for pull requests to napari and friends (vispy,
superqt). Experiments and proofs of concept, not a plugin.

Learning examples for rendering topics that come up in napari: shaders,
volume rendering (MIP, attenuated MIP), splatting for super-resolution data,
and multiscale pyramids. Each example is a single script you can read top to
bottom and run with `uv run`.

| Example | What it shows |
|---|---|
| `examples/01_raw_opengl_mip.py` | A volume MIP shader with raw OpenGL (no vispy): compile, upload a 3D texture, set uniforms, draw |
| `examples/01b_pygfx_mip.py` | The same MIP with pygfx (WebGPU), using its ready-made volume shader |
| `examples/02_smlm_splats_raw_opengl.py` | Additive Gaussian splats of 3D SMLM localizations with raw OpenGL: point sprites, per-point precision, zoom, gain |
| `examples/02b_smlm_elliptical_splats_raw_opengl.py` | The same with anisotropic, axis-aligned splats (sigma x, y, z): R Σ Rᵀ in the vertex shader, the inverse 2D covariance in the fragment shader |
| `examples/02c_gaussian_splats.py` | The GaussianSplat visual from vispy PR #2761 (copied unchanged into `splat_visual.py`), on its cluster fly sample or on the SMLM data: `fly` / `smlm`. The maths is explained in `gaussian_splat_shader.md` |
| `examples/03_attenuated_mip_raw_opengl.py` | Attenuated MIP (Beer-Lambert) for napari#8241: vispy's current shader copied into plain GLSL, with napari's controls (attenuation, contrast limits, gamma) |
| `examples/03b_attenuated_mip_napari.py` | The same volume in real napari, rendering = attenuated_mip, to compare with 03 |
| `examples/03c_attenuated_mip_vispy.py` | The same volume in vispy alone, set up like napari; renders with whichever vispy is installed, so it shows edits to vispy's shader |
| `examples/03d_amip_napari_branch.py` | The napari amip-sliders branch, run against local checkouts of the napari, vispy and superqt branches |

`pr/` holds drafts of the pull request descriptions and their figures for
napari#8241: vispy/vispy#2808, pyapp-kit/superqt#361 and napari/napari#9737.
`gist/` holds standalone demos of those branches, runnable with `uv run`.

## Data

`data/shareloc_zola3d_nup/` holds "Zola-3D NUP full nucleus" (Aristov et al.,
Nat Commun 9, 2409, 2018), from [ShareLoc.XYZ](https://shareloc.xyz),
https://doi.org/10.5281/zenodo.7233696, licensed CC BY 4.0. Example 2
downloads it if it is missing.

`data/kim_e15-5_lsfm_20um/` holds the reference image of the BrainGlobe atlas
`kim_dev_mouse_e15-5_lsfm_20um` (Kronman et al., Nat Commun 2024,
https://doi.org/10.1038/s41467-024-53254-w), the image used in napari#8241.
Example 3 downloads it if it is missing. The atlas README states no license,
so don't commit it to git until the terms are checked.
