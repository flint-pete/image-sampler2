# image-sampler2

An enhanced fork of the Sage/Waggle **imagesampler** plugin
(`waggle-sensor/plugin-imagesampler`, portal: `yonghokim/imagesampler`).

## Status

**Baseline snapshot — not yet modified.** This repo currently contains an exact
copy of the upstream plugin as the starting point for planned enhancements.

## Provenance of the baseline

- Upstream: https://github.com/waggle-sensor/plugin-imagesampler (branch `main`)
- Upstream version at copy time: **0.3.8** (see `sage.yaml`)
- All 12 upstream files copied faithfully (text files sha256-verified against
  upstream; binary `ecr-meta/*.jpg` byte-sizes verified).
- Copied on: 2026-07-03.

## What's added on top of the baseline

- `docs/imagesampler.flint.analysis.txt` — full code study of the upstream
  plugin: camera source, sample frequency, when/how images are saved,
  shortcomings, upgrade options, the pywaggle `{timestamp}-{filename}` naming
  mechanism, upload metadata (what pywaggle vs the server adds), the
  two-timestamp (capture + upload) design, and verified RTSP `sample.timestamp`
  semantics.

## Next steps

Use the analysis doc to write a staged modification plan, then implement.
Nothing in the original source has been changed yet.
