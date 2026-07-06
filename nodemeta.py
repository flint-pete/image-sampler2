#!/usr/bin/env python3
# ANL:waggle-license
#  This file is part of the Waggle Platform.  See LICENSE.waggle.txt.
# ANL:waggle-license
#
# image-sampler2 -- node identity resolution.
#
# ============================================================================
# TODO(sage-ci): REPLACE THE PLACEHOLDER RUNTIME LOOKUP  <-- grep for "sage-ci"
# ============================================================================
# As of 2026-07-06 there is NO supported way for a plugin to learn its own VSN
# or GPS lat/lon at runtime. Verified four ways:
#   1. pywaggle 0.56 has no gps/vsn/location/node API (source grep: zero hits).
#   2. pywaggle "writing-a-plugin" docs expose only publish/subscribe/upload_file.
#   3. A live `ses` plugin pod has only WAGGLE_PLUGIN_* + WAGGLE_SCOREBOARD env
#      and mounts only /run/waggle/{uploads,data-config.json}. /etc/waggle/ is a
#      node-HOST path and is NOT mounted into pods, so the node manifest is
#      unreadable from inside a plugin container.
#   4. The existing yolo/bioclip plugins do not self-identify at all -- they just
#      upload_file() and let Beehive attach node identity DOWNSTREAM via routing.
#
# The Sage cyberinfrastructure team is adding runtime "GPS call" and "VSN call"
# APIs (expected within days of 2026-07-06). WHEN THAT LANDS:
#   - Implement `_runtime_identity()` below to call the real APIs (likely a
#     pywaggle helper or a WES service such as wes-gps-server / a metadata svc).
#   - Return {"vsn": <str>, "lat": <float|None>, "lon": <float|None>,
#     "node_id": <str|None>} from whatever the CI team ships.
#   - Delete the PLACEHOLDER path and this banner.
# Everything downstream (the v2 filename, EXIF GPS, meta) already consumes the
# dict this module returns, so the swap is confined to `_runtime_identity()`.
# ============================================================================
#
# Resolution precedence (high -> low), applied per field:
#   1. explicit CLI flag / caller value (operator override; also used off-node)
#   2. runtime identity  -> PLACEHOLDER today, real GPS/VSN calls after sage-ci
#   3. node manifest / /etc/waggle files  (works ONLY when run on the node host,
#      e.g. dev/spikes; never inside a real pod)
# Node identity is NOT required for a correct upload: Beehive attributes the node
# from message routing regardless. vsn only shapes the v2 filename; lat/lon only
# enrich EXIF GPS and are OMITTED (never faked) when unknown.

import json
import os

DEFAULT_MANIFEST_PATH = os.environ.get(
    "WAGGLE_NODE_MANIFEST", "/etc/waggle/node-manifest-v2.json")
DEFAULT_VSN_FILE = "/etc/waggle/vsn"
DEFAULT_NODE_ID_FILE = "/etc/waggle/node-id"

# Placeholder VSN used ONLY until the sage-ci runtime VSN call exists. Overridable
# via env so an operator can stamp a real vsn per job in the meantime. Deliberately
# NOT a real node name -- it must be obvious in filenames/metadata that this is a
# stand-in (e.g. "1783...-v2-NODE-top.jpg"). Beehive still attributes the real
# node via routing, so this only affects the human-facing filename.
PLACEHOLDER_VSN = os.environ.get("IS2_PLACEHOLDER_VSN", "NODE")


def _read_text(path):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except (OSError, IOError):
        return None


def load_manifest(path=None):
    """Load the node manifest JSON, or {} if absent/unreadable/malformed.

    Never raises. NOTE: the manifest is only readable when running on the node
    HOST (dev/spikes); it is NOT mounted into plugin pods. See the sage-ci banner.
    """
    path = path or DEFAULT_MANIFEST_PATH
    txt = _read_text(path)
    if not txt:
        return {}
    try:
        obj = json.loads(txt)
        return obj if isinstance(obj, dict) else {}
    except (ValueError, TypeError):
        return {}


def _runtime_identity():
    """Runtime node-identity lookup.

    TODO(sage-ci): PLACEHOLDER. Today this returns nothing resolvable (vsn/lat/lon
    all None) because no runtime GPS/VSN query exists (see the banner at the top of
    this file). When the Sage CI team ships the runtime calls, implement them HERE
    and return real values. Keep the return-dict shape identical so nothing
    downstream changes.

    Returns: {"vsn": None|str, "node_id": None|str, "lat": None|float,
              "lon": None|float}
    """
    # --- BEGIN sage-ci PLACEHOLDER (delete when runtime APIs are available) ---
    return {"vsn": None, "node_id": None, "lat": None, "lon": None}
    # --- END sage-ci PLACEHOLDER ---


def _as_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def resolve_identity(*, vsn=None, node_id=None, lat=None, lon=None,
                     manifest_path=None):
    """Resolve node identity; ALWAYS returns usable values, never fails.

    Per-field precedence: explicit arg > runtime lookup (placeholder today) >
    node manifest / /etc/waggle files (host-only). If vsn is still unknown it
    falls back to PLACEHOLDER_VSN so the v2 filename is always well-formed
    (marked "vsn_is_placeholder": True). lat/lon that cannot be resolved come
    back as None and are simply OMITTED from EXIF GPS -- we never fabricate
    coordinates.

    Returns {vsn, node_id, lat, lon, vsn_is_placeholder}.
    """
    runtime = _runtime_identity()
    manifest = load_manifest(manifest_path)

    # vsn: explicit > runtime > manifest > /etc/waggle/vsn > PLACEHOLDER
    out_vsn = (vsn or runtime.get("vsn") or manifest.get("vsn")
               or _read_text(DEFAULT_VSN_FILE))
    vsn_is_placeholder = not bool(out_vsn)
    if vsn_is_placeholder:
        out_vsn = PLACEHOLDER_VSN

    out_node_id = (node_id or runtime.get("node_id") or manifest.get("name")
                   or _read_text(DEFAULT_NODE_ID_FILE))

    # lat/lon: explicit > runtime > manifest; None -> omitted (never faked)
    out_lat = lat if lat is not None else (
        runtime.get("lat") if runtime.get("lat") is not None
        else manifest.get("gps_lat"))
    out_lon = lon if lon is not None else (
        runtime.get("lon") if runtime.get("lon") is not None
        else manifest.get("gps_lon"))

    return {
        "vsn": out_vsn,
        "node_id": out_node_id or None,
        "lat": _as_float(out_lat),
        "lon": _as_float(out_lon),
        "vsn_is_placeholder": vsn_is_placeholder,
    }
