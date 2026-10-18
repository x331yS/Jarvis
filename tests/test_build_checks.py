"""The bundle must be built from the exact pinned dependency versions."""

from pathlib import Path

from desktop_app.build_checks import pinned_version_mismatches

ROOT = Path(__file__).resolve().parents[1]


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "requirements.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_reports_installed_version_that_differs_from_pin(tmp_path):
    reqs = _write(tmp_path, "faster-whisper==1.2.1\nnumpy>=1.0\n")
    installed = {"faster-whisper": "1.0.3", "numpy": "2.0.0"}

    assert pinned_version_mismatches(reqs, installed.get) == [
        ("faster-whisper", "1.2.1", "1.0.3")
    ]


def test_ignores_pinned_package_left_out_of_the_build_env(tmp_path):
    reqs = _write(tmp_path, "chatterbox-tts==0.1.2  # not bundled\n")

    assert pinned_version_mismatches(reqs, lambda _name: None) == []


def test_ignores_pins_for_other_platforms(tmp_path):
    reqs = _write(tmp_path, 'mlx-whisper==0.4.2; sys_platform == "never"\n')

    assert pinned_version_mismatches(reqs, lambda _name: None) == []


def test_spec_aborts_build_on_mismatched_pins():
    spec = (ROOT / "jarvis_desktop.spec").read_text(encoding="utf-8")

    assert "pinned_version_mismatches" in spec
