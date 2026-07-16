from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .paths import DEFAULT_KNOWLEDGE_QA_INDEX_PATH, PROJECT_ROOT


NO_EVIDENCE_ANSWER = "当前知识库未找到明确依据，需要人工复核。"
DEFAULT_INDEX_PATH = DEFAULT_KNOWLEDGE_QA_INDEX_PATH
FORCE_KNOWLEDGE_PREFIXES = ("查库：", "查库:", "@知识库", "#知识库")
KNOWLEDGE_INDEX_VERSION = "2026-06-30-fuzzy-price-candidates-v1"

COMMON_STOP_TERMS = {
    "什么",
    "什么意思",
    "为什么",
    "哪里来的",
    "哪来的",
    "依据",
    "标准",
    "解释",
    "来源",
    "出处",
    "这个",
    "这一行",
    "本行",
    "一般",
    "多少",
    "多少钱",
}

SYNONYM_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("0.22", "22%", "技术工作费"), ("0.22", "22%", "技术工作费", "工程测量技术工作费", "收费比例")),
    (("0.6", "60%"), ("0.6", "60%", "附加调整系数", "实物工作费调整系数", "不造标")),
    (("1.3", "130%"), ("1.3", "130%", "附加调整系数", "实物工作费调整系数")),
    (("1.5", "150%"), ("1.5", "150%", "附加调整系数", "实物工作费调整系数")),
    (
        ("实物工作费", "实物工作系数", "实物工作费系数", "实物系数", "工作费系数", "附加调整系数"),
        ("实物工作费", "实物工作费调整系数", "附加调整系数", "工程勘察", "工程测量"),
    ),
    (("技术工作费", "技术系数"), ("技术工作费", "技术工作费调整系数", "工程测量技术工作费", "收费比例")),
    (("不能连乘", "连乘", "相乘"), ("不能连乘", "连乘", "附加调整系数", "总则", "1.0.8", "相加")),
    (("第二层", "经验提示", "标黄", "黄色"), ("第二层", "经验提示", "经验数", "标黄", "黄色")),
    (("待复核", "标红", "红色"), ("待复核", "标红", "红色", "未命中", "人工复核")),
    (("预警", "经验池"), ("预警", "经验池预警", "偏离率", "阈值", "同类记录")),
    (("风险报告", "审查摘要", "输出风险报告", "生成风险报告"), ("风险报告", "审查摘要", "Word报告", "知识库依据", "处理结论", "主要风险", "复核建议")),
    (("问问智算", "智算模式", "@知识库", "查库", "强制知识库"), ("问问智算", "强制知识库", "快捷指令", "自动知识库问答", "普通自由问答", "行级AI复核", "风险报告")),
    (("导出", "下载", "输出excel", "输出word"), ("导出", "下载", "Excel", "Word", "原始输出", "大模型", "结构化规则引擎")),
    (("行级AI", "行级复核", "当前行复核"), ("行级AI复核", "当前行上下文", "匹配状态", "匹配说明", "预警参数", "预警细节")),
    (("地形测量", "地形图测绘"), ("地形测量", "地形图测绘", "地形图测绘(地形测量)")),
    (("首级控制", "首级控制测量"), ("首级控制", "首级控制测量", "控制测量")),
    (("GPS E级", "GPS测量E级"), ("GPS测量E级", "GPS测量", "E级")),
)

KNOWN_PHRASES = tuple(
    sorted(
        {
            term
            for triggers, expansions in SYNONYM_RULES
            for term in (*triggers, *expansions)
        }
        | {
            "基价",
            "单价",
            "要素1",
            "要素2",
            "要素3",
            "要素4",
            "要素5",
            "单位",
            "字段完全匹配",
            "非空要素顺序匹配",
            "技术工作费调整系数",
            "实物工作费调整系数",
        },
        key=len,
        reverse=True,
    )
)


@dataclass(frozen=True)
class KnowledgeChunk:
    id: str
    source_file: str
    source_type: str
    title_path: str
    content: str
    keywords: list[str]
    module: str
    created_at: str


@dataclass(frozen=True)
class KnowledgeSearchResult:
    id: str
    source_file: str
    source_type: str
    title_path: str
    snippet: str
    score: float
    module: str


def is_knowledge_question(question: str) -> bool:
    clean = _normalize_text(question)
    if not clean:
        return False
    triggers = (
        "哪里来的",
        "哪来的",
        "依据",
        "标准",
        "为什么",
        "什么意思",
        "解释",
        "来源",
        "出处",
        "0.22",
        "22%",
        "0.6",
        "1.3",
        "1.5",
        "技术工作费",
        "实物工作费",
        "实物工作系数",
        "实物工作费系数",
        "实物系数",
        "附加调整系数",
        "经验提示",
        "第二层",
        "待复核",
        "预警",
        "不能连乘",
        "风险报告",
        "审查摘要",
        "问问智算",
        "强制知识库",
        "行级ai",
        "行级复核",
    )
    return any(trigger in clean for trigger in triggers)


def strip_force_knowledge_prefix(question: str) -> tuple[str, bool]:
    clean_question = str(question or "").strip()
    for prefix in FORCE_KNOWLEDGE_PREFIXES:
        if clean_question.startswith(prefix):
            stripped = clean_question[len(prefix) :].lstrip(" \t\r\n:：,，.。;；")
            return stripped, True
    return clean_question, False


def search_knowledge(
    question: str,
    row_context: dict[str, Any] | None = None,
    limit: int = 8,
    *,
    project_root: Path = PROJECT_ROOT,
    index_path: Path | None = DEFAULT_INDEX_PATH,
) -> list[KnowledgeSearchResult]:
    clean_question = question.strip()
    if not clean_question:
        return []
    chunks = load_or_build_index(project_root=project_root, index_path=index_path)
    query_terms = _expand_query_terms(clean_question, row_context)
    if not query_terms:
        return []
    scored: list[tuple[float, KnowledgeChunk]] = []
    for chunk in chunks:
        score = _score_chunk(chunk, query_terms)
        if score >= 3:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    results: list[KnowledgeSearchResult] = []
    for score, chunk in scored[: max(1, min(limit, 20))]:
        results.append(
            KnowledgeSearchResult(
                id=chunk.id,
                source_file=chunk.source_file,
                source_type=chunk.source_type,
                title_path=chunk.title_path,
                snippet=_build_snippet(chunk.content, query_terms),
                score=round(score, 3),
                module=chunk.module,
            )
        )
    return results


def build_knowledge_answer_prompt(
    question: str,
    results: list[KnowledgeSearchResult],
    row_context: dict[str, Any] | None = None,
    project_memories: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    evidence_blocks = []
    for index, result in enumerate(results, start=1):
        evidence_blocks.append(
            "\n".join(
                [
                    f"资料{index}：",
                    f"来源文件：{result.source_file}",
                    f"来源类型：{result.source_type}",
                    f"标题路径：{result.title_path or '未标注'}",
                    f"正文片段：{result.snippet}",
                ]
            )
        )
    memory_blocks = []
    for index, memory in enumerate(project_memories or [], start=1):
        memory_blocks.append(
            "\n".join(
                [
                    f"项目记忆{index}：",
                    f"所属项目：{memory.get('project_name') or memory.get('project_key')}",
                    f"标题：{memory.get('title')}",
                    f"确认结论：{memory.get('conclusion')}",
                    f"适用条件：{memory.get('conditions') or '未填写'}",
                    f"例外情况：{memory.get('exceptions') or '未填写'}",
                    f"来源：{memory.get('source_reference')}",
                    f"确认人：{memory.get('confirmer')}",
                    f"确认时间：{memory.get('confirmed_at')}",
                ]
            )
        )
    row_context_text = (
        json.dumps(row_context, ensure_ascii=False, indent=2)
        if row_context
        else "未提供当前行上下文。"
    )
    user_content = "\n\n".join(
        [
            "【用户问题】",
            question.strip(),
            "【当前行上下文】",
            row_context_text,
            "【正式知识与规则依据】",
            "\n\n".join(evidence_blocks) or "未检索到正式知识与规则依据。",
            "【当前项目已确认知识记忆】",
            "\n\n".join(memory_blocks) or "未检索到当前项目已确认知识记忆。",
            "请用以下结构回答：",
            "智算解释：",
            "正式依据：",
            "项目记忆：",
            "提示：本回答只解释依据，不改变程序填价结果。",
            "项目记忆补充要求：",
            "1. 正式标准、正式规则和结构化计价库始终优先于项目记忆。",
            "2. 引用项目记忆时必须明确写“项目记忆”，并说明所属项目、确认人、确认时间、适用条件和来源。",
            "3. 项目口径不得表述成国家、行业或企业正式标准。",
            "4. 正式依据与项目记忆同时命中不等于冲突；无法确定冲突时只分区展示并提示人工复核。",
            "价格类问题补充要求：",
            "1. 如果检索资料中有来自 `03-知识库-二维数据库制作/【数据库】【导入】.xlsx` 的明确候选行，优先说明该行的序号、要素1-5、单位、基价和两个调整系数。",
            "2. 如果用户条件不足以唯一确定，但检索资料中有多个相似结构化计价库候选，不要直接说未找到依据；请列出 3-5 个候选项，并提示用户补充复杂程度、单位、比例尺或场景。",
            "3. 只有在没有结构化计价库候选且没有标准资料依据时，才回答当前知识库未找到明确依据，需要人工复核。",
        ]
    )
    return [
        {
            "role": "system",
            "content": (
                "你是造价智算的依据解释助手。你只能基于【已检索资料】和【当前行上下文】回答。"
                "本次【已检索资料】由【正式知识与规则依据】和【当前项目已确认知识记忆】分区组成。"
                "不得编造标准依据。不得直接裁决基价、实物工作费调整系数、技术工作费调整系数。"
                "不得覆盖结构化规则引擎的结果。如果资料不足，必须明确回答“当前知识库未找到明确依据，需要人工复核”。"
                "正式依据优先于项目记忆；项目记忆必须显式标注，不能伪装成正式标准。"
                "你的任务是把检索到的依据解释给业务人员听，并列出来源。"
            ),
        },
        {"role": "user", "content": user_content},
    ]


def load_or_build_index(
    *,
    project_root: Path = PROJECT_ROOT,
    index_path: Path | None = DEFAULT_INDEX_PATH,
) -> list[KnowledgeChunk]:
    sources = _discover_sources(project_root)
    source_signature = _source_signature(sources, project_root)
    if index_path and index_path.exists():
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            if payload.get("source_signature") == source_signature:
                return [KnowledgeChunk(**item) for item in payload.get("chunks", [])]
        except (OSError, TypeError, ValueError):
            pass

    chunks = build_index(project_root=project_root, sources=sources)
    if index_path:
        try:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(
                json.dumps(
                    {
                        "built_at": datetime.now().isoformat(timespec="seconds"),
                        "source_signature": source_signature,
                        "chunks": [asdict(chunk) for chunk in chunks],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
    return chunks


def build_index(project_root: Path = PROJECT_ROOT, sources: list[Path] | None = None) -> list[KnowledgeChunk]:
    source_paths = sources if sources is not None else _discover_sources(project_root)
    chunks: list[KnowledgeChunk] = []
    for path in source_paths:
        suffix = path.suffix.lower()
        if suffix == ".md":
            chunks.extend(_chunks_from_markdown(path, project_root))
        elif suffix == ".xlsx":
            chunks.extend(_chunks_from_workbook(path, project_root))
        elif suffix == ".csv":
            chunks.extend(_chunks_from_csv(path, project_root))
    return chunks


def _discover_sources(project_root: Path) -> list[Path]:
    rule_root = project_root / "03-【匹配规则】-勘察测绘知识库-匹配规则提炼"
    data_root = project_root / "03-知识库-二维数据库制作"
    original_root = rule_root / "01-原始资料"
    qa_root = rule_root / "90-【知识库】勘察测绘大模型问答知识库"
    candidates: list[Path] = [
        project_root / "README.md",
        project_root / "AGENTS.md",
        project_root / "CHANGELOG.md",
        project_root / "README.md",
        project_root / "00-PRD" / "00-产品总览.md",
        rule_root / "【重要匹配规则】项目以及总体匹配规则介绍.md",
        rule_root / "【重要匹配规则】要素1-5和单位的匹配模式介绍.md",
        rule_root / "【重要匹配规则】【第一层】-标准规则命中表-说人话版-v1.0.xlsx",
        data_root / "【数据库】【导入】.xlsx",
        project_root / "backend" / "app" / "rules" / "technical_fee_rules.xlsx",
        project_root / "backend" / "app" / "rules" / "technical_fee_rules.csv",
        project_root / "backend" / "app" / "rules" / "physical_factor_rules.xlsx",
        project_root / "backend" / "app" / "rules" / "physical_factor_rules.csv",
        project_root / "backend" / "app" / "rules" / "physical_factor_overrides.xlsx",
        project_root / "backend" / "app" / "rules" / "physical_factor_overrides.csv",
    ]
    for pattern in (
        "03-给深度研究的提示词和交付/20260614-深度研究【交付】*.md",
    ):
        candidates.extend(rule_root.glob(pattern))
    if original_root.exists():
        candidates.extend(
            path
            for path in original_root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".xlsx", ".csv"}
        )
    if qa_root.exists():
        candidates.extend(qa_root.rglob("*.md"))
    existing = []
    seen = set()
    for path in candidates:
        resolved = path.resolve()
        if path.exists() and not path.name.startswith("~$") and resolved not in seen:
            existing.append(path)
            seen.add(resolved)
    return existing


def _chunks_from_markdown(path: Path, project_root: Path) -> list[KnowledgeChunk]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    sections: list[tuple[str, str]] = []
    heading_stack: list[str] = []
    buffer: list[str] = []
    current_title = path.stem
    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            if buffer:
                sections.append((current_title, "\n".join(buffer).strip()))
                buffer = []
            level = len(match.group(1))
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(match.group(2).strip())
            current_title = " / ".join(heading_stack)
            buffer.append(line)
        else:
            buffer.append(line)
    if buffer:
        sections.append((current_title, "\n".join(buffer).strip()))

    chunks: list[KnowledgeChunk] = []
    for section_index, (title_path, content) in enumerate(sections, start=1):
        for part_index, part in enumerate(_split_long_text(content), start=1):
            chunks.append(_make_chunk(path, project_root, f"md-{section_index}-{part_index}", title_path, part))
    return chunks


def _chunks_from_workbook(path: Path, project_root: Path) -> list[KnowledgeChunk]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    chunks: list[KnowledgeChunk] = []
    try:
        for sheet in workbook.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue
            headers = [_cell_text(value) or f"列{index}" for index, value in enumerate(rows[0], start=1)]
            for row_index, row in enumerate(rows[1:], start=2):
                values = [_cell_text(value) for value in row]
                if not any(values):
                    continue
                pairs = [
                    f"{headers[index]}：{value}"
                    for index, value in enumerate(values[: len(headers)])
                    if value
                ]
                if not pairs:
                    continue
                title_path = f"{sheet.title} / 第{row_index}行规则卡片"
                content = "\n".join(
                    [
                        f"来源表：{sheet.title}",
                        f"Excel 行号：{row_index}",
                        *pairs,
                    ]
                )
                chunks.append(_make_chunk(path, project_root, f"xlsx-{sheet.title}-{row_index}", title_path, content))
    finally:
        workbook.close()
    return chunks


def _chunks_from_csv(path: Path, project_root: Path) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row_index, row in enumerate(reader, start=2):
            pairs = [f"{key}：{value}" for key, value in row.items() if key and str(value or "").strip()]
            if not pairs:
                continue
            title_path = f"{path.stem} / 第{row_index}行规则卡片"
            content = "\n".join([f"来源表：{path.name}", f"CSV 行号：{row_index}", *pairs])
            chunks.append(_make_chunk(path, project_root, f"csv-{row_index}", title_path, content))
    return chunks


def _make_chunk(path: Path, project_root: Path, suffix: str, title_path: str, content: str) -> KnowledgeChunk:
    rel = _relative_path(path, project_root)
    keywords = _keywords_for_text(" ".join([path.name, title_path, content]))
    return KnowledgeChunk(
        id=f"{rel}::{suffix}",
        source_file=rel,
        source_type=_source_type(path),
        title_path=title_path,
        content=content,
        keywords=keywords,
        module=_module_for_text(" ".join([path.name, title_path, content])),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )


def _source_type(path: Path) -> str:
    text = str(path)
    name = path.name
    if "01-原始资料" in text or "财建[2009]17号" in name or "计价格[2002]10号" in name:
        return "standard"
    if "backend" in text and "rules" in text:
        return "rule_card"
    if path.suffix.lower() in {".xlsx", ".csv"}:
        return "rule_card"
    return "project_rule"


def _module_for_text(text: str) -> str:
    clean = _normalize_text(text)
    if "问问智算" in clean or "大模型" in clean or "@知识库" in clean or "强制知识库" in clean:
        return "问问智算"
    if "不能连乘" in clean or "实物工作费" in clean or "实物工作系数" in clean or "附加调整系数" in clean:
        return "实物工作费调整系数"
    if "技术工作费" in clean:
        return "技术工作费调整系数"
    if "经验池" in clean or "预警" in clean:
        return "经验池预警"
    if "工作量" in clean:
        return "原始工作量抓取"
    if "要素1" in clean and "要素5" in clean and "单位" in clean and "匹配" in clean:
        return "要素匹配"
    if "基价" in clean or "单价" in clean:
        return "基价匹配"
    if "word" in clean or "报告" in clean:
        return "Word报告"
    return "通用概念"


def _expand_query_terms(question: str, row_context: dict[str, Any] | None) -> dict[str, float]:
    clean = _normalize_text(question)
    terms: dict[str, float] = {}
    for triggers, expansions in SYNONYM_RULES:
        if any(_normalize_text(trigger) in clean for trigger in triggers):
            for expansion in expansions:
                _add_term(terms, expansion, 3.0)
    for phrase in KNOWN_PHRASES:
        if _normalize_text(phrase) in clean:
            _add_term(terms, phrase, 2.0)
    price_markers = ("多少钱", "多少", "单价", "基价", "价格")
    fee_domain_markers = ("工程", "勘察", "测量", "控制", "地形", "gps", "隧道", "管线", "水域", "单位", "要素")
    if any(marker in clean for marker in price_markers) or (
        "收费" in clean and any(marker in clean for marker in fee_domain_markers)
    ):
        _add_term(terms, "基价", 2.8)
        _add_term(terms, "单价", 2.6)
        _add_term(terms, "价格", 2.4)
    for level in ("简单", "中等", "复杂"):
        if level in clean:
            _add_term(terms, level, 2.5)
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9.%:\-]+", question):
        clean_token = _normalize_text(token)
        if clean_token not in COMMON_STOP_TERMS and 2 <= len(clean_token) <= 20:
            _add_term(terms, token, 2.2)
        gps_match = re.search(r"(gps\s*测量\s*[a-z]\s*级)", token, flags=re.IGNORECASE)
        if gps_match:
            _add_term(terms, gps_match.group(1), 3.2)
            _add_term(terms, "GPS测量", 2.4)
            _add_term(terms, gps_match.group(1)[-2:], 2.4)
    for number in re.findall(r"\d+(?:\.\d+)?%?", clean):
        _add_term(terms, number, 2.5)
    for ratio in re.findall(r"\d+\s*:\s*\d+", question):
        compact_ratio = _normalize_text(ratio)
        _add_term(terms, compact_ratio, 3.5)
        _add_term(terms, f"比例-{compact_ratio}", 3.8)
    for raw in re.findall(r"[\u4e00-\u9fffA-Za-z0-9.%\-]{2,}", clean):
        if raw not in COMMON_STOP_TERMS and len(raw) <= 16:
            _add_term(terms, raw, 1.0)
    if row_context:
        for value in row_context.values():
            if isinstance(value, (str, int, float)) and str(value).strip():
                text = str(value).strip()
                if len(text) <= 30:
                    _add_term(terms, text, 1.5)
    return terms


def _score_chunk(chunk: KnowledgeChunk, terms: dict[str, float]) -> float:
    content = _normalize_text(chunk.content)
    title = _normalize_text(chunk.title_path)
    source = _normalize_text(chunk.source_file)
    keywords = {_normalize_text(keyword) for keyword in chunk.keywords}
    score = 0.0
    for term, weight in terms.items():
        clean_term = _normalize_text(term)
        if not clean_term:
            continue
        if clean_term in title:
            score += weight * 2.4
        if clean_term in source:
            score += weight * 1.6
        if clean_term in keywords:
            score += weight * 1.8
        occurrences = content.count(clean_term)
        if occurrences:
            score += weight * min(occurrences, 4)
    if "standard" == chunk.source_type:
        score *= 1.08
    score += _module_affinity_score(chunk.module, terms)
    score += _price_database_affinity_score(chunk, terms)
    return score


def _price_database_affinity_score(chunk: KnowledgeChunk, terms: dict[str, float]) -> float:
    if "03-知识库-二维数据库制作/【数据库】【导入】.xlsx" not in chunk.source_file:
        return 0.0
    clean_terms = {_normalize_text(term) for term in terms}
    price_question = any(term in clean_terms for term in {"单价", "基价", "价格"}) or any(
        term in clean_terms for term in {"多少", "多少钱"}
    )
    if not price_question:
        return 0.0
    content = _normalize_text(chunk.content)
    strong_terms = [
        term
        for term in clean_terms
        if len(term) >= 2
        and term not in COMMON_STOP_TERMS
        and term not in {"单价", "基价", "价格"}
        and term in content
    ]
    if len(strong_terms) < 2:
        return 0.0
    score = 14.0 + min(len(strong_terms), 8) * 5.0
    if any(term.startswith("比例-") and term in content for term in clean_terms):
        score += 12.0
    for level in ("简单", "中等", "复杂"):
        if level not in clean_terms:
            continue
        if f"要素4:{level}" in content or f"要素5:{level}" in content:
            score += 28.0
        elif any(f"要素4:{other}" in content or f"要素5:{other}" in content for other in ("简单", "中等", "复杂")):
            score -= 18.0
    return score


def _module_affinity_score(module: str, terms: dict[str, float]) -> float:
    clean_terms = {_normalize_text(term) for term in terms}
    module_targets = (
        ("实物工作费调整系数", ("实物工作费调整系数", "实物工作费", "实物工作系数", "实物系数", "附加调整系数")),
        ("技术工作费调整系数", ("技术工作费调整系数", "技术工作费", "技术系数", "0.22", "22%")),
        ("经验池预警", ("经验池预警", "经验池", "预警", "偏离率")),
        ("基价匹配", ("基价", "单价", "价格")),
        ("要素匹配", ("要素1", "要素5", "字段完全匹配", "非空要素顺序匹配")),
    )
    for target_module, markers in module_targets:
        if not any(_normalize_text(marker) in clean_terms for marker in markers):
            continue
        if module == target_module:
            return 8.0
        if module == "问问智算":
            return -4.0
    return 0.0


def _keywords_for_text(text: str) -> list[str]:
    clean = _normalize_text(text)
    keywords = [phrase for phrase in KNOWN_PHRASES if _normalize_text(phrase) in clean]
    keywords.extend(re.findall(r"\d+(?:\.\d+)?%?", clean))
    return sorted(set(keywords), key=lambda item: (len(item), item), reverse=True)[:30]


def _split_long_text(text: str, max_chars: int = 1500) -> list[str]:
    clean = text.strip()
    if len(clean) <= max_chars:
        return [clean] if clean else []
    paragraphs = re.split(r"\n\s*\n", clean)
    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and current_len + len(paragraph) > max_chars:
            parts.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(paragraph)
        current_len += len(paragraph)
    if current:
        parts.append("\n\n".join(current))
    return parts


def _build_snippet(content: str, terms: dict[str, float], max_chars: int = 520) -> str:
    clean = content.strip()
    normalized = _normalize_text(clean)
    first_hit = -1
    for term in terms:
        index = normalized.find(_normalize_text(term))
        if index >= 0:
            first_hit = index
            break
    if first_hit < 0 or len(clean) <= max_chars:
        return clean[:max_chars]
    start = max(0, first_hit - 120)
    return clean[start : start + max_chars]


def _source_signature(sources: list[Path], project_root: Path) -> list[dict[str, object]]:
    signature: list[dict[str, object]] = [{"index_version": KNOWLEDGE_INDEX_VERSION}]
    for path in sources:
        try:
            stat = path.stat()
        except OSError:
            continue
        signature.append(
            {
                "path": _relative_path(path, project_root),
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            }
        )
    return signature


def _relative_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("％", "%")
    text = text.replace("：", ":")
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    return text.lower()


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _add_term(terms: dict[str, float], term: str, weight: float) -> None:
    clean = _normalize_text(term)
    if not clean or clean in COMMON_STOP_TERMS:
        return
    terms[term] = max(terms.get(term, 0.0), weight)
