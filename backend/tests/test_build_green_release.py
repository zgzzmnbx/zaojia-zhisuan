from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "tools" / "build_green_release.py"
SPEC = importlib.util.spec_from_file_location("build_green_release", SCRIPT_PATH)
assert SPEC and SPEC.loader
build_green_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_green_release)


def test_copy_preview_column_preferences_uses_saved_project_default(tmp_path):
    project_root = tmp_path / "project"
    release_root = tmp_path / "release"
    preference_path = project_root / build_green_release.PREVIEW_COLUMN_PREFERENCES_RELATIVE_PATH
    preference_path.parent.mkdir(parents=True)
    preference_path.write_text(
        json.dumps(
            {
                "version": 1,
                "preferences": {
                    "defaultLabels": ["项目", "单位"],
                    "sheetOverrides": {"表2": ["项目"]},
                    "headerRows": {"表2": 3},
                    "maxDisplayChars": 12,
                    "columnWidths": {"表2": {"项目": 180}},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    copied = build_green_release.copy_preview_column_preferences(project_root, release_root)

    assert copied is True
    copied_payload = json.loads((release_root / build_green_release.PREVIEW_COLUMN_PREFERENCES_RELATIVE_PATH).read_text(encoding="utf-8"))
    assert copied_payload["preferences"]["headerRows"] == {"表2": 3}
    assert copied_payload["preferences"]["columnWidths"]["表2"]["项目"] == 180


def test_copy_preview_column_preferences_generates_release_default_when_missing(tmp_path):
    project_root = tmp_path / "project"
    release_root = tmp_path / "release"
    project_root.mkdir()

    copied = build_green_release.copy_preview_column_preferences(project_root, release_root)

    assert copied is False
    generated_payload = json.loads((release_root / build_green_release.PREVIEW_COLUMN_PREFERENCES_RELATIVE_PATH).read_text(encoding="utf-8"))
    assert generated_payload["preferences"]["defaultLabels"][0] == "要素1"
    assert generated_payload["preferences"]["maxDisplayChars"] == 8
    assert generated_payload["preferences"]["headerRows"] == {}
