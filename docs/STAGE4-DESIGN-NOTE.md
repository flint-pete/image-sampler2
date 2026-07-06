# Stage 4 Design Note — `--continuous` loop + ring cache (the producer)

Status: DRAFT for review (Pete). Do NOT implement until approved.
Date: 2026-07-06.
Design refs: analysis.txt 2.1 (producer role), 2.2 (scheduler), 2.6 (ring),
2.7 (cache EXIF/naming), 2.8 (local-only), 4.1 (cache home — RESOLVED → B),
4.2 (cross-user perms — OPEN, deferred). Plan: IMPLEMENTATION-PLAN.md Stage 4.

---

## 1. Goal

Add the `--continuous` producer: a drift-free periodic loop that captures a frame
each tick and writes it into a per-stream, bounded ring-buffer cache on local
disk. **Never uploads** (local-only, 2.8). Reuses the Stage 1–2 capture + name +
EXIF body verbatim as the per-tick action. This is the "producer" half of the
producer/consumer design; a later consumer (or Stage 6 `--one-shot --from-cache`)
reads the ring.

Out of scope for Stage 4 (explicitly deferred): the heartbeat (Stage 5),
`--from-cache` + self-exit (Stage 6), cross-user read permissions (4.2),
resize/quality (4.5).

---

## 2. Decisions already locked (from analysis.txt — not reopening)

These are settled; the note records them so implementation is unambiguous.

- **Scheduler (2.2):** monotonic-grid with skip-on-overrun. `tick` recomputed from
  elapsed monotonic time each cycle → O(1) jump past missed slots, no backlog, no
  busy-loop. Monotonic clock for *scheduling*; wall-clock for the *stamp*.
- **Bounded capture (2.2):** hard timeout on the grab; on timeout/error WARN + SKIP
  the sample, NO inline retry; one bad frame never kills the loop (fail-soft).
- **Ring (2.6):** per-stream subdir `<cache-dir>/<camera>/`, independent ring, caps
  applied per stream (no shared state, no locks). Two independent caps
  (`--cache-max-count`, `--cache-max-mb`), evict-on-EITHER. Evict-BEFORE-write.
  Atomic write (`.tmp` → fsync → `os.replace`). Oldest = capture-ts prefix in the
  v2 name (no stat). Stateless: each capture re-scans the subdir. Startup adoption
  of existing v2 files; never wipe. E3 guard: a single new image bigger than the
  size cap is dropped with a WARNING (keeps the ring valid).
- **Cache file naming/EXIF (2.7):** identical to what `--one-shot` would upload —
  `<capture_ts_ns>-v2-<vsn>-<camera>.jpg` with full Sage EXIF embedded. No
  `upload_timestamp` (that's a consumer concern).
- **4.1 cache home → Option B (RESOLVED 2026-07-06, empirically):** the WES
  upload-agent (`waggle-sensor/wes-upload-agent`, `main.sh`) rsyncs any
  `/uploads/[<job>/]<plugin>/<version>/<ts>-<sha1>/` dir to beehive **and deletes
  the source** (`rsync --remove-source-files`). So the ring must live in a
  dedicated subtree OUTSIDE the upload mount, or the agent would both upload our
  local-only files and delete them out from under our eviction. `--cache-dir`
  points at that subtree; it is never `/run/waggle/uploads`.

---

## 3. Module plan (small, testable, reuses Stages 1–3)

New module **`cache.py`** — the ring, pure and stateless. No camera, no network,
no pywaggle → fully unit-testable with tmp dirs. Proposed API:

```
class CacheError(Exception): ...            # config-time (fail-fast) issues only

def stream_dir(cache_dir, camera) -> str
    # <cache-dir>/<camera>; create with parents if missing (mkdir -p semantics).

def scan_ring(stream_dir) -> RingState
    # RingState = {count, total_bytes, members:[(capture_ts_ns, path, size)] oldest-first,
    #              unknown_files:[...]}  -- members are v2-name matches only;
    # ordering by capture-ts prefix, fallback mtime for odd names; unknown files
    # counted separately and never touched/sized.

def plan_evictions(ring, new_bytes, max_count, max_mb) -> EvictPlan
    # returns {drop_new: bool, evict:[paths oldest-first]} implementing the E3 guard
    # + evict-loop (2.6 steps 3–4). Pure function of its inputs (no I/O) -> trivially
    # unit-testable for all cap combinations.

def commit_capture(stream_dir, tmp_path, final_name, plan) -> CommitResult
    # apply evictions (delete oldest), then os.replace(tmp -> final). Fail-soft:
    # eviction-delete errors WARN + continue; returns {written, evicted, warnings}.
```

New module **`capture.py`** (or a shared function in `acquire`/`upload`) — the
per-tick body factored out of `_one_shot_from_camera` so continuous and one-shot
share ONE capture+embed path (DRY; guarantees identical bytes/naming/EXIF):

```
def capture_and_embed_to_tmp(*, url, capture_timeout, ident, job, task,
                             plugin, camera, cache_stream_dir) -> (tmp_path, final_name, size, capture_ts_ns)
    # grab (bounded) -> embed_all (Stage 2) -> write .tmp in the stream dir.
    # Raises CaptureError/CaptureTimeout on grab failure (caller warns+skips).
```

`app.py` — new **`_continuous_to_cache(args)`** dispatch:
```
1. Resolve identity once (nodemeta, Stage 3 placeholder-aware).           # cheap, reused per tick
2. Build the Reolink URL once (creds from env, Stage 3).
3. stream = args.stream[0]; camera = args.name[0] if args.name else stream
4. sdir = cache.stream_dir(args.cache_dir, camera)   # fail-fast if cache_dir missing/unwritable (validate_args already checks)
5. Run the 2.2 monotonic-grid loop:
     each tick:
       try: tmp,final,size,ts = capture.capture_and_embed_to_tmp(...)
       except (CaptureError, CaptureTimeout): WARN; continue          # fail-soft skip
       ring = cache.scan_ring(sdir)
       plan = cache.plan_evictions(ring, size, args.cache_max_count, args.cache_max_mb)
       if plan.drop_new: WARN(E3); delete tmp; continue
       res = cache.commit_capture(sdir, tmp, final, plan)
       log one line: wrote <final> size=.. evicted=.. ring_count=.. ring_mb=..
   (No exit condition in Stage 4 — runs until killed; --max-count/--max-runtime
    self-exit is Stage 6.)
```

Existing `_one_shot_from_camera` is refactored to call the SAME
`capture_and_embed_to_tmp` for its grab+embed, then hand the tmp to the upload
path instead of the ring. (Behaviour-preserving refactor; Stage-3 tests must stay
green.)

---

## 4. Flags (already defined in Stage 0 — Stage 4 gives them behaviour)

No new flags. `validate_args` already enforces the fail-fast rules (2.6):
- `--continuous SECONDS` mutually exclusive with `--one-shot` (argparse group).
- `--cache-dir` REQUIRED with `--continuous`; must be existing + writable → else
  fail-fast (exit 2). Confirm validate_args already checks writability; if it only
  checks existence, add the writable check.
- At least one of `--cache-max-count` / `--cache-max-mb` REQUIRED with
  `--continuous` (else unbounded) → fail-fast.
- `--cache-dir` / `--cache-max-*` with `--one-shot` → fail-fast (meaningless).
- **Open TODO to verify in code:** confirm the above are all present in the current
  `validate_args`; the flags exist but Stage 0 may not have wired every rule.

`--cache-max-mb` is decimal MB (10^6 bytes) per 2.6 — be explicit in code.

---

## 5. Deployment / mount (Option B concretely)

- **Local dev / pluginctl testing:** `pluginctl run -v <hostdir>:<cachedir> ...
  -- --continuous <sec> --cache-dir <cachedir> --cache-max-count N`. The hostdir
  is any dir NOT under `/media/plugin-data/uploads`.
- **Scheduled SES job:** needs a provisioned rw mount for the cache subtree
  (hostPath or a user volume). This is a deployment detail; Stage 4 code just takes
  `--cache-dir`. The job-YAML mount wiring can be finalized alongside the consumer
  (it's the consumer that needs to read the same subtree ro).
- **4.2 (cross-user read perms) stays OPEN** and is on the post-initial-code list:
  once the ring writes, confirm the uid it writes as and whether a different-user
  consumer pod can read the files (likely world-readable files + traversable dirs;
  add `chmod` on write if needed). Does NOT block Stage 4 producer work.

---

## 6. Verification plan (on-node, real evidence — per Pete's "verify in data plane")

Ring mechanics are local, so verify ON DISK on H00F (not the data API):

1. **Ring holds at cap.** Run with tiny caps (e.g. `--cache-max-count 5`,
   short interval); after >5 ticks confirm exactly 5 files, oldest evicted first
   (compare capture-ts prefixes), count + bytes correct.
2. **No torn/partial files.** No `.tmp` left under a final name at any point; every
   file a valid JPEG.
3. **Crash-safety.** `kill -9` mid-run, restart → re-scans cleanly, adopts existing
   files, no wipe, no double-count.
4. **Overrun.** Set interval shorter than a slow capture → schedule stays on grid,
   missed ticks skipped (no backlog / busy-loop). Check log timestamps land on the
   grid.
5. **E3 guard.** Set `--cache-max-mb` below a single frame size → new image dropped
   with WARNING, ring stays valid, loop continues.
6. **Local-only.** Confirm NOTHING is uploaded: no `upload` records for this
   instance in the data API over the run window; and the cache dir is NOT under the
   uploads mount (4.1).
7. **Fail-soft.** Point at an unreachable camera → WARN+skip each tick, loop keeps
   running, no crash.

---

## 7. Staged implementation order (small commits, tests each step)

Per Pete's staged workflow — each is a reviewable commit with tests + CHANGELOG.

- **4a — `cache.py` pure ring** (scan_ring, plan_evictions, commit_capture,
  stream_dir) with exhaustive unit tests (all cap combos, E3, adoption, unknown
  files, ordering, atomic replace, eviction fail-soft). No app wiring yet.
- **4b — factor `capture_and_embed_to_tmp`** shared body; refactor
  `_one_shot_from_camera` to use it (Stage-3 tests stay green — behaviour
  preserving).
- **4c — `_continuous_to_cache` loop** in app.py wiring 4a+4b + the 2.2 scheduler;
  unit-test the loop with a fake clock + fake capture (no camera): assert grid
  scheduling, skip-on-overrun, evict-before-write ordering, fail-soft skip.
- **4d — on-node verification** (section 6) on H00F via pluginctl with a mounted
  cache dir; record results in CHANGELOG + this note.
- Update IMPLEMENTATION-PLAN Stage 4 → done; mirror analysis.txt if it changed.

---

## 8. Open questions for Pete before/while building

1. **Scheduler `tick` naming vs `--continuous` value:** confirm `--continuous`
   takes the interval in **seconds** (Stage 0 flag help says SECONDS). OK to keep
   integer seconds, or allow fractional? (Design says `interval_s`; I'll accept
   float, validate > 0.)
2. **Multi-stream in one process?** 2.6 says "each `--stream` (own process) writes
   its own subdir" and caps are per-stream. Current CLI takes `--stream` as a list.
   For Stage 4, do we (a) support only ONE stream per `--continuous` process (fail-
   fast if >1, matching "own process" and your one-plugin-per-model preference), or
   (b) loop over multiple streams in one process? I lean (a) — simpler, matches the
   locked per-process model; multi-stream = run multiple jobs. Confirm.
3. **`--cache-name`** (2.7/2.8 mention a cache-name): is it just an alias/label for
   the subdir, or does it change the on-disk layout? Current flags include
   `--cache-name`; I'll treat it as the subdir name override (default = camera).
   Confirm intended semantics.
4. Anything you want logged per tick beyond `wrote/size/evicted/ring_count/ring_mb`?
