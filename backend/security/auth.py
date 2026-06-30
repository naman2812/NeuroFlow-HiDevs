import time
from typing import List, Dict, Any, Optional
import jwt
from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from backend.config import settings

# If settings doesn't have jwt_secret, fallback
JWT_SECRET = getattr(settings, "jwt_secret", "supersecretkey_change_in_production")
ALGORITHM = "HS256"

security = HTTPBearer()

class User(BaseModel):
    sub: str
    scopes: List[str]
    exp: int

def create_access_token(client_id: str, scopes: List[str], expires_in: int = 3600) -> str:
    payload = {
        "sub": client_id,
        "scopes": scopes,
        "exp": int(time.time()) + expires_in
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

async def get_current_user(request: Request, auth: HTTPAuthorizationCredentials = Security(security)) -> User:
    try:
        payload = jwt.decode(auth.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        user = User(**payload)
        # Attach user to request state for convenience
        request.state.user = user
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except (jwt.PyJWTError, Exception) as e:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

class RequireScope:
    def __init__(self, required_scope: str):
        self.required_scope = required_scope

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        if self.required_scope not in user.scopes:
            raise HTTPException(status_code=403, detail=f"Not enough permissions, requires {self.required_scope} scope")
        return user
