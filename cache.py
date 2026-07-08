#!/usr/bin/env python3
# ANL:waggle-license
#  This file is part of the Waggle Platform.  See LICENSE.waggle.txt.
# ANL:waggle-license
#
# image-sampler2 -- continuous-mode local ring cache (Stage 4, design 2.6).
#
# This module is the PRODUCER's local sink: a per-stream, bounded ring buffer of
# v2-named JPEGs on local disk. It is PURE with respect to camera/network/pywaggle
# -- the only I/O is filesystem -- so it is fully unit-testable with tmp dirs.
#
# Design invariants (2.6):
#   - Per-stream ring at <cache-root>/<cache-name>/<camera>/ (one plugin = one
#     stream, a1); caps applied per stream; no shared state, no locks.
#   - Two independent caps (count, MB decimal 10^6), evict-on-EITHER.
#   - EVICT BEFORE the new file joins the ring; atomic temp->fsync->os.replace so
#     the ring never transiently exceeds caps and no torn file exists under a final
#     name.
#   - Oldest = capture-ts PREFIX in the v2 name (authoritative, no stat); fallback
#     mtime for odd names. Unknown (non-v2) files are left untouched and uncounted.
#   - STATELESS: each capture re-scans the subdir; crash/restart just re-scans.
#   - E3 GUARD: a single new image larger than the size cap (even with an empty
#     ring) is DROPPED with a warning -- keeps the cache valid/bounded.
#   - Fail-SOFT at runtime (a long-running loop must not die on transient FS
#     errors); fail-FAST only at config time (CacheError).
#
# CACHE ROOT (Pete decision 2026-07-06): default auto-detected
#   $IS2_CACHE_ROOT  ->  /local-cache (if it exists)  ->  /tmp
# /tmp is an interim stopgap (pod-local, ephemeral); all logic here assumes a
# future node-persistent, cross-consumer /local-cache mount from the Sage CI team.

import logging
import os
import re

import metadata

logger = logging.getLogger("image-sampler2.cache")

# MB is decimal (10^6) per 2.6.
BYTES_PER_MB = 1_000_000

# Interim vs future cache roots (see module note).
LOCAL_CACHE_DIR = "/local-cache"
TMP_CACHE_DIR = "/tmp"

# A filesystem-safe cache-name: letters, digits, dot, dash, underscore; no path
# separators, no whitespace, not empty, not '.'/'..'.
_CACHE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class CacheError(Exception):
    """Config-time (fail-fast) cache error. Runtime errors are fail-soft (logged)."""


def resolve_cache_root(explicit=None):
    """Resolve the cache ROOT dir. Precedence (2.6):

        explicit (--cache-root)  >  $IS2_CACHE_ROOT  >  /local-cache (if isdir)  >  /tmp

    Returns the base dir as a string. Does NOT create it -- stream_dir() does the
    mkdir + writability check so config errors surface there. Pure except for one
    os.path.isdir probe of /local-cache (monkeypatchable in tests).
    """
    if explicit:
        return explicit
    env = os.environ.get("IS2_CACHE_ROOT")
    if env:
        return env
    if os.path.isdir(LOCAL_CACHE_DIR):
        return LOCAL_CACHE_DIR
    return TMP_CACHE_DIR


# Explanation reused by the fail-fast path and surfaced in --help / docs, so an
# operator who hits it understands the cause without reading the source.
_MISSING_LOCAL_CACHE_MSG = (
    "the shared cache mount %(dir)r is not present (or not a writable directory) "
    "on this node.\n"
    "  image-sampler2 was told to use the shared %(dir)s cache, but nothing is "
    "mounted there.\n"
    "  This means the node is MISSING the 'wes-local-cache-manager' WES component "
    "(and its\n"
    "  /media/plugin-data/local-cache host mount), OR this plugin was started "
    "without the\n"
    "  volume mount that maps the host cache dir to %(dir)s in the pod "
    "(pluginctl run -v ...).\n"
    "  Frames written here would be pod-EPHEMERAL and INVISIBLE to any consumer "
    "plugin, so\n"
    "  image-sampler2 refuses to run rather than silently produce data nobody can "
    "read.\n"
    "  Fix: deploy wes-local-cache-manager on the node (see the component's "
    "DESIGN-AND-PURPOSE.md)\n"
    "  and mount its host dir into this plugin at %(dir)s; OR drop the "
    "shared-cache requirement\n"
    "  (omit --require-local-cache / IS2_REQUIRE_LOCAL_CACHE) to use an interim "
    "local dir instead."
)


def _truthy_env(val):
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def require_local_cache_requested(flag=False):
    """Return True if the caller asserted the shared /local-cache is REQUIRED.

    Sources (either triggers it): the --require-local-cache flag, or the env
    twin IS2_REQUIRE_LOCAL_CACHE (1/true/yes/on). Kept separate/pure so app.py
    and tests share one definition.
    """
    if flag:
        return True
    return _truthy_env(os.environ.get("IS2_REQUIRE_LOCAL_CACHE", ""))


def assert_shared_cache_available(cache_root, *, required):
    """Fail-FAST guard for the shared-cache expectation (config time).

    Two independent checks:

      1. If `required` is True, the resolved cache_root MUST be the shared
         LOCAL_CACHE_DIR and it must exist as a writable directory. This is the
         explicit "I intend to use the shared cache" contract: on a node lacking
         the wes-local-cache-manager component (no /local-cache mount) it raises
         CacheError with a full explanation instead of silently using /tmp.

      2. Even when not `required`, if the caller RESOLVED to LOCAL_CACHE_DIR by
         name (--cache-root /local-cache or IS2_CACHE_ROOT=/local-cache) but the
         dir is missing/unwritable, that is an explicit ask for a path that isn't
         there -> CacheError. (Never silently downgrade a named /local-cache to
         /tmp.)

    Pure except for os.path.isdir / os.access probes (monkeypatchable in tests).
    Raises CacheError (the existing fail-fast type) so app.py's existing handler
    reports it and exits EXIT_CONFIG_ERROR.
    """
    targets_shared = os.path.abspath(cache_root) == os.path.abspath(LOCAL_CACHE_DIR)
    present = os.path.isdir(cache_root) and os.access(cache_root, os.W_OK | os.X_OK)

    if required:
        if not targets_shared:
            raise CacheError(
                "shared cache is REQUIRED (--require-local-cache / "
                "IS2_REQUIRE_LOCAL_CACHE) but the resolved cache root is %r, not "
                "the shared %s. Do not override --cache-root / IS2_CACHE_ROOT when "
                "requiring the shared cache." % (cache_root, LOCAL_CACHE_DIR))
        if not present:
            raise CacheError(_MISSING_LOCAL_CACHE_MSG % {"dir": LOCAL_CACHE_DIR})
        return

    # Not required, but if the operator explicitly named /local-cache, honor the
    # ask: refuse to fall through to /tmp behind their back.
    if targets_shared and not present:
        raise CacheError(_MISSING_LOCAL_CACHE_MSG % {"dir": LOCAL_CACHE_DIR})


def validate_cache_name(name):
    """Return name if filesystem-safe, else raise CacheError (fail-fast, 2.6)."""
    if not name or not _CACHE_NAME_RE.match(name) or name in (".", ".."):
        raise CacheError(
            "cache-name %r must be non-empty and contain only letters, digits, "
            "dot, dash, underscore (no path separators/whitespace)" % (name,))
    return name


def stream_dir(cache_root, cache_name, camera, *, create=True):
    """Compute (and by default create) <cache-root>/<cache-name>/<camera>/.

    cache_name is validated (fail-fast) here. camera is used as a single path
    segment; it must not contain path separators (build_v2_name enforces the same
    for the filename). When create=True: mkdir -p, then verify writability ->
    CacheError on failure (config-time fail-fast). Returns the absolute dir path.
    """
    validate_cache_name(cache_name)
    if not camera or any(c in camera for c in "/\\"):
        raise CacheError("camera %r must be a single path segment (no separators)"
                         % (camera,))
    sdir = os.path.join(cache_root, cache_name, camera)
    if create:
        try:
            os.makedirs(sdir, exist_ok=True)
        except OSError as e:
            raise CacheError("cannot create cache dir %r: %s" % (sdir, e))
        if not os.access(sdir, os.W_OK | os.X_OK):
            raise CacheError("cache dir %r is not writable" % (sdir,))
    return os.path.abspath(sdir)


class RingMember:
    """One managed (v2-named) image in the ring."""

    __slots__ = ("path", "name", "capture_ts_ns", "size", "sort_key")

    def __init__(self, path, name, capture_ts_ns, size, sort_key):
        self.path = path
        self.name = name
        self.capture_ts_ns = capture_ts_ns   # None if derived from mtime fallback
        self.size = size
        self.sort_key = sort_key             # (ts_or_mtime_ns) used for ordering

    def __repr__(self):  # pragma: no cover - debug aid
        return "RingMember(%r, ts=%r, size=%r)" % (self.name, self.capture_ts_ns,
                                                   self.size)


class RingState:
    """Snapshot of a per-stream ring at scan time."""

    __slots__ = ("count", "total_bytes", "members", "unknown_files")

    def __init__(self, members, unknown_files):
        # members: oldest-first list of RingMember
        self.members = members
        self.unknown_files = unknown_files
        self.count = len(members)
        self.total_bytes = sum(m.size for m in members)


def scan_ring(sdir):
    """Scan a per-stream dir -> RingState. Never raises on a missing/odd file.

    Managed members = files whose basename parses as a v2 name (metadata.
    parse_v2_name). Ordering key = capture-ts prefix (authoritative). A v2-looking
    file is always a member; non-v2 files (and .tmp) are UNKNOWN -- counted
    separately, never sized, never evicted. A missing dir yields an empty ring.
    """
    members = []
    unknown = []
    try:
        entries = os.listdir(sdir)
    except FileNotFoundError:
        return RingState([], [])
    except OSError as e:  # pragma: no cover - unusual FS state
        logger.warning("cache scan: cannot list %r: %s", sdir, e)
        return RingState([], [])

    for name in entries:
        path = os.path.join(sdir, name)
        if not os.path.isfile(path):
            continue
        if name.endswith(".tmp"):
            unknown.append(path)          # in-flight write; not a ring member
            continue
        parsed = metadata.parse_v2_name(name)
        try:
            size = os.path.getsize(path)
        except OSError:                   # file vanished mid-scan; skip
            continue
        if parsed is None:
            unknown.append(path)
            continue
        capture_ts_ns = parsed[0]
        members.append(RingMember(path, name, capture_ts_ns, size, capture_ts_ns))

    members.sort(key=lambda m: (m.sort_key, m.name))   # oldest first, stable
    return RingState(members, unknown)


class EvictPlan:
    """Decision for one capture: whether to drop the new image, and what to evict."""

    __slots__ = ("drop_new", "evict", "reason")

    def __init__(self, drop_new, evict, reason=""):
        self.drop_new = drop_new
        self.evict = evict                # list of RingMember to delete, oldest first
        self.reason = reason


def plan_evictions(ring, new_bytes, max_count, max_mb):
    """Pure eviction planner (2.6 steps 3-4). No I/O.

    Given the current ring, the size of the incoming image, and the caps (either
    may be None = that cap unset), decide:
      - E3 GUARD: if a size cap is set and new_bytes alone exceeds it (even with an
        EMPTY ring), drop the new image (drop_new=True, evict=[]).
      - else EVICT oldest-first until BOTH would hold after adding the new image:
            count + 1 <= max_count   AND   bytes + new_bytes <= max_bytes
        (each cap only constrains if set).
    Returns an EvictPlan. Never mutates `ring`.
    """
    max_bytes = max_mb * BYTES_PER_MB if max_mb is not None else None

    # E3 guard: a single image bigger than the whole size budget can never fit.
    if max_bytes is not None and new_bytes > max_bytes:
        return EvictPlan(
            True, [],
            reason="new image %d B exceeds cache-max-mb budget %d B (E3 drop)"
                   % (new_bytes, max_bytes))

    # Simulate adding the new image, evicting oldest until both caps hold.
    remaining = list(ring.members)        # oldest first
    cur_count = ring.count
    cur_bytes = ring.total_bytes
    evict = []

    def over():
        if max_count is not None and cur_count + 1 > max_count:
            return True
        if max_bytes is not None and cur_bytes + new_bytes > max_bytes:
            return True
        return False

    while over() and remaining:
        victim = remaining.pop(0)
        evict.append(victim)
        cur_count -= 1
        cur_bytes -= victim.size

    return EvictPlan(False, evict)


class CommitResult:
    """Outcome of commit_capture."""

    __slots__ = ("written", "final_path", "evicted", "warnings")

    def __init__(self, written, final_path, evicted, warnings):
        self.written = written            # bool: did the new file join the ring?
        self.final_path = final_path
        self.evicted = evicted            # list of paths actually deleted
        self.warnings = warnings          # list[str]


def commit_capture(sdir, tmp_path, final_name, plan):
    """Apply an EvictPlan then atomically publish tmp_path -> <sdir>/<final_name>.

    Order matters (2.6 step 5): EVICT FIRST, then os.replace, so the ring never
    transiently exceeds caps. Fail-SOFT on eviction-delete errors (warn, continue,
    the next cycle retries). If plan.drop_new is True, the tmp is removed and
    nothing is written. Returns CommitResult. Does not raise on runtime FS errors
    except a failure of the final os.replace (which the caller treats as a skipped
    sample).
    """
    warnings = []
    evicted = []

    if plan.drop_new:
        _safe_remove(tmp_path, warnings, "drop-new tmp")
        if plan.reason:
            warnings.append(plan.reason)
        return CommitResult(False, None, evicted, warnings)

    # 1. Evict oldest first (fail-soft: a delete failure is logged, not fatal).
    for victim in plan.evict:
        try:
            os.remove(victim.path)
            evicted.append(victim.path)
        except FileNotFoundError:
            evicted.append(victim.path)   # already gone: eviction goal satisfied
        except OSError as e:
            warnings.append("eviction failed for %r: %s" % (victim.path, e))

    # 2. Publish the new file atomically. tmp_path is assumed already fsync'd by
    #    the writer (capture stage); we just rename into place.
    final_path = os.path.join(sdir, final_name)
    try:
        os.replace(tmp_path, final_path)
    except OSError as e:
        warnings.append("atomic publish failed (%r -> %r): %s"
                        % (tmp_path, final_path, e))
        _safe_remove(tmp_path, warnings, "failed-publish tmp")
        return CommitResult(False, None, evicted, warnings)

    return CommitResult(True, final_path, evicted, warnings)


def _safe_remove(path, warnings, what):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        warnings.append("could not remove %s %r: %s" % (what, path, e))
