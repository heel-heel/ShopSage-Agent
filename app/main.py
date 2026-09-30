from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.models import AgentRun, AgentStep, Event, KnowledgeDocument, Product
from app.schemas import AdminLogin, AgentRunResponse, ChatRequest, ConsumerToken, EventRequest, InsightResponse, ProductResponse
from app.security import anonymous_consumer, create_access_token, require_admin, require_consumer
from app.services.agent import build_insights, run_decision_agent, update_profile_from_event
from app.services.knowledge import knowledge_store
from app.services.seed import seed_database

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(title="ShopSage", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def consumer_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/api/health")
def health():
    settings = get_settings()
    return {"status": "ok", "model_provider": settings.model_provider, "model_name": settings.model_name}


@app.post("/api/auth/consumer", response_model=ConsumerToken)
def start_consumer_session():
    consumer_id, token = anonymous_consumer()
    return ConsumerToken(access_token=token, consumer_id=consumer_id)


@app.post("/api/auth/admin", response_model=ConsumerToken)
def admin_login(payload: AdminLogin):
    settings = get_settings()
    if payload.email != settings.admin_email or payload.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="管理员凭据不正确。")
    return ConsumerToken(access_token=create_access_token(payload.email, "merchant_admin"), consumer_id=payload.email)


@app.post("/api/consumer/chat")
def consumer_chat(request: ChatRequest, identity: dict = Depends(require_consumer), db: Session = Depends(get_db)):
    return run_decision_agent(db, identity["id"], request)


@app.post("/api/consumer/events")
def consumer_event(request: EventRequest, identity: dict = Depends(require_consumer), db: Session = Depends(get_db)):
    product = db.get(Product, request.product_id) if request.product_id else None
    if request.product_id and not product:
        raise HTTPException(status_code=404, detail="商品不存在。")
    db.add(Event(consumer_id=identity["id"], product_id=request.product_id, event_type=request.event_type, payload=request.payload))
    db.commit()
    update_profile_from_event(db, identity["id"], product, request.event_type)
    return {"ok": True}


@app.get("/api/consumer/products/{product_id}", response_model=ProductResponse)
def product_detail(product_id: str, identity: dict = Depends(require_consumer), db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在。")
    return product


@app.get("/api/admin/insights", response_model=InsightResponse)
def admin_insights(identity: dict = Depends(require_admin), db: Session = Depends(get_db)):
    return build_insights(db)


@app.get("/api/admin/agent-runs")
def admin_runs(identity: dict = Depends(require_admin), db: Session = Depends(get_db)):
    runs = list(db.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(20)).all())
    return [{"trace_id": run.trace_id, "question": run.question, "consumer_id": run.consumer_id, "created_at": run.created_at, "status": run.status} for run in runs]


@app.get("/api/admin/agent-runs/{trace_id}", response_model=AgentRunResponse)
def admin_run_detail(trace_id: str, identity: dict = Depends(require_admin), db: Session = Depends(get_db)):
    run = db.get(AgentRun, trace_id)
    if not run:
        raise HTTPException(status_code=404, detail="未找到该运行记录。")
    steps = list(db.scalars(select(AgentStep).where(AgentStep.trace_id == trace_id).order_by(AgentStep.id)).all())
    return AgentRunResponse(trace_id=run.trace_id, consumer_id=run.consumer_id, question=run.question, model_name=run.model_name, status=run.status, result=run.result, created_at=run.created_at, steps=[{"name": step.step_name, "input": step.input_data, "output": step.output_data} for step in steps])


@app.post("/api/admin/knowledge/import")
async def knowledge_import(file: UploadFile = File(...), identity: dict = Depends(require_admin), db: Session = Depends(get_db)):
    content = await file.read()
    if len(content) > 1_000_000:
        raise HTTPException(status_code=413, detail="演示版单个文件最大为 1 MB。")
    import hashlib
    from uuid import uuid4

    content_hash = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.content_hash == content_hash))
    if existing:
        return {"status": "skipped", "document_id": existing.id, "reason": "内容未变化，无需重复索引。"}
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="演示版仅支持 UTF-8 的 TXT、Markdown、CSV。") from exc
    document_id = f"upload-{uuid4().hex[:12]}"
    document = KnowledgeDocument(id=document_id, filename=file.filename or "untitled.txt", content_hash=content_hash)
    db.add(document)
    knowledge_store.upsert(document_id, document.filename, text, {"type": "upload"})
    db.commit()
    return {"status": "indexed", "document_id": document_id, "characters": len(text)}
