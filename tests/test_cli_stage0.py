# Stage 0 tests for image-sampler2 CLI contract + fail-fast validation.
#
# These are PURE tests: no camera, no network, no pywaggle. They exercise the
# real argparse parser (build_parser) and the pure validator (validate_args),
# asserting that every bad flag combination is rejected with a clear message and
# every good combination is accepted. Section refs (e.g. 2.6) point at
# docs/imagesampler.flint.analysis.txt.
#
# Run:  python3 -m pytest tests/ -q      (or: python3 -m pytest tests/test_cli_stage0.py -v)

import os
import sys
from unittest import mock

import pytest

# Make app.py importable regardless of where pytest is invoked from.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app  # noqa: E402


def parse(argv):
    """Parse argv with the real parser. Returns the args namespace.

    argparse errors (e.g. missing required mode, mutually-exclusive violation,
    bad int) raise SystemExit -- tests that expect those catch SystemExit.
    Cross-flag rules are enforced by validate_args and raise ConfigError.
    """
    return app.build_parser().parse_args(argv)


def validate(argv):
    """Parse then validate. Raises SystemExit (argparse) or ConfigError."""
    args = parse(argv)
    app.validate_args(args)
    return args


# ---------------------------------------------------------------------------
# MODE: required + mutually exclusive (2.2)
# ---------------------------------------------------------------------------

def test_no_mode_is_rejected_by_argparse():
    # argparse enforces the required mode group -> SystemExit
    with pytest.raises(SystemExit):
        parse(["--stream", "top_camera"])


def test_both_modes_rejected_by_argparse():
    with pytest.raises(SystemExit):
        parse(["--one-shot", "--continuous", "10", "--stream", "top_camera"])


def test_continuous_non_integer_rejected_by_argparse():
    with pytest.raises(SystemExit):
        parse(["--continuous", "abc", "--stream", "top_camera"])


@pytest.mark.parametrize("bad", ["0", "-5"])
def test_continuous_non_positive_rejected(bad):
    with pytest.raises(app.ConfigError, match="positive integer"):
        validate(["--continuous", bad, "--stream", "top_camera",
                  "--cache-dir", ".", "--cache-name", "c", "--cache-max-count", "5"])


# ---------------------------------------------------------------------------
# STREAM / NAME (1.2 / 2.2)
# ---------------------------------------------------------------------------

def test_missing_stream_rejected():
    with pytest.raises(app.ConfigError, match="at least one --stream"):
        validate(["--one-shot"])


def test_name_count_mismatch_rejected():
    with pytest.raises(app.ConfigError, match="must match --stream count"):
        validate(["--one-shot", "--stream", "a", "--stream", "b", "--name", "only_one"])


def test_name_count_match_ok():
    args = validate(["--one-shot", "--stream", "a", "--stream", "b",
                     "--name", "x", "--name", "y"])
    assert args.name == ["x", "y"]


def test_names_optional_ok():
    args = validate(["--one-shot", "--stream", "a"])
    assert args.name == []


# ---------------------------------------------------------------------------
# ONE-SHOT: upload-only, cache flags rejected (2.6); --from-cache ok (2.8)
# ---------------------------------------------------------------------------

def test_one_shot_from_camera_ok():
    args = validate(["--one-shot", "--stream", "top_camera"])
    assert args.one_shot is True
    assert args.from_cache is None


@pytest.mark.parametrize("cache_flag", [
    ["--cache-dir", "."],
    ["--cache-name", "c"],
    ["--cache-max-count", "10"],
    ["--cache-max-mb", "50"],
])
def test_one_shot_rejects_cache_flags(cache_flag):
    with pytest.raises(app.ConfigError, match="only valid with --continuous"):
        validate(["--one-shot", "--stream", "a"] + cache_flag)


def test_one_shot_from_cache_ok(tmp_path):
    args = validate(["--one-shot", "--stream", "a", "--from-cache", str(tmp_path)])
    assert args.from_cache == str(tmp_path)


# ---------------------------------------------------------------------------
# --from-cache is one-shot only (2.8)
# ---------------------------------------------------------------------------

def test_from_cache_rejected_in_continuous(tmp_path):
    with pytest.raises(app.ConfigError, match="only valid with --one-shot"):
        validate(["--continuous", "10", "--stream", "a",
                  "--cache-dir", str(tmp_path), "--cache-name", "c",
                  "--cache-max-count", "5", "--from-cache", str(tmp_path)])


# ---------------------------------------------------------------------------
# CONTINUOUS: requires cache-dir, cache-name, >=1 cap (2.6)
# ---------------------------------------------------------------------------

def test_continuous_requires_cache_dir(tmp_path):
    with pytest.raises(app.ConfigError, match="requires --cache-dir"):
        validate(["--continuous", "10", "--stream", "a",
                  "--cache-name", "c", "--cache-max-count", "5"])


def test_continuous_requires_cache_name(tmp_path):
    with pytest.raises(app.ConfigError, match="requires --cache-name"):
        validate(["--continuous", "10", "--stream", "a",
                  "--cache-dir", str(tmp_path), "--cache-max-count", "5"])


def test_continuous_requires_a_cap(tmp_path):
    with pytest.raises(app.ConfigError, match="at least one of --cache-max"):
        validate(["--continuous", "10", "--stream", "a",
                  "--cache-dir", str(tmp_path), "--cache-name", "c"])


def test_continuous_count_cap_ok(tmp_path):
    args = validate(["--continuous", "10", "--stream", "a",
                     "--cache-dir", str(tmp_path), "--cache-name", "c",
                     "--cache-max-count", "100"])
    assert args.continuous == 10
    assert args.cache_max_count == 100


def test_continuous_mb_cap_ok(tmp_path):
    args = validate(["--continuous", "10", "--stream", "a",
                     "--cache-dir", str(tmp_path), "--cache-name", "c",
                     "--cache-max-mb", "50"])
    assert args.cache_max_mb == 50.0


def test_continuous_both_caps_ok(tmp_path):
    args = validate(["--continuous", "10", "--stream", "a",
                     "--cache-dir", str(tmp_path), "--cache-name", "c",
                     "--cache-max-count", "100", "--cache-max-mb", "50"])
    assert args.cache_max_count == 100 and args.cache_max_mb == 50.0


@pytest.mark.parametrize("cap,val", [
    ("--cache-max-count", "0"),
    ("--cache-max-count", "-1"),
    ("--cache-max-mb", "0"),
    ("--cache-max-mb", "-2.5"),
])
def test_continuous_non_positive_caps_rejected(tmp_path, cap, val):
    with pytest.raises(app.ConfigError, match="must be a positive"):
        validate(["--continuous", "10", "--stream", "a",
                  "--cache-dir", str(tmp_path), "--cache-name", "c", cap, val])


# ---------------------------------------------------------------------------
# --cache-dir existence / writability (2.6)
# ---------------------------------------------------------------------------

def test_continuous_cache_dir_missing_rejected(tmp_path):
    missing = str(tmp_path / "does_not_exist")
    with pytest.raises(app.ConfigError, match="not an existing directory"):
        validate(["--continuous", "10", "--stream", "a",
                  "--cache-dir", missing, "--cache-name", "c",
                  "--cache-max-count", "5"])


def test_continuous_cache_dir_not_writable_rejected(tmp_path):
    ro = tmp_path / "readonly"
    ro.mkdir()
    os.chmod(ro, 0o500)  # r-x, no write
    try:
        # root ignores permission bits; skip if we can still write.
        if os.access(str(ro), os.W_OK):
            pytest.skip("running as root: write bit not enforced")
        with pytest.raises(app.ConfigError, match="not writable"):
            validate(["--continuous", "10", "--stream", "a",
                      "--cache-dir", str(ro), "--cache-name", "c",
                      "--cache-max-count", "5"])
    finally:
        os.chmod(ro, 0o700)  # restore so tmp cleanup works


# ---------------------------------------------------------------------------
# --cache-name filesystem safety (2.12)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_name", [
    "has/slash", "has\\back", "has space", "", "tab\tname", "dot/../escape",
])
def test_continuous_bad_cache_name_rejected(tmp_path, bad_name):
    with pytest.raises(app.ConfigError, match="not filesystem-safe|requires --cache-name"):
        validate(["--continuous", "10", "--stream", "a",
                  "--cache-dir", str(tmp_path), "--cache-name", bad_name,
                  "--cache-max-count", "5"])


@pytest.mark.parametrize("ok_name", [
    "hummingcam", "top_camera", "cam-1", "cam.2", "H00F_top",
])
def test_continuous_good_cache_name_ok(tmp_path, ok_name):
    args = validate(["--continuous", "10", "--stream", "a",
                     "--cache-dir", str(tmp_path), "--cache-name", ok_name,
                     "--cache-max-count", "5"])
    assert args.cache_name == ok_name


# ---------------------------------------------------------------------------
# main() exit codes (fail-fast config error -> distinct nonzero code)
# ---------------------------------------------------------------------------

def test_main_ok_one_shot_requires_camera_config():
    # As of Stage 1, one-shot-from-camera needs a camera host (flag or env). With
    # neither, it fails fast as a config error rather than silently exiting OK.
    import os as _os
    saved = _os.environ.pop("CAMERA_HOST", None)
    try:
        rc = app.main(["--one-shot", "--stream", "top_camera"])
    finally:
        if saved is not None:
            _os.environ["CAMERA_HOST"] = saved
    assert rc == app.EXIT_CONFIG_ERROR


def test_main_ok_continuous(tmp_path):
    rc = app.main(["--continuous", "10", "--stream", "top_camera",
                   "--cache-dir", str(tmp_path), "--cache-name", "c",
                   "--cache-max-count", "5"])
    assert rc == app.EXIT_OK


def test_main_config_error_returns_nonzero():
    # one-shot with a cache flag -> ConfigError -> EXIT_CONFIG_ERROR (not 0)
    rc = app.main(["--one-shot", "--stream", "a", "--cache-max-count", "5"])
    assert rc == app.EXIT_CONFIG_ERROR
    assert rc != app.EXIT_OK


def test_main_argparse_error_exits(tmp_path):
    # missing mode -> argparse SystemExit with code 2
    with pytest.raises(SystemExit):
        app.main(["--stream", "a"])


def test_main_stage1_capture_dispatch(tmp_path, monkeypatch):
    # one-shot-from-camera with camera config + env creds -> calls acquire and
    # returns OK. acquire is mocked so no real network/camera is touched.
    import acquire as _acq
    dst = str(tmp_path / "cap.jpg")
    monkeypatch.setenv("CAMERA_USER", "admin")
    monkeypatch.setenv("CAMERA_PASSWORD", "pw")

    calls = {}

    def fake_capture(url, path, timeout):
        calls["url"] = url
        calls["path"] = path
        # write a real file so os.path.getsize works
        with open(path, "wb") as f:
            f.write(b"\xff\xd8fake\xff\xd9")
        return path

    monkeypatch.setattr(_acq, "capture_still_to_path", fake_capture)
    rc = app.main(["--one-shot", "--stream", "top_camera",
                   "--camera-host", "10.0.0.9", "--camera-port", "10000",
                   "--out-path", dst])
    assert rc == app.EXIT_OK
    assert calls["path"] == dst
    assert "cmd=Snap" in calls["url"]


def test_main_stage1_missing_creds_config_error(tmp_path, monkeypatch):
    monkeypatch.delenv("CAMERA_USER", raising=False)
    monkeypatch.delenv("CAMERA_PASSWORD", raising=False)
    rc = app.main(["--one-shot", "--stream", "top_camera",
                   "--camera-host", "10.0.0.9", "--out-path", str(tmp_path / "c.jpg")])
    assert rc == app.EXIT_CONFIG_ERROR


def test_main_stage1_capture_error_returns_capture_code(tmp_path, monkeypatch):
    import acquire as _acq
    monkeypatch.setenv("CAMERA_USER", "admin")
    monkeypatch.setenv("CAMERA_PASSWORD", "pw")
    monkeypatch.setattr(_acq, "capture_still_to_path",
                        mock.Mock(side_effect=_acq.CaptureTimeout("timed out")))
    rc = app.main(["--one-shot", "--stream", "top_camera",
                   "--camera-host", "10.0.0.9", "--out-path", str(tmp_path / "c.jpg")])
    assert rc == app.EXIT_CAPTURE_ERROR


# ---------------------------------------------------------------------------
# summarize() smoke (no crash, includes mode)
# ---------------------------------------------------------------------------

def test_summarize_one_shot():
    args = validate(["--one-shot", "--stream", "top_camera"])
    s = app.summarize(args)
    assert "one-shot" in s and "top_camera" in s


def test_summarize_continuous(tmp_path):
    args = validate(["--continuous", "30", "--stream", "top_camera",
                     "--cache-dir", str(tmp_path), "--cache-name", "c",
                     "--cache-max-count", "5"])
    s = app.summarize(args)
    assert "continuous" in s and "interval=30s" in s
