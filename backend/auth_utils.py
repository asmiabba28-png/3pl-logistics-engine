import os
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

JWT_SECRET = os.getenv("JWT_SECRET", "fallback_temporary_secret_key_change_this")
JWT_ALGORITHM = "HS256"

security_agent = HTTPBearer()

def hash_password(password: str) -> str:
    """
    Standard secure SHA-256 hashing for password storage.
    """
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

def create_tenant_access_token(tenant_id: str, user_id: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    Generates a secure JWT token binding the worker to their specific 3PL tenant_id scope.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=7) # Long-lived token for rugged warehouse scanners
        
    claims = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "exp": expire
    }
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_tenant_context(credentials: HTTPAuthorizationCredentials = Security(security_agent)) -> str:
    """
    Dependency Injection Middleware: Intercepts incoming API calls, decodes the JWT,
    and returns the tenant_id to isolate data queries.
    """
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        tenant_id: str = payload.get("tenant_id")
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Security validation failure: Token claims lack tenant scope boundaries."
            )
        return tenant_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token has expired.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token architecture profile.")