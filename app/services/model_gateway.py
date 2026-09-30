"""Optional LiteLLM explanation layer; facts, ranking, and citations stay deterministic."""

from app.config import get_settings


def enrich_explanation(question: str, factual_summary: str) -> str:
    settings = get_settings()
    if settings.model_provider == "deterministic" or not settings.model_api_key:
        return factual_summary
    try:
        from litellm import completion

        response = completion(
            model=settings.model_name,
            api_key=settings.model_api_key,
            api_base=settings.model_api_base,
            temperature=0.2,
            timeout=15,
            messages=[
                {"role": "system", "content": "你是咖啡选购助手。只能重述给定事实，不能补充商品参数、健康承诺或未被证据支持的内容。用简明中文说明取舍。"},
                {"role": "user", "content": f"用户问题：{question}\n可用事实：{factual_summary}\n请给出不超过两句的建议。"},
            ],
        )
        text = response.choices[0].message.content.strip()
        return text or factual_summary
    except Exception:
        # A provider timeout must never remove the evidence-grounded response.
        return factual_summary
