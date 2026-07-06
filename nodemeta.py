#!/usr/bin/env python3
# ANL:waggle-license
#  This file is part of the Waggle Platform.  See LICENSE.waggle.txt.
# ANL:waggle-license
#
# image-sampler2 -- node identity resolution (Stage 3).
#
# The Sage/Waggle platform does NOT expose node identity (VSN, node id, GPS) as
# pod environment variables. pywaggle reads only messaging plumbing vars
# (WAGGLE_PLUGIN_*, WAGGLE_APP_ID). Verified on H00F: node identity lives in files
# under /etc/waggle/:
#   - /etc/waggle/node-manifest-v2.json : {"vsn","name","gps_lat","gps_lon",...}
#   - /etc/waggle/vsn                   : e.g. "H00F"
#   - /etc/waggle/node-id               : e.g. "00004CBB4701D16C"
# Node identity is otherwise attached DOWNSTREAM by Beehive via message routing;
# the plugin only needs vsn (+ camera) to build the v2 filename, and lat/lon to
# enrich the EXIF GPS. This module resolves those in a fleet-portable way so the
# same image is correct on any of the ~100 nodes with no per-node config.
#
# Resolution precedence (high -> low), applied per field by the caller:
#   1. explicit CLI flag / caller value
#   2. node-manifest-v2.json
#   3. /etc/waggle/vsn and /etc/waggle/node-id (for vsn / node_id only)
# Missing vsn is fatal for the v2 name (caller decides); missing lat/lon just
# omits EXIF GPS.

import json
import os

DEFAULT_MANIFEST_PATH = os.environ.get(
    "WAGGLE_NODE_MANIFEST", "/etc/waggle/node-manifest-v2.json")
DEFAULT_VSN_FILE = "/etc/waggle/vsn"
DEFAULT_NODE_ID_FILE = "/etc/waggle/node-id"


def _read_text(path):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except (OSError, IOError):
        return None


def load_manifest(path=None):
    """Load the node manifest JSON, or {} if absent/unreadable/malformed.

    Never raises: a missing manifest is a normal case off-node (dev/CI) and must
    not crash the plugin -- the caller falls back to flags.
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


def resolve_identity(*, vsn=None, node_id=None, lat=None, lon=None,
                     manifest_path=None):
    """Resolve node identity, preferring explicit values over on-node files.

    Returns a dict {vsn, node_id, lat, lon} with each field filled from the first
    available source (explicit -> manifest -> /etc/waggle files for vsn/node_id).
    Values that cannot be resolved come back as None. Pure w.r.t. its inputs; the
    only I/O is reading the manifest/id files, and it never raises.
    """
    manifest = load_manifest(manifest_path)

    out_vsn = vsn or manifest.get("vsn") or _read_text(DEFAULT_VSN_FILE)

    out_node_id = (node_id or manifest.get("name")
                   or _read_text(DEFAULT_NODE_ID_FILE))

    out_lat = lat if lat is not None else manifest.get("gps_lat")
    out_lon = lon if lon is not None else manifest.get("gps_lon")

    def _as_float(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "vsn": out_vsn or None,
        "node_id": out_node_id or None,
        "lat": _as_float(out_lat),
        "lon": _as_float(out_lon),
    }
