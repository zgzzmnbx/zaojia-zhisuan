from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)
ALLOWED_STATUSES = {"active", "beta", "planned", "disabled"}
TASK_ENABLED_STATUSES = {"active"}
REQUIRED_FIELDS = {
    "id",
    "displayName",
    "version",
    "status",
    "domain",
    "description",
    "inputProfile",
    "capabilities",
    "assets",
    "validation",
}
PROHIBITED_KEYS = {
    "script",
    "scripts",
    "command",
    "commands",
    "executable",
    "entrypoint",
    "module",
    "pythonmodule",
    "shell",
}
SECRET_KEYS = {
    "apikey",
    "appsecret",
    "password",
    "secret",
    "token",
    "accesstoken",
    "refreshtoken",
}
EXECUTABLE_SUFFIXES = {".bat", ".cmd", ".com", ".exe", ".ps1", ".py", ".sh"}
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
SKILL_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ASSET_LABELS = {
    "knowledgeBase": "结构化计价库",
    "reportTemplate": "Word 报告模板",
    "ruleDocuments": "核心规则说明",
    "ruleWorkbooks": "结构化规则表",
    "validationSample": "回归验证样例",
}


class ProfessionalSkillError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class ProfessionalSkillRegistry:
    def __init__(
        self,
        project_root: Path,
        skills_root: Path,
        settings_path: Path,
        *,
        fallback_default_skill_id: str = "survey-measurement-limit-price",
    ) -> None:
        self.project_root = project_root.resolve()
        self.skills_root = skills_root.resolve()
        self.settings_path = settings_path
        self.fallback_default_skill_id = fallback_default_skill_id

    def default_skill_id(self) -> str:
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        section = payload.get("professionalSkills", {}) if isinstance(payload, dict) else {}
        configured = str(section.get("defaultSkillId") or "").strip() if isinstance(section, dict) else ""
        return configured or self.fallback_default_skill_id

    def list_public(self) -> dict[str, object]:
        manifests = self._load_all()
        default_id = self.default_skill_id()
        return {
            "default_skill_id": default_id,
            "items": [self.public_summary(manifest, default_id=default_id) for manifest in manifests],
        }

    def get_public(self, skill_id: str) -> dict[str, object]:
        manifest = self.load(skill_id)
        return self.public_detail(manifest, default_id=self.default_skill_id())

    def load(self, skill_id: str) -> dict[str, Any]:
        clean_id = str(skill_id or "").strip()
        if not SKILL_ID_PATTERN.fullmatch(clean_id):
            raise ProfessionalSkillError("skill_not_found", "未找到指定的专业能力", status_code=404)
        manifest_path = self.skills_root / clean_id / "manifest.json"
        if not manifest_path.is_file():
            raise ProfessionalSkillError("skill_not_found", "未找到指定的专业能力", status_code=404)
        return self._load_manifest(manifest_path)

    def resolve_for_task(self, skill_id: str | None, skill_version: str | None) -> dict[str, object]:
        explicit = bool(str(skill_id or "").strip() or str(skill_version or "").strip())
        resolved_id = str(skill_id or "").strip() or self.default_skill_id()
        try:
            manifest = self.load(resolved_id)
        except ProfessionalSkillError:
            if explicit:
                raise
            LOGGER.warning("默认专业能力 Manifest 不可用，启用勘察测量安全兼容快照")
            return self._compatibility_snapshot(resolved_id)

        status = str(manifest["status"])
        if status not in TASK_ENABLED_STATUSES:
            label = {"planned": "规划中", "beta": "内测中", "disabled": "已停用"}.get(status, "不可用")
            raise ProfessionalSkillError(
                "skill_not_available",
                f"专业能力“{manifest['displayName']}”当前为{label}，不能创建真实任务",
                status_code=409,
            )
        requested_version = str(skill_version or "").strip()
        if requested_version and requested_version != manifest["version"]:
            raise ProfessionalSkillError(
                "skill_version_mismatch",
                "专业能力版本已更新，请刷新能力清单后重试",
                status_code=409,
            )
        return self.create_snapshot(manifest)

    def create_snapshot(self, manifest: dict[str, Any]) -> dict[str, object]:
        return {
            "id": manifest["id"],
            "display_name": manifest["displayName"],
            "version": manifest["version"],
            "manifest_hash": manifest["_manifest_hash"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "asset_ids": sorted(manifest["assets"].keys()),
            "compatibility_fallback": False,
        }

    @staticmethod
    def public_snapshot(snapshot: object) -> dict[str, object]:
        if not isinstance(snapshot, dict):
            return {}
        return {
            "id": str(snapshot.get("id") or ""),
            "display_name": str(snapshot.get("display_name") or ""),
            "version": str(snapshot.get("version") or ""),
            "manifest_hash": str(snapshot.get("manifest_hash") or ""),
            "created_at": str(snapshot.get("created_at") or ""),
            "compatibility_fallback": bool(snapshot.get("compatibility_fallback", False)),
        }

    def public_summary(self, manifest: dict[str, Any], *, default_id: str) -> dict[str, object]:
        status = str(manifest["status"])
        return {
            "id": manifest["id"],
            "display_name": manifest["displayName"],
            "version": manifest["version"],
            "status": status,
            "status_label": {"active": "已上线", "beta": "内测中", "planned": "规划中", "disabled": "已停用"}[status],
            "domain": manifest["domain"],
            "description": manifest["description"],
            "capabilities": self._capability_names(manifest["capabilities"]),
            "asset_count": self._asset_count(manifest["assets"]),
            "validation_status": str(manifest["validation"].get("status") or "unverified"),
            "is_default": manifest["id"] == default_id,
            "can_create_task": status in TASK_ENABLED_STATUSES,
        }

    def public_detail(self, manifest: dict[str, Any], *, default_id: str) -> dict[str, object]:
        summary = self.public_summary(manifest, default_id=default_id)
        return {
            **summary,
            "input_profile": manifest["inputProfile"],
            "applicability": manifest.get("applicability", {}),
            "asset_summary": self._asset_summary(manifest["assets"]),
            "validation": manifest["validation"],
            "boundary": "规则裁决、模型解释、人工兜底；专业能力说明不得覆盖结构化计价规则。",
        }

    def _load_all(self) -> list[dict[str, Any]]:
        if not self.skills_root.is_dir():
            raise ProfessionalSkillError("skill_registry_unavailable", "专业能力清单暂不可用", status_code=503)
        manifests = [self._load_manifest(path) for path in sorted(self.skills_root.glob("*/manifest.json"))]
        if not manifests:
            raise ProfessionalSkillError("skill_registry_empty", "当前没有可展示的专业能力", status_code=503)
        ids = [str(item["id"]) for item in manifests]
        if len(ids) != len(set(ids)):
            raise ProfessionalSkillError("skill_manifest_invalid", "专业能力清单存在重复标识", status_code=503)
        return sorted(manifests, key=lambda item: (item["status"] != "active", item["displayName"]))

    def _load_manifest(self, manifest_path: Path) -> dict[str, Any]:
        try:
            raw_text = manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(raw_text)
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfessionalSkillError("skill_manifest_invalid", "专业能力清单格式无效", status_code=503) from exc
        if not isinstance(manifest, dict):
            raise ProfessionalSkillError("skill_manifest_invalid", "专业能力清单必须是对象", status_code=503)
        missing = sorted(REQUIRED_FIELDS - manifest.keys())
        if missing:
            raise ProfessionalSkillError("skill_manifest_invalid", f"专业能力清单缺少字段：{', '.join(missing)}", status_code=503)
        self._validate_metadata(manifest, manifest_path)
        self._reject_unsafe_entries(manifest)
        self._validate_assets(manifest)
        canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {**manifest, "_manifest_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}

    def _validate_metadata(self, manifest: dict[str, Any], manifest_path: Path) -> None:
        skill_id = str(manifest.get("id") or "").strip()
        if not SKILL_ID_PATTERN.fullmatch(skill_id) or manifest_path.parent.name != skill_id:
            raise ProfessionalSkillError("skill_manifest_invalid", "专业能力 ID 与目录不一致", status_code=503)
        if not str(manifest.get("displayName") or "").strip():
            raise ProfessionalSkillError("skill_manifest_invalid", "专业能力名称不能为空", status_code=503)
        if not SEMVER_PATTERN.fullmatch(str(manifest.get("version") or "")):
            raise ProfessionalSkillError("skill_manifest_invalid", "专业能力版本必须使用 x.y.z", status_code=503)
        if manifest.get("status") not in ALLOWED_STATUSES:
            raise ProfessionalSkillError("skill_manifest_invalid", "专业能力状态无效", status_code=503)
        for field in ("inputProfile", "capabilities", "assets", "validation"):
            if not isinstance(manifest.get(field), dict):
                raise ProfessionalSkillError("skill_manifest_invalid", f"专业能力字段 {field} 必须是对象", status_code=503)

    def _reject_unsafe_entries(self, value: object, *, key: str = "") -> None:
        normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
        if normalized_key in PROHIBITED_KEYS:
            raise ProfessionalSkillError("skill_manifest_unsafe", "专业能力清单不得声明脚本或可执行入口", status_code=503)
        if normalized_key in SECRET_KEYS:
            raise ProfessionalSkillError("skill_manifest_unsafe", "专业能力清单不得保存运行秘密", status_code=503)
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                self._reject_unsafe_entries(child_value, key=str(child_key))
        elif isinstance(value, list):
            for child_value in value:
                self._reject_unsafe_entries(child_value, key=key)

    def _validate_assets(self, manifest: dict[str, Any]) -> None:
        assets = manifest["assets"]
        if manifest["status"] in {"active", "beta"} and not assets:
            raise ProfessionalSkillError("skill_manifest_invalid", "上线专业能力必须声明资产", status_code=503)
        for value in assets.values():
            paths = value if isinstance(value, list) else [value]
            if not paths or any(not isinstance(path, str) or not path.strip() for path in paths):
                raise ProfessionalSkillError("skill_manifest_invalid", "专业能力资产引用格式无效", status_code=503)
            for path_text in paths:
                self._validate_asset_path(path_text)

    def _validate_asset_path(self, path_text: str) -> None:
        relative = Path(path_text)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() in EXECUTABLE_SUFFIXES:
            raise ProfessionalSkillError("skill_asset_unsafe", "专业能力资产引用不安全", status_code=503)
        try:
            resolved = (self.project_root / relative).resolve(strict=True)
            resolved.relative_to(self.project_root)
        except (OSError, ValueError) as exc:
            raise ProfessionalSkillError("skill_asset_unavailable", "专业能力所需资产缺失或超出允许范围", status_code=503) from exc

    @staticmethod
    def _asset_count(assets: dict[str, object]) -> int:
        return sum(len(value) if isinstance(value, list) else 1 for value in assets.values())

    @staticmethod
    def _capability_names(capabilities: dict[str, object]) -> list[str]:
        labels = {
            "pricing": "三数字匹配",
            "workloadCapture": "工作量抓取",
            "experienceWarning": "经验池预警",
            "knowledgeQa": "知识库问答",
            "knowledgeMemory": "知识记忆",
            "wordReport": "Word 报告",
            "collaboration": "智能协同",
        }
        return [labels.get(key, key) for key, enabled in capabilities.items() if enabled]

    @staticmethod
    def _asset_summary(assets: dict[str, object]) -> list[dict[str, object]]:
        return [
            {
                "id": key,
                "name": ASSET_LABELS.get(key, key),
                "count": len(value) if isinstance(value, list) else 1,
            }
            for key, value in assets.items()
        ]

    @staticmethod
    def _compatibility_snapshot(skill_id: str) -> dict[str, object]:
        return {
            "id": skill_id,
            "display_name": "勘察测量最高投标限价编制",
            "version": "compatibility",
            "manifest_hash": "compatibility-default-survey-measurement",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "asset_ids": [],
            "compatibility_fallback": True,
        }
