## Add QLabeledMappedSlider

Adds `QLabeledMappedSlider`, a `QLabeledDoubleSlider` variant where the slider position is mapped to the value using a log or power curve.

- `"log"`: each decade gets the same space on the slider (range 1 to 100, the middle is 10). The minimum must be greater than 0.
- `"power"`: `minimum + (maximum - minimum) * p ** exponent` (range 0 to 1000, the middle is 500 for `exponent=1` and 250 for `exponent=2`). It can start at 0, with finer control near the minimum.

```python
slider = QLabeledMappedSlider(Qt.Orientation.Horizontal)
slider.setMapping("power")
slider.setExponent(3)
slider.setRange(0, 0.5)
```

Motivation: napari's attenuated MIP slider needs fine control at small values and still needs to reach 0. A custom log slider was tried in napari/napari#8669, and the discussion in napari/napari#8241 suggested a slider like this belongs in superqt. napari/napari#XXXX uses it.

Includes tests, an example (`examples/mapped_slider.py`) and a docs page.

(drag a screenshot of `examples/mapped_slider.py` here)
