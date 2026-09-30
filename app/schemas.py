from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConsumerToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    consumer_id: str


class AdminLogin(BaseModel):
    email: str
    password: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    budget: float | None = Field(default=None, gt=0, le=10000)
    brew_method: str | None = None
    flavor: str | None = None
    experience: Literal["beginner", "intermediate", "expert"] | None = None


class EventRequest(BaseModel):
    event_type: Literal["view", "save", "not_fit", "add_to_cart", "purchase", "feedback"]
    product_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    id: str
    title: str
    excerpt: str
    source_url: str | None = None


class Recommendation(BaseModel):
    product_id: str
    name: str
    category: str
    price: float
    rating: float
    match_score: int = Field(ge=0, le=100)
    reasons: list[str]
    tradeoffs: list[str]
    citations: list[str]


class DecisionResponse(BaseModel):
    answer: str
    recommendations: list[Recommendation]
    matched_constraints: list[str]
    unmet_constraints: list[str]
    tradeoffs: list[str]
    citations: list[Citation]
    follow_up_questions: list[str]
    trace_id: str


class ProductResponse(BaseModel):
    id: str
    name: str
    category: str
    price: float
    rating: float
    review_count: int
    brew_methods: list[str]
    flavor_tags: list[str]
    level: str
    summary: str
    source_url: str | None


class InsightResponse(BaseModel):
    total_events: int
    funnel: dict[str, int]
    segments: list[dict[str, Any]]
    strategy: dict[str, Any]


class AgentRunResponse(BaseModel):
    trace_id: str
    consumer_id: str
    question: str
    model_name: str
    status: str
    result: dict[str, Any]
    created_at: datetime
    steps: list[dict[str, Any]]
