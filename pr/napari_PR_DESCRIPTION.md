# References and relevant issues

- Part of #8241
- Depends on vispy/vispy#2808 (adds `base_attenuation` to vispy's Volume visual)
- Depends on pyapp-kit/superqt#361 (adds `QLabeledMappedSlider`)
- Builds on #8669 by @TimMonko (his two commits are included)

# Description

- Add `base_attenuation` to the Image layer, passed to vispy, with a slider next to the attenuation slider (default 0, no change)
- Include the default change from #8669: `attenuated_mip` with attenuation 0.005
- The attenuation slider uses superqt's `QLabeledMappedSlider` with a power curve (fine control near 0, and it can reach 0), in place of the custom log slider from #8669
- Update tests for the new defaults, add tests for `base_attenuation`

(drag `napari_controls.png` here)

To try it:

```
uv run https://gist.githubusercontent.com/bnorthan/67153ec1bd1e1f3c0e817319dfc05268/raw/amip_napari_demo.py
```

Tests will fail until releases of vispy and superqt include vispy/vispy#2808 and pyapp-kit/superqt#361.

<!-- AI Policy
The [napari AI use policy and guidelines](https://napari.org/dev/developers/contributing/ai.html) should be read and followed when using AI tools to assist with development.

TLDR: We are humans who enjoy working with other humans. You may use whatever tools you like, but you are ultimately responsible for the changes you submit. Don’t submit changes you haven’t carefully read through yourself, and let us have a conversation with you, not a chatbot.
-->

<!-- Final Checklist
- My PR is the minimum possible work for the desired functionality
- I have commented my code, particularly in hard-to-understand areas
- I have made corresponding changes to docstrings and documentation
  (open a PR on the docs repository (https://github.com/napari/docs) if relevant!)
- I have added tests that prove my fix is effective or that my feature works
- If an API has been modified, I have added a `.. versionadded::` or `.. versionchanged::`
  directive to the appropriate docstring (For more information see
  [the Sphinx documentation](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#describing-changes-between-versions)).
-->
