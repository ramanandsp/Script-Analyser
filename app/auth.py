import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Optional, Dict, Any

import jwt
import requests
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
SECRET_KEY = os.getenv("SECRET_KEY", "script-analyser-jwt-secret-key-398247923847")
DEMO_USER_EMAIL = os.getenv("DEMO_USER_EMAIL", "faculty@scriptanalyser.com")
DEMO_USER_PASSWORD = os.getenv("DEMO_USER_PASSWORD", "FacultyDemo2026!")

# Local password hashing
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}:{key.hex()}"

def verify_password(stored_password: str, provided_password: str) -> bool:
    try:
        salt, key_hex = stored_password.split(":")
        new_key = hashlib.pbkdf2_hmac("sha256", provided_password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return hmac.compare_digest(new_key.hex(), key_hex)
    except Exception:
        return False

# Token generation
def create_access_token(user_id: str, email: str, name: str = "", expires_in_seconds: int = 86400 * 7) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "name": name,
        "role": "authenticated",
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_seconds,
        "aud": "authenticated",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    # 1. Check if token is the hardcoded demo session
    if token == "demo-faculty-session-token":
        return {
            "id": "demo-user-id",
            "email": DEMO_USER_EMAIL,
            "name": "Faculty Reviewer",
            "role": "authenticated",
        }

    # 2. If Supabase JWT Secret is provided, decode with it
    if SUPABASE_JWT_SECRET:
        try:
            payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
            return {
                "id": payload.get("sub", payload.get("id")),
                "email": payload.get("email", ""),
                "name": payload.get("user_metadata", {}).get("full_name", payload.get("email", "").split("@")[0]),
                "role": payload.get("role", "authenticated"),
            }
        except Exception:
            pass

    # 3. If Supabase URL is set, verify with Supabase Auth endpoint
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            resp = requests.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": SUPABASE_ANON_KEY,
                },
                timeout=4.0,
            )
            if resp.status_code == 200:
                user_data = resp.json()
                metadata = user_data.get("user_metadata", {})
                return {
                    "id": user_data.get("id"),
                    "email": user_data.get("email", ""),
                    "name": metadata.get("full_name") or metadata.get("name") or user_data.get("email", "").split("@")[0],
                    "role": "authenticated",
                }
        except Exception as e:
            logger.debug(f"Supabase auth check notice: {e}")

    # 4. Fallback decode with local SECRET_KEY
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_aud": False})
        return {
            "id": payload.get("sub", payload.get("id")),
            "email": payload.get("email", ""),
            "name": payload.get("name", payload.get("email", "").split("@")[0]),
            "role": payload.get("role", "authenticated"),
        }
    except Exception:
        return None

# FastAPI dependency
def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in to access this project.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    user = decode_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication session. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user

# Optional dependency for routes that allow either authenticated user or demo guest
def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    if not authorization:
        return None
    try:
        return get_current_user(authorization)
    except HTTPException:
        return None

from pydantic import BaseModel, Field, field_validator

# ============================================================
# AUTH REQUEST SCHEMAS & ROUTER
# ============================================================

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=180)
    password: str = Field(min_length=6, max_length=128)
    full_name: Optional[str] = Field(default="", max_length=120)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean or "." not in clean.split("@")[-1]:
            raise ValueError("Please provide a valid email address.")
        return clean

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=180)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean:
            raise ValueError("Please provide a valid email address.")
        return clean

@auth_router.post("/register")
def register(payload: RegisterRequest):
    email = payload.email.strip().lower()
    password = payload.password
    full_name = (payload.full_name or "").strip()

    # If Supabase Auth is configured, register through Supabase
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            resp = requests.post(
                f"{SUPABASE_URL}/auth/v1/signup",
                headers={
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_ANON_KEY,
                },
                json={
                    "email": email,
                    "password": password,
                    "data": {"full_name": full_name},
                },
                timeout=6.0,
            )
            data = resp.json()
            if resp.status_code in (200, 201):
                user = data.get("user") or data
                access_token = data.get("access_token") or create_access_token(user.get("id"), email, full_name)
                return {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "user": {
                        "id": user.get("id"),
                        "email": email,
                        "name": full_name or email.split("@")[0],
                    },
                    "message": "Registration successful",
                }
            else:
                msg = data.get("msg") or data.get("error_description") or data.get("message") or "Registration failed"
                raise HTTPException(status_code=400, detail=msg)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Supabase registration error, falling back to local: {e}")

    # Local fallback registration
    from .database import connection
    with connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="An account with this email already exists.")
        
        user_id = secrets.token_hex(16)
        pw_hash = hash_password(password)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn.execute(
            "INSERT INTO users (id, email, password_hash, full_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, pw_hash, full_name, now)
        )
    
    token = create_access_token(user_id, email, full_name)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user_id, "email": email, "name": full_name or email.split("@")[0]},
        "message": "Account created successfully",
    }

@auth_router.post("/login")
def login(payload: LoginRequest):
    email = payload.email.strip().lower()
    password = payload.password

    # Check for faculty demo credentials
    if email == DEMO_USER_EMAIL.lower() and password == DEMO_USER_PASSWORD:
        token = create_access_token("demo-user-id", DEMO_USER_EMAIL, "Faculty Reviewer")
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": "demo-user-id",
                "email": DEMO_USER_EMAIL,
                "name": "Faculty Reviewer",
            },
            "message": "Faculty demonstration login successful",
        }

    # If Supabase Auth is configured, authenticate through Supabase
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            resp = requests.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers={
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_ANON_KEY,
                },
                json={"email": email, "password": password},
                timeout=6.0,
            )
            data = resp.json()
            if resp.status_code == 200:
                user = data.get("user", {})
                name = user.get("user_metadata", {}).get("full_name") or email.split("@")[0]
                return {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "token_type": "bearer",
                    "user": {
                        "id": user.get("id"),
                        "email": email,
                        "name": name,
                    },
                    "message": "Login successful",
                }
            else:
                msg = data.get("error_description") or data.get("msg") or "Invalid email or password"
                raise HTTPException(status_code=401, detail=msg)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Supabase login error, attempting local fallback: {e}")

    # Local fallback authentication
    from .database import connection
    with connection() as conn:
        row = conn.execute("SELECT id, email, password_hash, full_name FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not verify_password(row["password_hash"], password):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        
        token = create_access_token(row["id"], row["email"], row["full_name"])
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": row["id"],
                "email": row["email"],
                "name": row["full_name"] or row["email"].split("@")[0],
            },
            "message": "Login successful",
        }

@auth_router.post("/demo-login")
def demo_login():
    """One-click instant login for university faculty presentation/demonstration."""
    token = create_access_token("demo-user-id", DEMO_USER_EMAIL, "Faculty Reviewer")
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": "demo-user-id",
            "email": DEMO_USER_EMAIL,
            "name": "Faculty Reviewer",
        },
        "message": "Demo login successful",
    }

@auth_router.get("/me")
def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    return {"user": user}

@auth_router.post("/logout")
def logout():
    return {"status": "ok", "message": "Signed out successfully"}
