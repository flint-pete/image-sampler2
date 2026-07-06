# image-sampler2

An enhanced fork of the Sage/Waggle **imagesampler** plugin
(`waggle-sensor/plugin-imagesampler`, portal: `yonghokim/imagesampler`).

## Status

**Stages 0-3 shipped and verified end-to-end on H00F (2026-07-06).** CLI contract
+ fail-fast validation (Stage 0), single real capture (Stage 1), capture-time v2
naming + self-describing EXIF/JSON embed (Stage 2), and the one-shot upload path
to Beehive with placeholder node identity (Stage 3, full Beehive round-trip
confirmed). `--continuous` ring cache + heartbeat land in later stages. Full
design: `docs/imagesampler.flint.analysis.txt`.

> **Platform blockers:** Sage infra bugs encountered building/deploying this
> plugin (arm64/Thor build, buildkit `/proc/acpi`, side-loading path, runtime
> GPS/VSN for node identity) are tracked with issue-ready writeups in
> `~/AI-projects/Infra-problems-to-fix.md`.

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

## Changelog

All improvements and design changes are recorded in `CHANGELOG.md`. **After each
improvement or design change to the code, add a short entry under `[Unreleased]`.**
When a set of changes is cut into a plugin version, move them under a new version
heading and bump `sage.yaml`.
