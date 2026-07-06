# image-sampler2 — Implementation Plan

Staged, verify-as-you-go build plan for image-sampler2. Companion to the design
doc `docs/imagesampler.flint.analysis.txt` (section refs like "2.6" point there).

## Principles

- **Each stage ends with a verifiable artifact**, not "it runs." The proof is a
  file on disk with the right name/EXIF, or a record in Beehive — never "Running"
  (crash-loops show Running too; verify in the data plane).
- **Build the self-proving skeleton first**, then layer features onto a working
  spine.
- **Interlinked features ship together only when one is meaningless to verify
  without the other** (e.g. capture-ts naming + EXIF both need a real saved frame).
- **Fail-fast on bad config/CLI; fail-soft at runtime** (a bad frame must not kill
  a continuous loop). Config errors exit with a distinct code (2).
- **Defer anything needing a second pod or the shared mount** (2.12) until the
  single-plugin path is solid.
- Preserve old CLI arg *semantics* where they carry over; document changes loudly.

## Status legend

`[DONE]` shipped + verified  ·  `[IN PROGRESS]`  ·  `[TODO]`  ·  `[BLOCKED]`  ·
`[DEFERRED]` (design doc Part 5, not in this plan)

---

## Dependency spine

```
0 ──▶ 1 ──▶ 2 ──▶ ┬─▶ 3 ─┐
                  └─▶ 4 ─┼─▶ 6 ──▶ 7
                        └─▶ 5
```

- Stage 2 depends on 1 (needs a real saved frame to name/EXIF).
- Stages 3 (one-shot upload) and 4 (continuous ring) both build on 2 and are
  independent of each other — can proceed in parallel or serially.
- Stage 5 (heartbeat) needs 4 (a ring to report on).
- Stage 6 (--from-cache + self-exit) needs both 3 (upload path) and 4 (a populated
  cache).
- Stage 7 (deploy/package) needs the whole core (0–6) proven.

**Serialization choice (Pete to confirm):** review cadence favors serial 3 → 4
over parallel, giving cleaner per-stage review checkpoints for a single reviewer.
Default assumption below: serial.

---

## Stage 0 — Repo skeleton + CLI contract + fail-fast  `[DONE]`

Commit `6c05e53`.

**Features:** argparse two-mode group (`--one-shot` / `--continuous SECONDS`,
mutually-exclusive-required); `--stream`/`--name`; `--from-cache`;
`--cache-dir`/`--cache-name`/`--cache-max-count`/`--cache-max-mb` (parsed +
validated, not yet used); pure `validate_args()` with all fail-fast rules
(2.2/2.6/2.8/2.12). Stage 0 performs NO capture: it validates, prints the config,
exits 0. Config errors exit 2.

**Verified:** `tests/test_cli_stage0.py` — 45 pure tests (no camera/network) over
every bad + good flag combination, all passing; real subprocess exit codes
confirmed (0 valid / 2 config). ecr-meta flag docs written. `.gitignore` added.

---

## Stage 1 — Single real capture → save raw bytes  `[DONE]`  (the acquisition spine)

Commit: see git log (Stage 1). Verified on H00F 2026-07-06.

**Shipped:**
- `acquire.py`: native-still fetch (`build_reolink_snap_url` with query-param auth,
  no %-encode of password punctuation; `fetch_raw_still` with a hard timeout;
  raw bytes saved UNTOUCHED via `save_bytes_atomic` temp→fsync→os.replace). JPEG
  validated by SOI/EOI (non-JPEG auth-error blobs rejected, not saved). Timeout vs
  generic error mapped to distinct exceptions; password redacted in logs. OpenCV
  fallback stubbed (raises NotImplementedError).
- `app.py`: one-shot-from-camera path wired. Camera address via `--camera-host`/
  `--camera-port`/`--camera-channel` (env fallbacks CAMERA_HOST/PORT/CHANNEL);
  credentials ENV-ONLY (CAMERA_USER/CAMERA_PASSWORD), never a flag. `--capture-
  timeout`; `--out-path` (Stage-1 temporary sink, replaced by v2 naming in Stage 2).
  New exit code EXIT_CAPTURE_ERROR=3.
- Tests: `tests/test_acquire_stage1.py` (26) + Stage-1 dispatch tests in the CLI
  suite; 74 total, all mocked (no camera/network), all pass.

**Verified on-node (H00F, one live capture):**
- Valid JPEG, 1,226,354 bytes, 3840×2160; SOI ffd8 / EOI ffd9; no `.tmp` litter.
- Design 2.4 CONFIRMED: Reolink `cmd=Snap` returns a BARE JPEG — only DQT/SOF0/DHT,
  NO APP0/JFIF, NO APP1/EXIF, NO COM. No foreign camera segments to preserve on
  this camera (so Stage 2 must inject all provenance metadata itself).
- Timeout path: unreachable host → clean CaptureTimeout after the bounded interval,
  rc=3, no file, no `.tmp`.

**Note (credentials):** the admin password is supplied by Pete and passed via stdin
on-node (kept out of argv/history/files). Not stored in the repo or memory.

---

## Stage 1.5 — EXIF-injection library spike  `[DONE]`  (resolved design 4.4)

**Result:** piexif chosen and VERIFIED. A spike (`spikes/exif_spike.py`) on a JPEG
carrying a foreign COM segment proved: piexif.insert preserves foreign camera
segments (M1IMG survived), the compressed pixel scan is byte-identical (no
re-encode), and our 13-field UserComment JSON + SHA256 ImageUniqueID round-trip.
Decision + API quirks recorded in design 4.4 (BytesIO sink required for in-memory
bytes; UserComment 8-byte charset prefix; GPS needs abs value + N/S/E/W ref — H00F
lon -87.9827; compute SHA256 over the final injected bytes). piexif added to
requirements at Stage 2.

---

## Stage 2 — Capture-ts + v2 naming + EXIF embed  `[TODO]`  (the self-describing file)

**Features:**
- Node-clock `capture_ts = time.time_ns()` at grab (2.9).
- Full v2 filename `<capture_ts_ns>-v2-<vsn>-<camera>.jpg` built by the sampler
  (2.10), written to the cache/output path.
- EXIF embed (2.11) using the Stage-1.5 library: standard tags + UserComment JSON
  blob (13 fields) + SHA256 of final bytes as ImageUniqueID; injected without
  re-encode (2.3).

**Interlinked rationale:** these three are one feature seen three ways — the name
needs the capture_ts; "self-describing" can't be verified without reading the EXIF
back. All operate on the single saved frame from Stage 1.

**Verify (on-node):**
- exiftool/piexif reads back all 13 fields; SHA256 matches the file bytes.
- Filename prefix decodes to the capture instant (node clock).
- Any camera-authored segments survive intact (verify on a Mobotix frame if
  available; on Reolink confirm no corruption).
- `vsn`, `camera`, lat/lon (H00F 41.7180, -87.9827) correct.

---

## Stage 3 — `--one-shot` upload path  `[TODO]`  (first end-to-end cloud result)

**Features:**
- Wire the Stage-2 frame into `plugin.upload_file(path, meta=..., timestamp=capture_ts)`
  (the one-line capture-ts switch, 2.10).
- `upload_timestamp` (node send time) into meta (2.9).
- `plugin.duration.*` phase timing for the one-shot run, in NANOSECONDS (3.2).

**Interlinked rationale:** first stage that produces a Beehive record — the
strongest verification. Closes the whole one-shot-from-camera flow (invocation 1).

**Verify (data plane / Beehive):**
- `upload` record appears; object name carries the capture-ts prefix
  `<ts>-v2-<vsn>-<camera>.jpg`.
- `upload_timestamp` present in meta; `upload_timestamp − timestamp` = a sane,
  positive latency.
- `plugin.duration.*` present.
- Object store is cross-country (~2 min propagation) — allow lag when checking.

---

## Stage 4 — `--continuous` loop + ring cache  `[TODO]`  (the producer)

**Features:**
- Monotonic-grid fixed-period scheduler with skip-on-overrun (2.2 algorithm).
- Per-stream ring under `<cache-dir>/<camera>/` (2.6); evict-before-write atomic
  algorithm (temp→fsync→os.replace); both caps (count + MB), evict-on-either.
- Oversized-new-image drop guard (E3); startup adoption of existing v2 files;
  stateless per-capture scan; fail-soft FS handling.
- Reuses Stages 1–2 (capture + name + EXIF) as the per-tick body.
- Local-only: NEVER uploads (2.8).

**Interlinked rationale:** the loop and the ring are inseparable — an unbounded
loop is wrong, and eviction only means something inside the loop.

**Verify (on-node):**
- Run with tiny caps; ring holds steady at cap; oldest evicted first (by capture-ts
  prefix); count/bytes correct after N cycles; no `.tmp`/torn files under final
  names.
- `kill -9` mid-run then restart → re-scans cleanly, no wipe, no double-count.
- Overrun (interval shorter than a slow capture) → schedule stays on grid, missed
  ticks skipped (no backlog/busy-loop).
- Confirm NOTHING is uploaded (no `upload` records for this instance).

---

## Stage 5 — Continuous heartbeat  `[TODO]`  (producer liveness)

**Features:**
- ~60 s periodic cache-stats heartbeat, decoupled from the sample interval,
  `--heartbeat-secs` configurable (3.2).
- Payload: total image count + total bytes in the cache (per cache-name/stream);
  optional written/evicted-since-last, last capture status. Namespaced topic
  (e.g. `env.imagesampler.cache.count` / `.bytes`), distinct from `plugin.*`.
- Fires even when captures are skipped/failed (the "running but silent" case).
- Stats are ~free (the 2.6 ring scan already computes count+bytes each capture).

**Interlinked rationale:** small, but needs Stage 4's ring to report on; verified
in the data plane (Beehive) rather than on disk, so kept separate.

**Verify (Beehive):**
- Heartbeat records appear ~1/min with count/bytes matching what's on disk.
- Keeps firing when the camera is dark (point at an unreachable stream).

---

## Stage 6 — `--one-shot --from-cache` + self-exit  `[TODO]`  (composition bridge)

**Features:**
- `--from-cache <dir>` newest-selection (2.8), reusing the Stage-3 upload path;
  fail-fast on empty/missing cache dir at run time.
- `--max-count` / `--max-runtime` clean self-exit (3.3), checked at loop tail so
  exit lands on a window edge.

**Interlinked rationale:** `--from-cache` needs both a populated cache (Stage 4)
and the upload path (Stage 3), so it lands after both. It makes the
producer/consumer composition turnkey.

**Verify:**
- Fill a cache with a continuous run; then a separate `--one-shot --from-cache`
  → the NEWEST cached file uploads with its ORIGINAL capture-ts name preserved end
  to end (2.10); no camera hit; no new write; no eviction.
- `--max-count N` / `--max-runtime S` exit at the expected boundary.

---

## Stage 7 — Shared-cache placement + packaging  `[TODO]`  (make it deployable)

**Features:**
- Resolve cache home A-vs-B (4.1): on-node check that the upload-agent only uploads
  pywaggle-staged files (else option A is wrong for a local-only ring); pick the
  cache home.
- Cross-user read permissions (4.2): confirm a different plugin pod can read the
  cache; chmod on write if needed.
- Ready-to-copy SES job PAIR (continuous producer + scheduled `--from-cache`
  uploader) so the simple case is turnkey (2.8).
- ECR build/registration; deps/docs cleanup (3.5: drop croniter, refresh README,
  remove upload.py cruft, pin pywaggle).

**Interlinked rationale:** everything here is "make the proven plugin deployable
and consumable by other pods."

**Verify (on-node / Beehive):**
- A DIFFERENT plugin pod reads the sampler's cache (proves R-A + R-B).
- The job pair runs under SES; heartbeat + (composed) uploads visible in Beehive.
- Note ECR arm64/Thor build constraints (QEMU SIGABRT; token push scope) — see
  main ToDo #14/#15; sideload workaround may be needed.

---

## Deferred (design doc Part 5 — not in this plan)  `[DEFERRED]`

- **5.1 Cache discovery / announcement** — consumers use convention for now.
- **5.2 `--from-cache` time-window selectors** (`--closest-before/after-timestamp`)
  — v1 is newest-only.
- **4.5 resize/quality vs never-re-encode** — still an OPEN design decision; cannot
  be a build stage until resolved. Do not silently re-encode a native-raw image.

## Open decisions feeding this plan

1. **Stage 1.5 spike** — included above (resolves 4.4 before Stage 2). Confirm you
   want it as its own step vs folding the choice into Stage 2.
2. **Serial vs parallel 3/4** — plan assumes serial for review cadence.
3. **This document** lives at `docs/IMPLEMENTATION-PLAN.md`; update the status tags
   as stages land.
