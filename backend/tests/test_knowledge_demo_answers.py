from app.knowledge_demo_answers import (
    DEMO_QUESTION_BRIDGE_CHART,
    DEMO_QUESTION_COST_CODES,
    DEMO_QUESTION_ROUTE_MAP_PRICE,
    DEMO_QUESTION_TECHNICAL_FEE,
    demo_questions,
    get_demo_answer,
)


def test_demo_questions_keep_the_required_front_page_order():
    assert demo_questions() == (
        DEMO_QUESTION_TECHNICAL_FEE,
        DEMO_QUESTION_ROUTE_MAP_PRICE,
        DEMO_QUESTION_COST_CODES,
        DEMO_QUESTION_BRIDGE_CHART,
    )


def test_demo_question_matching_allows_only_punctuation_and_spacing_changes():
    assert get_demo_answer("勘察测量: 技术工作费调整系数如何确定?") is not None
    assert get_demo_answer("勘察测量，实物工作费调整系数如何确定？") is None


def test_demo_code_answer_is_the_requested_markdown_table_only():
    answer = get_demo_answer(DEMO_QUESTION_COST_CODES)

    assert answer is not None
    assert answer["answer"].startswith("| 管径 | 单位 | 清单单价 | 来源定位 |")
    assert "D1016" in answer["answer"]
    assert "2,250元" in answer["answer"]
    assert answer["chart"] is None
