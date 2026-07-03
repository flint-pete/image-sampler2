# Changelog

All notable changes to **image-sampler2** are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project (once it diverges from the upstream baseline) will aim to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Convention: after each improvement or design change to the code, add a short
entry under `[Unreleased]`. When a set of changes is cut into a plugin version,
move them under a new `[x.y.z] - YYYY-MM-DD` heading and bump `sage.yaml`.
Group entries as Added / Changed / Fixed / Removed / Deprecated / Security.

## [Unreleased]

### Added
- Analysis Section 9: what a downloaded JPG reveals (cv2.imwrite embeds no EXIF),
  the object-store URL structure, the verified filename->event-log reverse-lookup
  recipe, and the ns-as-key uniqueness problem.
- Analysis Section 10: coarse-clock/coarse-timestamp finding. Diagnosed W096's
  whole-second upload timestamps to file-forager stamping by source-file mtime
  (not time_ns()) and reusing one second across multiple artifacts — a
  plugin-level provenance issue outside image-sampler2/pywaggle. Flagged as an
  upstream action item (raise with file-forager author / Sage data conventions).
- Analysis Section 11: camera-metadata vendor-interface study + live evidence.
  Marker-scanned three real frames: Reolink snapshot (no metadata; camera authors
  none), Mobotix via mobotix-scan (stripped — libav re-encode, only a Lavc tag),
  and Mobotix via imagesampler-mobotix (FULL M1IMG fingerprint + MXF block
  preserved). Documents Reolink/Hanwha/Mobotix acquisition interfaces and decodes
  the Mobotix fingerprint (manufacturer, ms capture time+TZ, per-sensor geometry/
  exposure telemetry).

### Changed
- Design mandate (acquisition/metadata): where possible, acquire the ORIGINAL
  ENCODED image from the camera's native still endpoint and save raw JPEG bytes
  UNTOUCHED so high-quality-camera metadata (e.g. Mobotix M1IMG, Hanwha EXIF) is
  preserved; INJECT our Sage fields as an added EXIF/COM segment without
  re-encoding. OpenCV/RTSP (pixel decode + re-encode) demoted to a fallback for
  stream-only cameras and clearly labeled as re-encoded. Native-still HTTP fetch
  becomes a first-class acquisition source. Prefer camera-side capture time
  (Mobotix TIM/TZN/TIT) when present, else node grab-time.
- Design decision (linking/uniqueness): object name = `<ns>-<camera>.jpg`
  (per-stream, not constant `sample.jpg`); embed immutable provenance as EXIF
  (vsn, camera, capture_ts, plugin+version, per-capture unique id); mirror vsn +
  both timestamps + unique id into the upload record meta for a
  construction-guaranteed 1:1 key. Empirically, `(vsn, ns)` is NOT unique (760
  same-node + 695 cross-node ns collisions in 24h of fleet data, incl.
  coarse/whole-second clocks); `(vsn, ns, filename)` is unique in practice but
  not by construction — hence the per-capture unique id.

## [0.3.8-baseline] - 2026-07-03

Starting point. Not a code change — recorded for provenance.

### Added
- Exact copy of upstream `waggle-sensor/plugin-imagesampler` @ `main`
  (version 0.3.8) as the baseline. Text files sha256-verified against upstream;
  `ecr-meta` binaries size-verified.
- `docs/imagesampler.flint.analysis.txt` — full code study (camera source,
  sampling frequency, save behavior, shortcomings, pywaggle naming + upload
  metadata mechanism, two-timestamp design, verified RTSP timestamp semantics).
- `README-image-sampler2.md` — fork README recording baseline provenance.
