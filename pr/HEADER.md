This is one of three linked PRs for the attenuated MIP improvements in napari/napari#8241:

- vispy/vispy#2808: remove the `-1` offset and add `base_attenuation` to the Volume visual
- pyapp-kit/superqt#361: add `QLabeledMappedSlider`, a slider with a log or power curve
- napari/napari#9737: `base_attenuation` in the Image layer, and the attenuation sliders; depends on the other two

To try all three together (builds them from the PR branches):

```
uv run https://gist.githubusercontent.com/bnorthan/67153ec1bd1e1f3c0e817319dfc05268/raw/amip_napari_demo.py
```
