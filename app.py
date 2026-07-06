#!/usr/bin/env python3
# ANL:waggle-license
#  This file is part of the Waggle Platform.  Please see the file
#  LICENSE.waggle.txt for the legal details of the copyright and software
#  license.  For more details on the Waggle project, visit:
#           http://www.wa8.gl
# ANL:waggle-license
#
# image-sampler2 -- enhanced fork of the Sage/Waggle imagesampler.
# See docs/imagesampler.flint.analysis.txt for the full design (section refs
# below, e.g. "2.2", point at that document).
#
# STAGE 0 (this file): CLI contract + fail-fast validation only. It parses and
# validates every flag combination and then prints the validated configuration
# and exits 0. Acquisition, naming/EXIF, upload, the continuous ring cache, and
# the heartbeat are added in later stages onto this validated spine.

import argparse
import logging
import os
import sys

import acquire

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    datefmt='%Y/%m/%d %H:%M:%S')

logger = logging.getLogger("image-sampler2")


# Exit codes: fail-FAST on bad config/CLI is a clean, distinct nonzero code so a
# scheduler/operator can tell "you invoked me wrong" from a runtime failure.
EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
EXIT_CAPTURE_ERROR = 3


class ConfigError(Exception):
    """Raised for an invalid flag combination (fail-fast config error).

    Kept separate from argparse's own errors so validate_args() is a pure,
    unit-testable function: it raises ConfigError instead of calling exit(),
    and main() is the only place that turns it into a process exit code.
    """


# Filesystem-safe cache-name: letters, digits, dot, dash, underscore. No path
# separators (would let a --cache-name escape SHARED_ROOT/<cache-name>/, 2.12),
# no whitespace, non-empty.
_CACHE_NAME_ALLOWED = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def _is_valid_cache_name(name):
    return bool(name) and all(c in _CACHE_NAME_ALLOWED for c in name)


def build_parser():
    """Build the argparse parser for image-sampler2.

    Returned as a function so tests can construct the parser in isolation.

    Mode is a REQUIRED, mutually-exclusive group (2.2):
      --one-shot            capture once, upload, exit 0.
      --continuous SECONDS  run forever on a fixed period of SECONDS.
    """
    parser = argparse.ArgumentParser(
        prog="image-sampler2",
        description="Sample still images from a camera stream: upload once "
                    "(--one-shot) or maintain a local ring cache (--continuous).")

    # --- mode: required, mutually exclusive (2.2) -------------------------------
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        '--one-shot', dest='one_shot', action='store_true',
        help='Capture exactly one frame, queue it for cloud upload, then exit 0. '
             'External cadence: rely on the SES scheduler to relaunch the pod. '
             'Upload-only: never writes to --cache-dir.')
    mode.add_argument(
        '--continuous', dest='continuous', metavar='SECONDS',
        action='store', type=int, default=None,
        help='Run forever, capturing on a FIXED PERIOD of SECONDS. Local-only: '
             'writes each frame into the ring cache (--cache-dir) and NEVER '
             'uploads. SECONDS must be a positive integer.')

    # --- source ----------------------------------------------------------------
    parser.add_argument(
        '--stream', dest='stream', action='append',
        help='ID or name of a camera stream (e.g. top_camera) or a raw URL '
             '(rtsp://IP:PORT/...). Repeat --stream for multiple streams; each '
             'runs in its own worker process. REQUIRED (at least one).')
    parser.add_argument(
        '--name', dest='name', default=[], action='append',
        help='(optional) Label to report for a stream. When given, the count and '
             'order MUST match the --stream options.')
    parser.add_argument(
        '--from-cache', dest='from_cache', metavar='DIR',
        action='store', default=None, type=str,
        help='ONE-SHOT ONLY. Instead of hitting the camera, upload the NEWEST '
             'image already present in cache DIR (populated by a --continuous '
             'producer). Does not touch the camera, write, or evict.')

    # --- continuous ring cache (2.6 / 2.12) ------------------------------------
    parser.add_argument(
        '--cache-dir', dest='cache_dir', metavar='DIR',
        action='store', default=None, type=str,
        help='CONTINUOUS ONLY. Directory that holds the per-stream ring cache. '
             'Must already exist and be writable. REQUIRED with --continuous.')
    parser.add_argument(
        '--cache-name', dest='cache_name', metavar='NAME',
        action='store', default=None, type=str,
        help='CONTINUOUS ONLY. Stable, filesystem-safe identifier for this '
             'cache instance so consumers can find it and two configs on the '
             'same camera do not collide. REQUIRED with --continuous. Allowed: '
             'letters, digits, dot, dash, underscore (no path separators).')
    parser.add_argument(
        '--cache-max-count', dest='cache_max_count', metavar='N',
        action='store', default=None, type=int,
        help='CONTINUOUS ONLY. Max number of images kept per stream in the ring. '
             'Oldest are evicted first. At least one of --cache-max-count / '
             '--cache-max-mb is REQUIRED with --continuous.')
    parser.add_argument(
        '--cache-max-mb', dest='cache_max_mb', metavar='MB',
        action='store', default=None, type=float,
        help='CONTINUOUS ONLY. Max total size (decimal MB, 10^6 bytes) of the '
             'per-stream ring. Oldest are evicted first. At least one of '
             '--cache-max-count / --cache-max-mb is REQUIRED with --continuous.')

    # --- camera connection (native-still fetch, design 2.3/4.3) ----------------
    # Address may come from flags or env (CAMERA_HOST/PORT/CHANNEL). Credentials
    # are ENV-ONLY (CAMERA_USER / CAMERA_PASSWORD) and never a flag, so they do
    # not appear in process args / shell history / logs.
    parser.add_argument(
        '--camera-host', dest='camera_host', metavar='HOST',
        action='store', default=os.environ.get('CAMERA_HOST'), type=str,
        help='Camera IP/host for the native-still fetch. Defaults to env '
             'CAMERA_HOST. Required for a from-camera capture.')
    parser.add_argument(
        '--camera-port', dest='camera_port', metavar='PORT',
        action='store', default=int(os.environ.get('CAMERA_PORT', "80")), type=int,
        help='Camera HTTP port (default env CAMERA_PORT or 80).')
    parser.add_argument(
        '--camera-channel', dest='camera_channel', metavar='N',
        action='store', default=int(os.environ.get('CAMERA_CHANNEL', "0")), type=int,
        help='Camera channel (default env CAMERA_CHANNEL or 0).')
    parser.add_argument(
        '--capture-timeout', dest='capture_timeout', metavar='SECONDS',
        action='store', default=float(os.environ.get('CAPTURE_TIMEOUT', "10")), type=float,
        help='Hard timeout (seconds) for a single capture (default 10).')
    parser.add_argument(
        '--out-path', dest='out_path', metavar='PATH',
        action='store', default=None, type=str,
        help='STAGE 1 ONLY (temporary): write the captured raw JPEG to PATH. '
             'Later stages replace this with v2 naming + upload/cache.')

    return parser


def validate_args(args):
    """Validate a parsed args namespace; raise ConfigError on any bad combo.

    Pure function (no exit(), no I/O side effects beyond an os.path check on
    --cache-dir) so it is unit-testable. Encodes the fail-fast rules from the
    design doc:
      - exactly one mode (argparse already enforces required + mutually
        exclusive, but we re-check for direct callers/tests)                (2.2)
      - --continuous SECONDS must be a positive integer                     (2.2)
      - at least one --stream                                              (2.2)
      - if --name given, its count must match --stream                     (1.2/2.2)
      - --from-cache is one-shot only                                       (2.8)
      - cache flags (--cache-dir/-name/-max-*) are continuous only          (2.6)
      - --continuous REQUIRES --cache-dir, --cache-name, and at least one cap (2.6)
      - --cache-dir must be an existing, writable directory                 (2.6)
      - --cache-name must be filesystem-safe                                (2.12)
      - caps, if set, must be positive                                      (2.6)
    """
    one_shot = bool(getattr(args, 'one_shot', False))
    continuous = getattr(args, 'continuous', None)

    # exactly one mode
    if one_shot and continuous is not None:
        raise ConfigError("choose exactly one mode: --one-shot OR --continuous, not both")
    if not one_shot and continuous is None:
        raise ConfigError("a mode is required: pass --one-shot or --continuous SECONDS")

    # continuous interval must be positive
    if continuous is not None and continuous <= 0:
        raise ConfigError(f"--continuous SECONDS must be a positive integer (got {continuous})")

    # at least one stream
    streams = args.stream or []
    if len(streams) == 0:
        raise ConfigError("at least one --stream is required")

    # --name count must match --stream count when names are given
    names = args.name or []
    if len(names) > 0 and len(names) != len(streams):
        raise ConfigError(
            f"--name count ({len(names)}) must match --stream count ({len(streams)})")

    # cache flags: which ones were supplied?
    cache_flags_set = [
        ('--cache-dir', args.cache_dir is not None),
        ('--cache-name', args.cache_name is not None),
        ('--cache-max-count', args.cache_max_count is not None),
        ('--cache-max-mb', args.cache_max_mb is not None),
    ]
    any_cache_flag = any(present for _, present in cache_flags_set)

    if one_shot:
        # one-shot is upload-only: cache flags are meaningless -> fail-fast (2.6)
        offending = [flag for flag, present in cache_flags_set if present]
        if offending:
            raise ConfigError(
                "cache flags are only valid with --continuous; "
                f"remove {', '.join(offending)} in --one-shot mode")
        # --from-cache: newest-from-cache is a valid one-shot source
        if args.from_cache is not None:
            if not args.from_cache:
                raise ConfigError("--from-cache requires a non-empty directory path")
            # existence/emptiness of the cache dir is checked at run time in the
            # Stage that implements --from-cache (2.8); Stage 0 only enforces the
            # flag-combination rules.
        return  # one-shot config is valid

    # --- continuous mode ------------------------------------------------------
    # --from-cache is one-shot only (2.8)
    if args.from_cache is not None:
        raise ConfigError("--from-cache is only valid with --one-shot")

    # --continuous REQUIRES --cache-dir and --cache-name (2.6)
    if args.cache_dir is None:
        raise ConfigError("--continuous requires --cache-dir")
    if args.cache_name is None:
        raise ConfigError("--continuous requires --cache-name")

    # at least one cap, else the ring is unbounded (2.6)
    if args.cache_max_count is None and args.cache_max_mb is None:
        raise ConfigError(
            "--continuous requires at least one of --cache-max-count / --cache-max-mb "
            "(an unbounded cache is not allowed)")

    # caps, if given, must be positive
    if args.cache_max_count is not None and args.cache_max_count <= 0:
        raise ConfigError(
            f"--cache-max-count must be a positive integer (got {args.cache_max_count})")
    if args.cache_max_mb is not None and args.cache_max_mb <= 0:
        raise ConfigError(
            f"--cache-max-mb must be a positive number (got {args.cache_max_mb})")

    # --cache-name must be filesystem-safe (2.12)
    if not _is_valid_cache_name(args.cache_name):
        raise ConfigError(
            f"--cache-name '{args.cache_name}' is not filesystem-safe; use only "
            "letters, digits, dot, dash, underscore (no path separators/spaces)")

    # --cache-dir must be an existing, writable directory (2.6)
    if not os.path.isdir(args.cache_dir):
        raise ConfigError(f"--cache-dir '{args.cache_dir}' is not an existing directory")
    if not os.access(args.cache_dir, os.W_OK):
        raise ConfigError(f"--cache-dir '{args.cache_dir}' is not writable")


def summarize(args):
    """Human-readable one-line summary of the validated configuration."""
    if args.one_shot:
        src = f"from-cache={args.from_cache}" if args.from_cache else "from-camera"
        return (f"mode=one-shot ({src}) streams={args.stream} "
                f"names={args.name or '(auto)'}")
    caps = []
    if args.cache_max_count is not None:
        caps.append(f"max_count={args.cache_max_count}")
    if args.cache_max_mb is not None:
        caps.append(f"max_mb={args.cache_max_mb}")
    return (f"mode=continuous interval={args.continuous}s streams={args.stream} "
            f"names={args.name or '(auto)'} cache_dir={args.cache_dir} "
            f"cache_name={args.cache_name} caps=[{', '.join(caps)}]")


def _one_shot_from_camera_stage1(args):
    """STAGE 1: capture ONE raw still from the camera and save it to --out-path.

    Reads credentials from the environment (CAMERA_USER / CAMERA_PASSWORD) --
    never from flags. Builds the Reolink native-still URL and saves the raw bytes
    untouched (no naming/EXIF/upload yet -- Stage 2/3). Returns an exit code.
    """
    if not args.camera_host:
        logger.error("config error: --camera-host (or env CAMERA_HOST) is required "
                     "for a from-camera capture")
        return EXIT_CONFIG_ERROR
    if not args.out_path:
        logger.error("config error: --out-path is required in Stage 1 to save the "
                     "captured frame (temporary; later stages name/upload it)")
        return EXIT_CONFIG_ERROR

    user = os.environ.get("CAMERA_USER")
    password = os.environ.get("CAMERA_PASSWORD")
    if not user or password is None:
        logger.error("config error: set CAMERA_USER and CAMERA_PASSWORD in the "
                     "environment (credentials are never passed as flags)")
        return EXIT_CONFIG_ERROR

    try:
        url = acquire.build_reolink_snap_url(
            args.camera_host, args.camera_port, user, password, args.camera_channel)
    except ValueError as e:
        logger.error("config error: %s", e)
        return EXIT_CONFIG_ERROR

    try:
        out = acquire.capture_still_to_path(url, args.out_path, args.capture_timeout)
    except acquire.CaptureTimeout as e:
        logger.error("capture timeout: %s", e)
        return EXIT_CAPTURE_ERROR
    except acquire.CaptureError as e:
        logger.error("capture error: %s", e)
        return EXIT_CAPTURE_ERROR

    size = os.path.getsize(out)
    logger.info("STAGE 1: captured raw still -> %s (%d bytes)", out, size)
    return EXIT_OK


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
    except ConfigError as e:
        logger.error("config error: %s", e)
        return EXIT_CONFIG_ERROR

    logger.info("image-sampler2 config OK: %s", summarize(args))

    # Dispatch. Stage 1 implements one-shot-from-camera (single stream). Other
    # paths are validated but not yet wired (later stages).
    if args.one_shot and args.from_cache is None:
        if len(args.stream) > 1:
            logger.warning("STAGE 1: multi-stream not wired yet; capturing the "
                           "first stream only (%s)", args.stream[0])
        return _one_shot_from_camera_stage1(args)

    if args.one_shot and args.from_cache is not None:
        logger.info("STAGE 1: --from-cache path not implemented yet (Stage 6).")
        return EXIT_OK

    # continuous
    logger.info("STAGE 1: --continuous path not implemented yet (Stage 4).")
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
