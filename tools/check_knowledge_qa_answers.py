from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = PROJECT_ROOT / "backend" / "tests" / "fixtures" / "knowledge_qa_regression_cases.json"


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _source_text(payload: dict[str, Any]) -> str:
    return "\n".join(
        " | ".join(
            str(source.get(key) or "")
            for key in ("source_file", "title_path", "snippet", "library_name")
        )
        for source in payload.get("sources", [])
    )


def _check_case(case: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    expected = case["expected"]
    answer = str(payload.get("answer") or "")
    errors: list[str] = []
    if bool(payload.get("evidence_found")) != bool(expected["evidenceFound"]):
        errors.append(f"evidence_found 应为 {expected['evidenceFound']}")
    if "presetAnswer" in expected and bool(payload.get("preset_answer")) != bool(expected["presetAnswer"]):
        errors.append(f"preset_answer 应为 {expected['presetAnswer']}")
    if "generatedByModel" in expected and bool(payload.get("generated_by_model")) != bool(expected["generatedByModel"]):
        errors.append(f"generated_by_model 应为 {expected['generatedByModel']}")
    if expected.get("answerMode") and payload.get("answer_mode") != expected["answerMode"]:
        errors.append(f"answer_mode 应为 {expected['answerMode']}")
    if expected.get("exactAnswer") and answer.strip() != expected["exactAnswer"]:
        errors.append("回答未命中固定标准答案")
    for phrase in expected.get("mustInclude", []):
        if phrase.lower() not in answer.lower():
            errors.append(f"回答缺少：{phrase}")
    for phrase in expected.get("mustNotInclude", []):
        if phrase.lower() in answer.lower():
            errors.append(f"回答不应包含：{phrase}")
    sources = _source_text(payload)
    for phrase in expected.get("sourceContains", []):
        if phrase.lower() not in sources.lower():
            errors.append(f"依据来源缺少：{phrase}")
    if "chartItemCount" in expected:
        chart_items = (payload.get("chart") or {}).get("items") or []
        if len(chart_items) != int(expected["chartItemCount"]):
            errors.append(f"图表数据项应为 {expected['chartItemCount']} 条")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="运行问问智算知识库标准答案回归。")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    data = json.loads(args.cases.read_text(encoding="utf-8"))
    selected = [
        case
        for case in data["cases"]
        if not args.case_ids or case["id"] in set(args.case_ids)
    ]
    if not selected:
        print("没有匹配的回归问题。", file=sys.stderr)
        return 2

    failures = 0
    endpoint = args.base_url.rstrip("/") + "/api/knowledge/ask"
    for case in selected:
        question = str(case["question"])
        if question.startswith("#知识库："):
            question = question[len("#知识库：") :]
        try:
            payload = _post_json(
                endpoint,
                {
                    "question": question,
                    "force_knowledge": True,
                    "library_ids": case["libraryIds"],
                    "limit": 8,
                },
                args.timeout,
            )
            errors = _check_case(case, payload)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors = [f"请求失败：{exc}"]
        if errors:
            failures += 1
            print(f"[FAIL] {case['id']} - {case['name']}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"[PASS] {case['id']} - {case['name']}")

    print(f"\n结果：{len(selected) - failures}/{len(selected)} 通过")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
