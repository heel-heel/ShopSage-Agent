from app.schemas import ChatRequest
from app.services.agent import parse_constraints


def test_explicit_request_constraints_are_preserved():
    constraints = parse_constraints(
        ChatRequest(question="想要低酸手冲咖啡豆", budget=100, brew_method="hand_drip", experience="beginner"),
        {},
    )
    assert constraints["budget"] == 100
    assert constraints["brew_method"] == "hand_drip"
    assert constraints["experience"] == "beginner"


def test_question_budget_is_detected():
    constraints = parse_constraints(ChatRequest(question="预算 300 元，手冲新手想买咖啡豆"), {})
    assert constraints["budget"] == 300
    assert constraints["brew_method"] == "hand_drip"
    assert constraints["category"] == "coffee_bean"
