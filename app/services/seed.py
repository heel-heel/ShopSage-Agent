from datetime import UTC, datetime, timedelta
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.catalog import CATALOG, KNOWLEDGE
from app.models import Event, Product
from app.services.knowledge import knowledge_store


def seed_database(db: Session) -> None:
    if not db.scalar(select(Product.id).limit(1)):
        db.add_all([Product(**item) for item in CATALOG])
        db.commit()

    for item in CATALOG:
        text = f"{item['name']}。{item['summary']} 冲煮方式：{'、'.join(item['brew_methods'])}。风味/特点：{'、'.join(item['flavor_tags'])}。"
        knowledge_store.upsert(item["id"], item["name"], text, {"type": "product", "source_url": item["source_url"]})
    for item in KNOWLEDGE:
        knowledge_store.upsert(item["id"], item["title"], item["text"], {"type": "guide"})

    if db.scalar(select(Event.id).limit(1)):
        return
    rng = Random(42)
    product_ids = [item["id"] for item in CATALOG]
    fake_consumers = [f"demo-{index:02d}" for index in range(1, 25)]
    event_types = ["view", "view", "view", "save", "add_to_cart", "purchase"]
    now = datetime.now(UTC)
    events = []
    for _ in range(180):
        event_type = rng.choice(event_types)
        events.append(
            Event(
                consumer_id=rng.choice(fake_consumers),
                product_id=rng.choice(product_ids),
                event_type=event_type,
                payload={"seed": True},
                created_at=now - timedelta(days=rng.randrange(0, 28)),
            )
        )
    db.add_all(events)
    db.commit()
