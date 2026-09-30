from __future__ import annotations

import re
from collections import Counter
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AgentRun, AgentStep, ConsumerProfile, Event, Product
from app.schemas import ChatRequest, Citation, DecisionResponse, Recommendation
from app.services.graph import decision_graph
from app.services.knowledge import knowledge_store
from app.services.model_gateway import enrich_explanation


BREW_ALIASES = {
    "手冲": "hand_drip",
    "手沖": "hand_drip",
    "滤杯": "filter",
    "意式": "espresso",
    "拿铁": "espresso",
    "摩卡": "moka_pot",
}
FLAVOR_ALIASES = {
    "果": "citrus",
    "酸": "citrus",
    "花": "floral",
    "莓": "berry",
    "巧克力": "chocolate",
    "可可": "chocolate",
    "坚果": "nutty",
    "低酸": "chocolate",
}
CATEGORY_ALIASES = {
    "咖啡豆": "coffee_bean",
    "豆子": "coffee_bean",
    "磨豆": "grinder",
    "滤杯": "dripper",
    "手冲壶": "kettle",
    "套装": "bundle",
}


def parse_constraints(request: ChatRequest, preferences: dict[str, Any]) -> dict[str, Any]:
    question = request.question.lower()
    budget = request.budget
    if budget is None:
        match = re.search(r"(?:预算|不超过|以内|元内)\s*(\d{2,4})", question)
        if match:
            budget = float(match.group(1))

    brew_method = request.brew_method or next((value for key, value in BREW_ALIASES.items() if key in question), None)
    flavor = request.flavor or next((value for key, value in FLAVOR_ALIASES.items() if key in question), None)
    experience = request.experience
    if not experience:
        experience = "beginner" if any(word in question for word in ["新手", "入门", "刚开始"]) else preferences.get("experience")
    category = next((value for key, value in CATEGORY_ALIASES.items() if key in question), None)
    return {
        "budget": budget or preferences.get("budget"),
        "brew_method": brew_method or preferences.get("brew_method"),
        "flavor": flavor or preferences.get("flavor"),
        "experience": experience,
        "category": category,
    }


def _catalog_filter(db: Session, constraints: dict[str, Any]) -> tuple[list[Product], list[str]]:
    products = list(db.scalars(select(Product)).all())
    unmet: list[str] = []
    if constraints["category"]:
        products = [product for product in products if product.category == constraints["category"]]
    if constraints["budget"]:
        products = [product for product in products if product.price <= constraints["budget"]]
        if not products:
            unmet.append(f"预算 {constraints['budget']:.0f} 元内没有满足其他条件的商品")
    if constraints["brew_method"]:
        products = [product for product in products if constraints["brew_method"] in product.brew_methods]
        if not products:
            unmet.append("现有目录没有同时满足指定冲煮方式的商品")
    return products, unmet


def _score(product: Product, question: str, constraints: dict[str, Any], preferences: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    source = f"{product.name} {product.summary} {' '.join(product.flavor_tags)}"
    score = 35
    reasons: list[str] = []
    tradeoffs: list[str] = []
    flavor = constraints.get("flavor")
    if flavor and flavor in product.flavor_tags:
        score += 25
        reasons.append(f"风味与您偏好的 {flavor} 方向一致")
    if constraints.get("brew_method") in product.brew_methods:
        score += 20
        reasons.append("支持您指定的冲煮方式")
    if constraints.get("budget") and product.price <= constraints["budget"]:
        score += 10
        reasons.append("价格在设定预算内")
    if constraints.get("experience") == product.level:
        score += 10
        reasons.append(f"适合 {product.level} 阶段使用")
    if preferences.get("saved_flavors") and set(product.flavor_tags) & set(preferences["saved_flavors"]):
        score += 8
        reasons.append("与您此前收藏的风味偏好相近")
    if product.price >= 500:
        tradeoffs.append("投入较高，更适合高频使用或已有明确需求的用户")
    if product.level == "intermediate":
        tradeoffs.append("需要更稳定的冲煮参数，入门时可能不如基础款省心")
    if product.category == "grinder" and "manual" in product.flavor_tags:
        tradeoffs.append("手动研磨需要时间与体力")
    if not reasons:
        reasons.append("商品与当前需求存在基础匹配，建议结合参数进一步比较")
    return min(score, 100), reasons, tradeoffs


def _citations(products: list[Product], retrieved: list[dict[str, Any]]) -> list[Citation]:
    result = []
    for product in products:
        result.append(Citation(
            id=f"product:{product.id}",
            title=product.name,
            excerpt=product.summary,
            source_url=product.source_url,
        ))
    for item in retrieved[:2]:
        result.append(Citation(id=f"knowledge:{item['id']}", title=item["title"], excerpt=item["text"], source_url=item["metadata"].get("source_url")))
    return result


def _record_step(db: Session, trace_id: str, name: str, input_data: dict, output_data: dict) -> None:
    db.add(AgentStep(trace_id=trace_id, step_name=name, input_data=input_data, output_data=output_data))


def run_decision_agent(db: Session, consumer_id: str, request: ChatRequest) -> DecisionResponse:
    trace_id = uuid4().hex
    # LangGraph supplies the stable orchestration order; each node's business output is recorded below.
    graph_state = decision_graph.invoke({"completed_nodes": []})
    profile = db.get(ConsumerProfile, consumer_id)
    preferences = profile.preferences if profile else {}
    constraints = parse_constraints(request, preferences)
    _record_step(db, trace_id, "intent_and_constraints", {"question": request.question}, constraints)
    _record_step(db, trace_id, "profile_analyzer", {"consumer_id": consumer_id}, {"labels": profile.labels if profile else ["new_visitor"], "preferences": preferences})

    retrieved = knowledge_store.query(request.question)
    _record_step(db, trace_id, "knowledge_retriever", {"query": request.question}, {"document_ids": [item["id"] for item in retrieved]})

    candidates, unmet = _catalog_filter(db, constraints)
    _record_step(db, trace_id, "catalog_filter", constraints, {"product_ids": [product.id for product in candidates], "unmet": unmet})

    ranked = []
    for product in candidates:
        score, reasons, tradeoffs = _score(product, request.question, constraints, preferences)
        ranked.append((score, product, reasons, tradeoffs))
    ranked.sort(key=lambda item: (item[0], item[1].rating), reverse=True)
    top = ranked[:3]
    _record_step(db, trace_id, "recommendation_ranker", constraints, {"ranked": [{"id": item[1].id, "score": item[0]} for item in top]})

    products = [item[1] for item in top]
    citations = _citations(products, retrieved)
    recommendations = [
        Recommendation(
            product_id=product.id,
            name=product.name,
            category=product.category,
            price=product.price,
            rating=product.rating,
            match_score=score,
            reasons=reasons,
            tradeoffs=tradeoffs,
            citations=[f"product:{product.id}"],
        )
        for score, product, reasons, tradeoffs in top
    ]
    matched = []
    display_names = {"budget": "预算", "brew_method": "冲煮方式", "flavor": "风味偏好", "experience": "使用经验"}
    for key, label in display_names.items():
        if constraints.get(key):
            matched.append(f"已纳入{label}：{constraints[key]}")
    factual_answer = (
        f"我先按{'、'.join(matched) if matched else '当前描述'}筛选。"
        + (f"以下 {len(recommendations)} 个选项都在可用目录中；建议优先看第一项的取舍。" if recommendations else "当前硬条件下没有可推荐商品，建议提高预算或放宽冲煮方式。")
    )
    answer = enrich_explanation(request.question, factual_answer)
    response = DecisionResponse(
        answer=answer,
        recommendations=recommendations,
        matched_constraints=matched,
        unmet_constraints=unmet,
        tradeoffs=[tradeoff for _, _, _, tradeoffs in top for tradeoff in tradeoffs][:3],
        citations=citations,
        follow_up_questions=["您通常使用哪种冲煮方式？", "更在意低酸醇厚，还是花果香？"] if not constraints.get("flavor") else [],
        trace_id=trace_id,
    )
    _record_step(db, trace_id, "citation_validator", {"recommendation_count": len(recommendations)}, {"citation_count": len(citations), "valid": bool(citations) or not recommendations, "graph_nodes": graph_state["completed_nodes"]})
    db.add(AgentRun(trace_id=trace_id, consumer_id=consumer_id, question=request.question, model_name=get_settings().model_name, result=response.model_dump(mode="json")))
    db.commit()
    return response


def update_profile_from_event(db: Session, consumer_id: str, product: Product | None, event_type: str) -> None:
    profile = db.get(ConsumerProfile, consumer_id)
    if not profile:
        profile = ConsumerProfile(consumer_id=consumer_id, preferences={}, labels=[])
        db.add(profile)
    preferences = dict(profile.preferences or {})
    if product and event_type in {"save", "add_to_cart", "purchase"}:
        saved = set(preferences.get("saved_flavors", []))
        saved.update(product.flavor_tags)
        preferences["saved_flavors"] = sorted(saved)
    profile.preferences = preferences
    profile.labels = ["coffee_explorer"] if preferences.get("saved_flavors") else ["new_visitor"]
    db.commit()


def build_insights(db: Session) -> dict[str, Any]:
    events = list(db.scalars(select(Event)).all())
    funnel = Counter(event.event_type for event in events)
    product_events = Counter(event.product_id for event in events if event.product_id)
    top_product_id = product_events.most_common(1)[0][0] if product_events else None
    top_product = db.get(Product, top_product_id) if top_product_id else None
    profiles = list(db.scalars(select(ConsumerProfile)).all())
    explorers = sum("coffee_explorer" in (profile.labels or []) for profile in profiles)
    return {
        "total_events": len(events),
        "funnel": {key: funnel.get(key, 0) for key in ["view", "save", "add_to_cart", "purchase", "not_fit"]},
        "segments": [
            {"name": "咖啡探索者", "count": explorers, "signal": "已收藏或加入购物车，存在可解释的风味偏好"},
            {"name": "首次访问者", "count": max(len({event.consumer_id for event in events}) - explorers, 0), "signal": "缺少偏好信息，应优先询问冲煮方式与预算"},
        ],
        "strategy": {
            "title": "为高意向手冲新手提供稳定入门组合",
            "action": f"在手冲相关会话中优先解释 {top_product.name if top_product else '入门组合'} 的使用场景，并以预算和冲煮方式作为第一轮筛选条件。",
            "evidence": f"演示数据中该商品相关行为 {product_events.get(top_product_id, 0)} 次；不包含真实订单或个人信息。",
        },
    }
