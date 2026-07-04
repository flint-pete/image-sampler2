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
- Analysis Section 11 update: added Hanwha data point (W08D bottom camera,
  2560x1920, raw-preserved) — JFIF only, NO EXIF. 2 of 3 tested cameras author no
  metadata; confirms metadata presence is model-specific/unpredictable, which is
  exactly why the vendor-agnostic preserve-if-present design is correct (no
  per-camera special-casing; future EXIF-bearing cameras work with no code
  change). Corrected the earlier "Hanwha likely carries EXIF" assumption and the
  capture-time note (capture_timestamp is ALWAYS node clock per Section 13, never
  camera). Hanwha open item resolved.

- Analysis Section 14: OPEN Q2 RESOLVED. (Check 1) Data-service honors
  client-supplied timestamps — across 18,873 fleet upload records the API record
  timestamp equals the supplied ns prefix 100% (gap <1ms), and genuinely
  back-dated file-forager records (~5.5h behind source; oldest 23.7h back) are
  stored and retrievable at their back-dated time. So a capture-time record
  timestamp is safe at the data layer. (Check 2) slack-hummingbird watcher uses a
  FIXED 120s relative lookback (safe pattern, not a max-ts cursor), so it won't
  permanently drop back-dated records; the image-sampler2 capture-time switch
  affects image-upload records (already tolerated via the 240s deferred image
  queue), not the near-real-time detection records the watcher polls. Follow-up
  only if inference plugins later adopt capture-time: widen detection lookback to
  >=300s. Section 13 production prerequisite CLEARED for image-sampler2.

### Changed
- Design (EXIF field set, Section 12 — LOCKED): Option C hybrid — standard EXIF
  tags where a real one fits (Model=vsn, Software=plugin+version, DateTimeOriginal
  =capture, ImageUniqueID=SHA256, GPS=lat/lon) PLUS a complete JSON blob in
  UserComment for lossless round-trip of all 13 fields. unique_id = SHA256 of the
  saved JPEG bytes (also an integrity check).
- Design (timestamp source + filename, Section 13 — LOCKED): the ONE authoritative
  time is the NODE Linux clock (RTC/GPS-disciplined), never the camera. Filename
  prefix switches from send-time (upstream) to CAPTURE time (node time_ns() at
  grab); upload time (node time_ns() at send) is stored in meta+EXIF. Filename
  scheme Opt-4: `<node_capture_ts_ns>-v2-<vsn>-<camera>.jpg`. The "v2" marker
  flags the changed timestamp meaning + new machinery; vsn fixes cross-node ns
  collisions; camera fixes same-node batch collisions; the guaranteed 1:1 key is
  the EXIF SHA256. PREREQUISITE before production: resolve back-dated-timestamp
  handling (open Q2) and audit the watcher polling window.

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
