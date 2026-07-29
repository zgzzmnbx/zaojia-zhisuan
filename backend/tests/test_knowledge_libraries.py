import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import main as main_module
from app.main import app
from app.knowledge_libraries import (
    knowledge_library_catalog,
    parse_requested_library_ids,
    resolve_knowledge_library_selection,
)
from app.knowledge_qa import (
    KnowledgeSearchResult,
    _build_snippet,
    build_knowledge_answer_prompt,
    search_knowledge,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.build_aiw_knowledge_assets import build_asset, discover_sources  # noqa: E402
from tools.build_green_release import copy_runtime_assets  # noqa: E402


def write_library_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "libraries": [
                    {
                        "id": "project-core",
                        "name": "项目正式知识库",
                        "kind": "static",
                        "sourceMode": "professional-skill",
                        "defaultSelected": True,
                    },
                    {
                        "id": "cost-aiw",
                        "name": "造价通用知识库",
                        "kind": "static",
                        "paths": ["assets/aiw"],
                        "recursive": True,
                        "extensions": [".md"],
                        "excludeNames": ["知识资产清单.md"],
                        "defaultSelected": True,
                    },
                    {
                        "id": "knowledge-memory",
                        "name": "已确认知识记忆",
                        "kind": "memory",
                        "defaultSelected": True,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_snippet_starts_near_the_most_specific_query_phrase():
    content = (
        "清单单价用于概算。"
        + "地区差异调整系数表。" * 40
        + "对于部分改建项目，考虑安装与生产同时进行条件下施工效率降低因素，"
        + "清单单价按5.7%比例计取安装与生产同时进行降效费。"
    )
    terms = {
        "基价": 2.8,
        "单价": 2.6,
        "安装与生产同时进行": 1.0,
        "安装与生产同时进行降效费按多少比例计取": 2.2,
    }

    snippet = _build_snippet(content, terms)

    assert "5.7%" in snippet
    assert "安装与生产同时进行" in snippet


def test_dictionary_lookup_prompt_requests_one_concise_markdown_table():
    messages = build_knowledge_answer_prompt(
        "工程费用5000万元时，建设单位管理费费率是多少？",
        [
            KnowledgeSearchResult(
                id="cost-1",
                source_file="2024其他费用.md",
                source_type="reference",
                title_path="建设单位管理费",
                snippet="工程费用5000万元，费率4%。",
                score=10,
                module="通用概念",
            )
        ],
    )

    user_prompt = messages[1]["content"]
    assert "只输出一个简洁的 Markdown 表格" in user_prompt
    assert "不要在表格外重复输出" in user_prompt


def test_library_selection_isolates_static_sources_and_memory(tmp_path):
    project_root = tmp_path / "project"
    core_source = project_root / "core.md"
    aiw_source = project_root / "assets" / "aiw" / "cost.md"
    inventory = aiw_source.parent / "知识资产清单.md"
    aiw_source.parent.mkdir(parents=True)
    core_source.write_text("# 正式知识\n\n正式依据", encoding="utf-8")
    aiw_source.write_text("# AIW\n\n造价依据", encoding="utf-8")
    inventory.write_text("# 清单", encoding="utf-8")
    config_path = write_library_config(project_root / "config" / "knowledge-qa-libraries.json")

    aiw_only = resolve_knowledge_library_selection(
        ("cost-aiw",),
        project_root=project_root,
        base_sources=(core_source,),
        base_index_path=tmp_path / "runtime" / "knowledge.json",
        config_path=config_path,
    )
    assert aiw_only.selected_ids == ("cost-aiw",)
    assert aiw_only.sources == (aiw_source,)
    assert aiw_only.memory_enabled is False
    assert aiw_only.library_for_source("assets/aiw/cost.md").id == "cost-aiw"

    memory_only = resolve_knowledge_library_selection(
        ("knowledge-memory",),
        project_root=project_root,
        base_sources=(core_source,),
        base_index_path=tmp_path / "runtime" / "knowledge.json",
        config_path=config_path,
    )
    assert memory_only.sources == ()
    assert memory_only.index_path is None
    assert memory_only.memory_enabled is True


def test_library_catalog_reports_available_sources(tmp_path):
    project_root = tmp_path / "project"
    core_source = project_root / "core.md"
    aiw_source = project_root / "assets" / "aiw" / "cost.md"
    aiw_source.parent.mkdir(parents=True)
    core_source.write_text("# 正式知识", encoding="utf-8")
    aiw_source.write_text("# AIW", encoding="utf-8")
    config_path = write_library_config(project_root / "config" / "knowledge-qa-libraries.json")

    payload = knowledge_library_catalog(
        project_root=project_root,
        base_sources=(core_source,),
        config_path=config_path,
    )

    by_id = {item["id"]: item for item in payload["libraries"]}
    assert by_id["project-core"]["source_count"] == 1
    assert by_id["cost-aiw"]["source_count"] == 1
    assert by_id["knowledge-memory"]["source_count"] is None
    assert payload["default_library_ids"] == [
        "project-core",
        "cost-aiw",
        "knowledge-memory",
    ]


def test_manifest_backed_library_ignores_stale_generated_markdown(tmp_path):
    project_root = tmp_path / "project"
    asset_dir = project_root / "assets" / "aiw"
    asset_dir.mkdir(parents=True)
    ready = asset_dir / "ready.md"
    stale = asset_dir / "stale.md"
    ready.write_text("# 当前资产", encoding="utf-8")
    stale.write_text("# 已失效资产", encoding="utf-8")
    (asset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "assets": [
                    {"output_name": ready.name, "status": "ready"},
                    {"output_name": "pending.md", "status": "pending_conversion"},
                ]
            }
        ),
        encoding="utf-8",
    )
    config_path = write_library_config(project_root / "config" / "knowledge-qa-libraries.json")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["libraries"][1]["manifestFile"] = "manifest.json"
    config_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    selection = resolve_knowledge_library_selection(
        ("cost-aiw",),
        project_root=project_root,
        base_sources=(),
        config_path=config_path,
    )

    assert selection.sources == (ready,)
    assert stale not in selection.sources


def test_general_chinese_question_retrieves_long_aiw_phrase(tmp_path):
    source = tmp_path / "06-知识库问答资料" / "造价AIW资料库" / "数字化.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 数字与信息化项目投资计价依据\n\n"
        "软件购置费包括购置应用软件、数据库和需额外购买的系统软件等费用。\n\n"
        "## 计算方法\n\n软件购置费通过指导价格、同类历史采购价和市场询价综合确定。",
        encoding="utf-8",
    )

    results = search_knowledge(
        "系统软件购置费如何计取？",
        project_root=tmp_path,
        index_path=None,
        sources=[source],
    )

    assert results
    assert results[0].source_type == "reference"
    assert any("软件购置费" in result.snippet for result in results)
    assert any("综合确定" in result.snippet for result in results)


def test_long_numeric_code_outranks_generic_price_headers(tmp_path):
    target = tmp_path / "target.md"
    decoy = tmp_path / "decoy.md"
    target.write_text(
        "# 第一章 土石方工程\n\n"
        "清单编码10101002，清单名称作业带扫线山区、丘陵，单位m²，"
        "清单单价1.66元，规费0.07元，安全生产费0.03元。",
        encoding="utf-8",
    )
    decoy.write_text(
        "# 2024年建设项目全费用工程量清单单价\n\n"
        "本资料包含清单编码、清单名称、单位、清单单价、规费、安全生产费和来源定位。",
        encoding="utf-8",
    )

    results = search_knowledge(
        "查清单编码10101002，只回答清单名称、单位、清单单价、规费、安全生产费和来源定位。",
        project_root=tmp_path,
        index_path=None,
        sources=[target, decoy],
    )

    assert results
    assert results[0].source_file == "target.md"
    assert "10101002" in results[0].snippet
    assert "1.66元" in results[0].snippet


def test_aiw_asset_builder_only_discovers_complete_filename_marker(tmp_path):
    source_root = tmp_path / "cost"
    source_root.mkdir()
    marked = source_root / "测试资料【AIW】.xlsx"
    unmarked = source_root / "测试资料.xlsx"
    for target in (marked, unmarked):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "费用表"
        worksheet.append(["费用名称", "费率"])
        worksheet.append(["系统软件购置费", 0.08])
        workbook.save(target)
        workbook.close()
    original_hash = marked.read_bytes()

    discovered = discover_sources(source_root)
    record, content = build_asset(
        marked,
        source_root,
        converted_dir=None,
        generated_at="2026-07-28T00:00:00+08:00",
    )

    assert discovered == [marked]
    assert record.status == "ready"
    assert AIW_MARKER_NOT_IN_OUTPUT(record.output_name)
    assert "Excel 第 2 行" in content
    assert "系统软件购置费" in content
    assert marked.read_bytes() == original_hash


def AIW_MARKER_NOT_IN_OUTPUT(output_name: str) -> bool:
    return "【AIW】" not in output_name


def test_requested_library_ids_require_an_array():
    try:
        parse_requested_library_ids("cost-aiw")
    except ValueError as exc:
        assert "数组" in str(exc)
    else:
        raise AssertionError("string library_ids should be rejected")


def test_green_release_carries_library_config_and_question_answer_assets(tmp_path):
    project_root = tmp_path / "project"
    release_root = tmp_path / "release"
    config = project_root / "config" / "knowledge-qa-libraries.json"
    asset = project_root / "06-知识库问答资料" / "造价AIW资料库" / "cost.md"
    config.parent.mkdir(parents=True)
    asset.parent.mkdir(parents=True)
    config.write_text('{"schemaVersion": 1, "libraries": []}', encoding="utf-8")
    asset.write_text("# 问答资产", encoding="utf-8")

    copy_runtime_assets(project_root, release_root)

    assert (release_root / config.relative_to(project_root)).read_text(encoding="utf-8") == config.read_text(encoding="utf-8")
    assert (release_root / asset.relative_to(project_root)).read_text(encoding="utf-8") == asset.read_text(encoding="utf-8")


def test_api_exposes_configured_knowledge_libraries():
    response = TestClient(app).get("/api/knowledge/libraries")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["libraries"]] == [
        "project-core",
        "cost-aiw",
        "knowledge-memory",
    ]
    assert payload["default_library_ids"] == [
        "project-core",
        "cost-aiw",
        "knowledge-memory",
    ]
    assert next(item for item in payload["libraries"] if item["id"] == "cost-aiw")["source_count"] >= 5


def test_api_can_disable_memory_and_only_search_selected_static_library(monkeypatch):
    captured = {}

    def fake_search(*args, **kwargs):
        captured["sources"] = kwargs["sources"]
        return []

    def forbidden_memory(*args, **kwargs):
        raise AssertionError("未选择知识记忆时不应读取记忆库")

    monkeypatch.setattr(main_module, "search_knowledge", fake_search)
    monkeypatch.setattr(main_module, "_safe_search_project_memories", forbidden_memory)
    response = TestClient(app).post(
        "/api/knowledge/search",
        json={
            "question": "数字与信息化项目投资计价依据",
            "library_ids": ["cost-aiw"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_library_ids"] == ["cost-aiw"]
    assert payload["memory_enabled"] is False
    assert captured["sources"]
    assert all("06-知识库问答资料" in str(path) for path in captured["sources"])


def test_api_memory_only_selection_skips_static_search(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "search_knowledge",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("只选知识记忆时不应构建静态索引")
        ),
    )
    monkeypatch.setattr(
        main_module,
        "_safe_search_project_memories",
        lambda *args, **kwargs: ([{"id": "KM-1", "title": "已确认记忆"}], True),
    )
    response = TestClient(app).post(
        "/api/knowledge/search",
        json={
            "question": "项目复核口径",
            "library_ids": ["knowledge-memory"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_library_ids"] == ["knowledge-memory"]
    assert payload["memory_enabled"] is True
    assert payload["results"] == []
    assert payload["project_memories"][0]["id"] == "KM-1"
