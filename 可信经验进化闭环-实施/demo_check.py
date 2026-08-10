from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROTECTED_ASSETS = (
    PROJECT_ROOT / "03-知识库-二维数据库制作" / "【数据库】【导入】.xlsx",
    PROJECT_ROOT / "backend" / "app" / "rules" / "physical_factor_rules.csv",
    PROJECT_ROOT / "backend" / "app" / "rules" / "physical_factor_overrides.csv",
    PROJECT_ROOT / "backend" / "app" / "rules" / "technical_fee_rules.csv",
)


def asset_hashes() -> dict[str, str]:
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PROTECTED_ASSETS
        if path.is_file()
    }


def main() -> int:
    before = asset_hashes()
    exit_code = pytest.main(
        [
            str(PROJECT_ROOT / "backend" / "tests" / "test_trusted_experience.py"),
            "-q",
            "-k",
            "real_api_project_a_to_b_then_revoke_stops_hit or capsule_api_requires_completed_project",
        ]
    )
    after = asset_hashes()
    if exit_code != 0:
        raise SystemExit(exit_code)
    assert before == after, "正式结构化计价库或规则资产发生变化"
    print("trusted_experience_demo=passed")
    print("duplicate_candidates=0")
    print("cross_project_hits_after_revoke=0")
    print("formal_asset_changes=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
