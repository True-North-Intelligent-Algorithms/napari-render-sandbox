## Attenuated MIP: remove the `-1` offset and add `base_attenuation`

This is the vispy side of napari/napari#8241, which compares the attenuated MIP formula here with ClearVolume's. The background and discussion are in that issue.

Two changes, one commit each:

- **Remove the `-1` offset.** The attenuation was `exp(-a * (sumval - 1))`, so while the sum is below 1 the scale is above 1 and the first samples along each ray were amplified instead of attenuated. With `exp(-a * sumval)` the scale starts at 1 and only decreases. Existing attenuated MIP renders get slightly dimmer, by a factor of `exp(-a)` (about 5% at napari's default `a = 0.05`).
- **Add `base_attenuation`** (the `0.1` term in ClearVolume). It is added at every step, so rays keep attenuating with depth even through empty or dim regions. The default of 0 keeps the current behaviour.

| `base_attenuation=0` | `base_attenuation=0.1` |
|---|---|
| (drag `fig_empty_0.0.png` here) | (drag `fig_empty_0.1.png` here) |

The light-sheet mouse embryo brain used in the napari issue, side view, `attenuation=0.02`. With base attenuation the deeper vessels fade, which gives a sense of depth.

To try it (builds vispy from this branch):

```
uv run https://gist.githubusercontent.com/bnorthan/5ff8ee64452fd423a1777c2b3f700667/raw/amip_vispy_demo.py
```

and to compare with released vispy:

```
uv run --with "vispy==0.17.0" https://gist.githubusercontent.com/bnorthan/5ff8ee64452fd423a1777c2b3f700667/raw/amip_vispy_demo.py
```

Updated `test_mip_cutoff`, which relied on the `-1` amplification to render full white.
