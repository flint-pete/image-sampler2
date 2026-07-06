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
- Stage 2 (capture-ts + v2 naming + EXIF embed; the self-describing file).
  Verified on H00F 2026-07-06.
  - metadata.py: now_capture_ts_ns (2.9); build_v2_name/object_name_for
    (<capture_ts_ns>-v2-<vsn>-<camera>.jpg, 2.10); build_exif_bytes (2.11 mapping:
    standard tags + full JSON UserComment with 8-byte ASCII prefix; GPS abs-value
    + N/S/E/W ref for negative coords); inject_exif (piexif, no pixel re-encode);
    embed_all (one pass: unique_id -> EXIF -> inject); read_back_fields.
  - app.py: one-shot --out-dir path captures -> embeds -> saves v2-named. New node/
    provenance flags --vsn/--node-id/--job/--task/--plugin-version/--lat/--lon (env
    fallbacks WAGGLE_NODE_*). --out-path retained for raw Stage-1 debug.
    EXIT_CAPTURE_ERROR used for embed failures.
  - requirements.txt: piexif == 1.1.*.
  - tests/test_metadata_stage2.py (16) + Stage-2 dispatch tests; 92 total, all pass.
  - On-node verification: real 4K frame, PIXEL SCAN (SOS..EOI) byte-identical to
    raw (no re-encode, +984 bytes EXIF); unique_id == SHA256(raw); JSON unique_id
    == ImageUniqueID tag; all fields round-trip; APP1/EXIF now present.
- Stage 1 (single real capture -> save raw bytes; the acquisition spine).
  Verified on H00F 2026-07-06.
  - acquire.py: native-still HTTP fetch. build_reolink_snap_url (query-param auth,
    no %-encode of password punctuation, rs cache-buster); fetch_raw_still with a
    hard timeout, returns RAW bytes untouched (no decode/re-encode); JPEG validated
    by SOI/EOI so non-JPEG auth-error blobs are rejected not saved; save_bytes_atomic
    (temp -> fsync -> os.replace, cleans .tmp on failure). CaptureTimeout vs
    CaptureError distinguished; passwords redacted in logs. OpenCV/RTSP fallback
    stubbed (NotImplementedError).
  - app.py: one-shot-from-camera wired. --camera-host/--camera-port/--camera-channel
    (env fallbacks CAMERA_HOST/PORT/CHANNEL); credentials ENV-ONLY (CAMERA_USER/
    CAMERA_PASSWORD), never a flag. --capture-timeout; --out-path (Stage-1 temporary
    sink; replaced by v2 naming in Stage 2). New exit code EXIT_CAPTURE_ERROR=3.
  - tests/test_acquire_stage1.py (26 tests) + Stage-1 dispatch tests; 74 total, all
    mocked (no camera/network), all pass.
  - On-node verification: valid JPEG 1,226,354 bytes 3840x2160, SOI/EOI intact, no
    .tmp litter. Design 2.4 CONFIRMED (Reolink cmd=Snap = bare JPEG, no APP0/APP1/
    COM). Timeout path clean (rc=3, no file).
- docs/IMPLEMENTATION-PLAN.md: staged, verify-as-you-go build plan (Stages 0-7 +
  1.5 spike), each ending in a verifiable artifact; dependency spine and deferred
  items documented. Stage 0 and Stage 1.5 marked DONE.
- Stage 1.5 EXIF-injection spike (spikes/exif_spike.py): resolves design 4.4.
  Proves piexif.insert embeds our EXIF/UserComment WITHOUT re-encoding pixels and
  WITHOUT stripping foreign camera segments (Mobotix M1IMG COM survived; SOS..EOI
  pixel scan byte-identical). 13-field UserComment JSON + SHA256 round-trip; H00F
  negative-lon GPS handled via abs+ref. 6/6 checks pass.
- Stage 0 (CLI contract + fail-fast validation). Rewrote app.py's command-line
  interface to the new two-mode design (docs 2.2/2.6/2.8/2.12):
  - Required, mutually-exclusive mode group: --one-shot | --continuous SECONDS.
  - Source flags: --stream (repeatable, required), --name (repeatable, optional,
    count must match --stream), --from-cache DIR (one-shot only).
  - Ring-cache flags (continuous only): --cache-dir, --cache-name,
    --cache-max-count, --cache-max-mb.
  - Pure, unit-testable validate_args() enforcing every fail-fast rule (both/
    neither mode, non-positive interval, missing stream, name/stream mismatch,
    cache flags in one-shot, --from-cache in continuous, continuous missing
    cache-dir/cache-name/cap, cache-dir not existing/writable, unsafe cache-name,
    non-positive caps). Config errors exit with code 2 (distinct from runtime).
  - Stage 0 performs NO capture: it validates and prints the config, exits 0.
  - tests/test_cli_stage0.py: 45 pure tests (no camera/network) covering every
    bad and good flag combination; all pass. Verified real subprocess exit codes.
  - Added .gitignore (venv, __pycache__, pytest cache, sample.jpg).

### Changed
- Design 2.11/4.4 unique_id semantics superseded by new 4.6 [RESOLVED]: unique_id
  = SHA256 of the ORIGINAL captured frame (before injection), not the final saved
  bytes. A hash of the final file cannot live inside that file (self-reference
  paradox); the source-frame hash is stable and written to BOTH UserComment JSON
  and ImageUniqueID. Object-integrity hash of final bytes, if ever wanted, goes in
  upload meta (Stage 3), not embedded. Mirror re-synced.
- Design doc 4.4: moved OPEN -> RESOLVED (piexif). Recorded the decision and the
  empirically-learned API quirks (BytesIO sink for in-memory bytes; UserComment
  8-byte charset prefix; GPS abs value + N/S/E/W ref, no signed values). Mirror
  re-synced.
- ecr-meta/ecr-science-description.md: rewritten to document the new two-mode CLI
  and every flag (what each does, which mode it belongs to) plus the fail-fast
  rules and usage examples (one-shot, multi-stream, continuous producer,
  --from-cache composition).
- Analysis doc 2.10: added a "HOW THE CAPTURE-TS SWITCH WORKS" note answering how
  we move the filename prefix from upload-time to capture-time given that pywaggle
  assembles the name. Grounded in the current pywaggle source: upload_file() does
  `timestamp = timestamp or get_timestamp()`, so pywaggle only DEFAULTS the
  timestamp — passing an explicit timestamp=capture_ts short-circuits the fallback
  and pywaggle uses our value verbatim for both the filename prefix and the upload
  record timestamp. The whole switch is one argument; we don't bypass pywaggle's
  naming. Noted the MIN_TIMESTAMP_NS constraint (ns int >= 2000-01-01) and that the
  cache path builds the full name itself with no pywaggle call.
- Analysis doc: final cleanup pass. Removed superseded-draft archaeology now that
  the design is settled — stripped the rejected-alternatives list and "Option C"
  labels from 2.11 (EXIF), the "Opt-4" tag from 2.10, and the internal draft
  question IDs (Q0/Q2) from the 2.8/2.13 headings and body cross-references.
  Trimmed the intro's self-referential "this is a rewrite of earlier drafts"
  meta-commentary to a concise reading guide. Kept legitimate design rationale
  (why the naive scheduling loops are rejected), upstream->new flag mappings, and
  the Part 1 defect->where-addressed tags. Verified all section cross-references
  resolve and no dangling Q-number/Option-letter references remain.
- Analysis doc 3.2 (heartbeat/liveness): sharpened and split by mode. Corrected the
  old "every cycle" wording (which would flood the data plane at up-to-1 Hz in
  continuous mode). --one-shot: emit plugin.duration.* for the single run (upload
  record is the primary liveness signal). --continuous (local-only cache producer):
  a PERIODIC CACHE HEARTBEAT ~once a minute (configurable --heartbeat-secs,
  decoupled from the sample interval), NOT per cycle, carrying simple cache stats —
  total image count and total bytes in --cache-dir (optionally images written/
  evicted since last, last capture status, cache-name+camera). It is the sole
  liveness signal in continuous mode and fires even when captures are skipped/
  failed. Documented that plugin.duration.* does NOT apply in continuous mode
  (no discrete run to time; per-capture timing would be noise).
- Analysis doc 2.10 (+ 2.1/2.7): clarified that the FULL v2 name INCLUDING the
  capture-timestamp prefix (<capture_ts_ns>-v2-<vsn>-<camera>.jpg) is applied AT
  CAPTURE TIME, identically in both paths — it is NOT added only at upload. The
  continuous/cache path: the sampler builds the full name itself and writes that
  exact filename into the ring, so cache files on disk already carry the capture-ts
  prefix (which is what makes 2.6 oldest-by-capture-ts eviction and 2.8/5.2
  --from-cache selection work off the filename). The one-shot/upload path: the
  sampler owns the basename and passes timestamp=capture_ts to pywaggle, which
  prepends the same prefix, producing the identical object name. Result: a cached
  file and a one-shot-uploaded file share the same naming structure and capture-ts
  prefix; a --from-cache upload preserves the cached file's original name end to
  end. Replaces the old upload-centric "pywaggle owns the prefix" framing that left
  the cache-file naming implicit.
- Analysis doc: clarified the end-to-end logic/flow of the two modes. Added a
  MODE-AND-FLOW OVERVIEW to 2.1 laying out the full decision tree for all three
  invocations: (1) --one-shot = grab one camera frame, queue for upload, exit
  ("get a sample now" / periodic snapshot); (2) --one-shot --from-cache = upload
  the NEWEST already-cached image (no camera, no write, no evict); (3) --continuous
  = fixed-period producer that writes the local ring and never uploads. Made
  explicit (per user question) that --one-shot is UPLOAD-ONLY and never writes a
  persistent local copy: --cache-dir/--cache-max-* are rejected in one-shot, and
  the staged file is ephemeral upload staging on the host-backed uploads mount (the
  async WES upload-agent completes the transfer after the pod exits). Reinforced
  the "upload always / cache never" vs "cache always / upload never" split and that
  the upload+persist case is met by composition, not a do-everything invocation.
  Reiterated that --from-cache time-window selectors remain a deferred enhancement.
- Analysis doc: renumbered all sections and cross-references from Roman to Arabic
  numerals (PART I->PART 1, II.6->2.6, IV.5->4.5, etc.) so sub-references read as
  3.1 / 4.2 instead of III.1 / IV.2. Content unchanged.
- Analysis doc: complete end-to-end scrub and reorganization (1405 -> 812 lines,
  no loss of verified findings or locked decisions). Restructured into 5 status-
  tagged parts with a legend ([LOCKED]/[VERIFIED]/[REQUIREMENT]/[OPEN]/[DEFERRED]):
  Part I upstream code study (all VERIFIED findings preserved: pywaggle naming,
  RTSP timestamp semantics, metadata evidence, uniqueness + coarse-clock analysis),
  Part II image-sampler2 design (13 locked subsections incl. producer/consumer
  architecture, modes, acquisition mandate, ring cache, Q0/from-cache, timestamps,
  v2 naming, EXIF, shared cache, back-dated-ts verification), Part III requirements
  carried forward (fail-soft loop, heartbeat, self-exit, format/quality, deps,
  tests — promoted from stale "ideas" to REQUIREMENTs), Part IV open items, Part V
  deferred enhancements. Reconciled contradictions from the accreted draft: the
  old "add trigger-based sampling" idea is now DECIDED-against (sampler is a pure
  producer; triggering is a consumer concern); the sample.jpg race is FIXED-in-
  design; the BOTTOM LINE rewritten to the producer/consumer framing; all resolved
  open questions (Q0/Q1/Q2) read as resolved. Surfaced one new OPEN item (IV.5):
  --resize/--jpeg-quality conflicts with the never-re-encode mandate and needs a
  reconciliation decision.

### Fixed
- Analysis Section 3: corrected a dangling "see pitfalls" cross-reference (no such
  section ever existed) to point at Section 4 (Shortcomings), the shared sample.jpg
  race. Added an image-sampler2 RESOLUTION note documenting that the upstream save
  pitfalls are already designed out: the sample.jpg race is eliminated by per-stream
  v2 filenames (Sec 13) + per-stream cache subdirs (Sec 15) + atomic temp->rename
  (Sec 15), and the upload-vs-local mutual exclusivity is replaced by the one-shot/
  continuous mode split (Sec 2b/15).

### Added
- Analysis: Q0 RESOLVED + --from-cache source (LOCKED). --continuous is STRICTLY
  LOCAL-ONLY (never uploads); the cache is its sole sink and uploading is a
  consumer concern. This unlocks the producer/consumer architecture: image-sampler2
  (CPU) fills the shared cache continuously; consumer plugins load a model ONCE,
  batch-infer N cached images, upload the interesting ones, unload, and free the
  GPU (BioClip amortization ~11.4s/img -> ~2.04s/img at N=10, GPU freed after) —
  fixing the single-GPU contention trap. Periodic-snapshot case solved by
  COMPOSITION, not an upload flag: a second SES-cron one-shot job with the new
  --one-shot --from-cache <dir> uploads the NEWEST cached image via the existing
  one-shot upload path (no new upload logic, no camera hit). --from-cache is a
  one-shot-only option (fail-fast if combined with --continuous or empty cache).
  Section 17.2 defers time-window selectors (--closest-before/after-timestamp) for
  cloud-side "pull the cached image nearest time T" use.
- Analysis Sections 16 & 17 (design in progress): shared cache for cross-plugin
  triggers (mode #3) + Planned Enhancements. #3 = continuous ring cache is a
  SHARED buffer other plugins read (e.g. audio lightning trigger uploads the ~10s
  of pre-event frames; remote wildfire alert pulls a matching-moment view). LOCKED:
  uniqueness via a stable user-supplied --cache-name (required with --continuous,
  fs-safe, validated) -> <SHARED_ROOT>/<cache-name>/<camera>/; consumers use
  convention for now. Documented ring<->trigger behavior (2C): size cache >=
  longest trigger lookback; concurrent read+evict is POSIX-safe (open fd survives
  unlink; atomic writes; consumers tolerate ENOENT/TOCTOU); eviction keeps the
  most-recent window. ON-NODE FINDINGS (H00F + edge-scheduler 0.28.0 source):
  CONFIRMED a host-backed, restart-persistent, cross-pod shared mount exists —
  every plugin auto-gets hostPath /media/plugin-data/uploads/<JOB>/<NAME>/<TAG> ->
  /run/waggle/uploads (rw, on 937G NVMe, per-instance); user volumes also exist
  but need a nodeSelector. Open: cache home A (under uploads, needs upload-agent
  scoping check) vs B (dedicated subtree; leaning B); cross-user read perms. Sec 17
  defers the discovery/announcement mechanism (2B option ii) to post-testing.
- Analysis Section 15 (design in progress): continuous-mode local cache / ring
  buffer. --continuous writes to a local --cache-dir (renamed from --out-dir),
  bounded as a ring buffer. LOCKED decisions: --cache-dir required with
  --continuous and rejected with --one-shot (fail-fast); two independent caps
  --cache-max-count / --cache-max-mb (decimal MB), evict-on-either, at least one
  required; per-stream subdirs (<cache-dir>/<camera>/) as independent race-free
  rings; oldest-by-capture-ts-prefix eviction; stateless (scan-each-capture);
  startup adoption of v2-matching files (never wipe, ignore unknowns); per-capture
  algorithm evicts BEFORE the atomic temp->rename so the ring never transiently
  exceeds caps and no torn file joins it; oversized-new-image dropped with warning
  (keep cache valid); fail-soft on delete/disk-full, fail-fast on config. OPEN:
  Q0 — whether --continuous also uploads or is strictly local-only.
- Analysis Section 2b (LOCKED): replace the poorly-named --cronjob flag with two
  descriptive, mutually-exclusive, REQUIRED mode flags — --one-shot (capture once,
  exit; external SES cadence) and --continuous <SECONDS> (run forever on a fixed
  period; interval is the flag's required positive-integer argument). Both/neither
  or interval<=0 are fail-fast parse errors; croniter dependency dropped. Includes
  the LOCKED fixed-period scheduling design: a ~12-line monotonic-grid-with-skip
  loop that never drifts, skips missed ticks on overrun (no backlog), and is
  clock-jump proof; requires a bounded capture (hard timeout -> warn+skip, no
  inline retry; warn at startup if timeout>=interval). Breaking CLI change vs
  upstream.
- Analysis Section 1 design note: camera source selection should prefer the
  acquisition method that yields the best metadata in the resulting JPG — pull the
  original encoded image from the camera's native still endpoint and save raw
  bytes where possible; avoid decode+re-encode paths (which strip camera
  metadata); cross-references Sections 11 and 12.
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
