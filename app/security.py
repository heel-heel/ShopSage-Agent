from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import get_settings

security = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    payload = {
        "sub": subject,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def anonymous_consumer() -> tuple[str, str]:
    consumer_id = f"consumer-{uuid4().hex[:12]}"
    return consumer_id, create_access_token(consumer_id, "consumer")


def current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先开始消费者会话或登录。")
    try:
        data = jwt.decode(credentials.credentials, get_settings().jwt_secret, algorithms=[ALGORITHM])
        return {"id": data["sub"], "role": data["role"]}
    except (JWTError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话已失效，请重新开始。") from exc


def require_consumer(identity: dict = Depends(current_identity)) -> dict:
    if identity["role"] != "consumer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该接口仅供消费者使用。")
    return identity


def require_admin(identity: dict = Depends(current_identity)) -> dict:
    if identity["role"] != "merchant_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该接口仅供商家管理员使用。")
    return identity
