# Security Guide

Comprehensive security practices and patterns for Velocix applications.

---

## Table of Contents

1. [Input Sanitization](#input-sanitization)
2. [SQL Injection Prevention](#sql-injection-prevention)
3. [Authentication & Authorization](#authentication--authorization)
4. [Password Management](#password-management)
5. [Rate Limiting](#rate-limiting)
6. [CORS Configuration](#cors-configuration)
7. [Security Headers](#security-headers)
8. [Secure Session Management](#secure-session-management)

---

## Input Sanitization

### Why It Matters

**Critical Issue**: Without proper input sanitization, your application is vulnerable to:
- SQL Injection attacks
- XSS (Cross-Site Scripting)
- Command Injection
- Path Traversal
- NoSQL Injection

### Built-in Validation with msgspec

Velocix uses `msgspec` for fast, type-safe validation:

```python
from velocix.validation.models import Struct

class UserCreate(Struct):
    username: str
    email: str
    age: int

@app.post("/users")
async def create_user(user: UserCreate):
    # Input is automatically validated:
    # - username must be a string
    # - email must be a string
    # - age must be an integer
    return {"user": user}
```

### Advanced Validation

```python
from velocix.validation.validators import validate_email, validate_length

class UserCreate(Struct):
    username: str
    email: str
    password: str
    age: int

def validate_user(user: UserCreate):
    # Email validation
    if not validate_email(user.email):
        raise ValueError("Invalid email format")
    
    # Length validation
    if not validate_length(user.username, min_len=3, max_len=50):
        raise ValueError("Username must be 3-50 characters")
    
    # Password strength
    if len(user.password) < 8:
        raise ValueError("Password must be at least 8 characters")
    
    # Age range
    if user.age < 18 or user.age > 120:
        raise ValueError("Invalid age")
    
    return True

@app.post("/users")
async def create_user(user: UserCreate):
    validate_user(user)
    # Now safe to proceed
    return {"user": user}
```

### Custom Input Sanitizer

```python
import re
import html

class InputSanitizer:
    """Sanitize user input to prevent injection attacks"""
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        """Remove dangerous characters from string input"""
        if not isinstance(value, str):
            raise ValueError("Input must be a string")
        
        # Limit length
        value = value[:max_length]
        
        # Remove null bytes
        value = value.replace('\x00', '')
        
        # Escape HTML
        value = html.escape(value)
        
        return value.strip()
    
    @staticmethod
    def sanitize_sql_identifier(identifier: str) -> str:
        """Sanitize table/column names (not values!)"""
        # Only allow alphanumeric and underscores
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
            raise ValueError("Invalid identifier")
        return identifier
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent path traversal"""
        # Remove directory separators
        filename = filename.replace('..', '').replace('/', '').replace('\\', '')
        
        # Only allow safe characters
        filename = re.sub(r'[^a-zA-Z0-9._-]', '', filename)
        
        return filename
    
    @staticmethod
    def sanitize_url(url: str) -> str:
        """Validate and sanitize URLs"""
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        
        # Only allow http/https
        if parsed.scheme not in ('http', 'https'):
            raise ValueError("Invalid URL scheme")
        
        return url

# Usage
sanitizer = InputSanitizer()

@app.post("/posts")
async def create_post(title: str, content: str):
    title = sanitizer.sanitize_string(title, max_length=200)
    content = sanitizer.sanitize_string(content, max_length=10000)
    
    # Now safe to use
    await db.execute(
        "INSERT INTO posts (title, content) VALUES (?, ?)",
        title, content
    )
    return {"created": True}
```

### Input Sanitization Middleware

```python
from velocix.core.middleware import BaseMiddleware
from velocix.core.request import Request

class InputSanitizationMiddleware(BaseMiddleware):
    """Sanitize all incoming request data"""
    
    def __init__(self, app):
        super().__init__(app)
        self.sanitizer = InputSanitizer()
    
    async def __call__(self, request: Request):
        # Sanitize query parameters
        if request.query_params:
            sanitized = {}
            for key, value in request.query_params.items():
                sanitized[key] = self.sanitizer.sanitize_string(value)
            request._query_params = sanitized
        
        # Sanitize form data
        if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
            form = await request.form()
            sanitized = {}
            for key, value in form.items():
                if isinstance(value, str):
                    sanitized[key] = self.sanitizer.sanitize_string(value)
                else:
                    sanitized[key] = value
            request._form = sanitized
        
        return await self.app(request)

# Apply middleware
app.add_middleware(InputSanitizationMiddleware)
```

---

## SQL Injection Prevention

### ❌ NEVER Do This

```python
# VULNERABLE TO SQL INJECTION
@app.get("/users")
async def get_user(email: str):
    query = f"SELECT * FROM users WHERE email = '{email}'"
    result = await db.execute(query)
    return result

# An attacker can send: email = "'; DROP TABLE users; --"
# Resulting query: SELECT * FROM users WHERE email = ''; DROP TABLE users; --'
```

### ✅ Always Use Parameterized Queries

```python
# SAFE - Using placeholders
@app.get("/users")
async def get_user(email: str):
    query = "SELECT * FROM users WHERE email = ?"
    result = await db.execute(query, email)
    return result

# Or with named parameters
@app.get("/users")
async def get_user(email: str):
    query = "SELECT * FROM users WHERE email = :email"
    result = await db.execute(query, {"email": email})
    return result
```

### Use ORM for Additional Safety

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

@app.get("/users")
async def get_user(email: str, db: AsyncSession = Depends(get_db)):
    # SQLAlchemy automatically parameterizes
    result = await db.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    return {"user": user}
```

### Dynamic Table/Column Names (Rare Cases)

```python
# If you MUST use dynamic identifiers, sanitize them
@app.get("/data")
async def get_data(table: str, column: str):
    # Whitelist approach
    ALLOWED_TABLES = {'users', 'posts', 'comments'}
    ALLOWED_COLUMNS = {'id', 'name', 'email', 'title', 'content'}
    
    if table not in ALLOWED_TABLES:
        raise ValueError("Invalid table")
    if column not in ALLOWED_COLUMNS:
        raise ValueError("Invalid column")
    
    # Now safe to use
    query = f"SELECT {column} FROM {table}"
    result = await db.execute(query)
    return result
```

---

## Authentication & Authorization

### JWT Authentication

```python
from velocix.security.jwt import JWT, JWTConfig
from velocix.core.exceptions import Unauthorized
from velocix.core.depends import Depends

# Configure JWT
jwt = JWT(JWTConfig(
    secret_key="your-secret-key-min-32-chars-long",
    algorithm="HS256",
    access_token_expire_minutes=30,
    refresh_token_expire_days=7
))

# Login endpoint
@app.post("/login")
async def login(username: str, password: str):
    # Verify credentials
    user = await db.get_user(username)
    if not user or not verify_password(password, user.password):
        raise Unauthorized("Invalid credentials")
    
    # Create tokens
    access_token = jwt.create_access_token({"sub": user.id, "role": user.role})
    refresh_token = jwt.create_refresh_token({"sub": user.id})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

# Protected endpoint
async def get_current_user(token: str = Depends(jwt.get_token)):
    payload = jwt.decode_token(token)
    user_id = payload.get("sub")
    
    if not user_id:
        raise Unauthorized("Invalid token")
    
    user = await db.get_user(user_id)
    if not user:
        raise Unauthorized("User not found")
    
    return user

@app.get("/me")
async def get_me(user = Depends(get_current_user)):
    return {"user": user}
```

### Role-Based Access Control

```python
from functools import wraps

def require_role(*allowed_roles):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, user = Depends(get_current_user), **kwargs):
            if user.role not in allowed_roles:
                raise Forbidden("Insufficient permissions")
            return await func(*args, user=user, **kwargs)
        return wrapper
    return decorator

@app.delete("/users/{user_id}")
@require_role("admin", "moderator")
async def delete_user(user_id: int, user = Depends(get_current_user)):
    await db.delete_user(user_id)
    return {"deleted": True}
```

---

## Password Management

### ✅ Use Argon2 (Recommended)

```python
from velocix.security.password import Argon2Hasher

hasher = Argon2Hasher()

@app.post("/register")
async def register(username: str, password: str):
    # Hash password
    hashed = hasher.hash_password(password)
    
    # Store only the hash
    await db.execute(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        username, hashed
    )
    return {"created": True}

@app.post("/login")
async def login(username: str, password: str):
    user = await db.get_user(username)
    
    # Verify password
    if not hasher.verify_password(password, user.password):
        raise Unauthorized("Invalid credentials")
    
    return {"token": create_token(user)}
```

### Password Requirements

```python
import re

def validate_password_strength(password: str) -> bool:
    """Enforce strong password policy"""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    
    if not re.search(r'[A-Z]', password):
        raise ValueError("Password must contain uppercase letter")
    
    if not re.search(r'[a-z]', password):
        raise ValueError("Password must contain lowercase letter")
    
    if not re.search(r'[0-9]', password):
        raise ValueError("Password must contain number")
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValueError("Password must contain special character")
    
    return True

@app.post("/register")
async def register(username: str, password: str):
    validate_password_strength(password)
    hashed = hasher.hash_password(password)
    # Continue...
```

---

## Rate Limiting

```python
from velocix.security.ratelimit import RateLimitMiddleware, ProductionRateLimiter

# Create limiter
limiter = ProductionRateLimiter()

# Global limit: 100 requests per 10 seconds
limiter.set_global_bucket(capacity=100, refill_rate=10)

# Login limit: 5 attempts per minute
limiter.set_bucket("/login", capacity=5, refill_rate=0.083)

# API limit: 1000 requests per minute
limiter.set_bucket("/api", capacity=1000, refill_rate=16.67)

# Apply middleware
app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter,
    key_func=lambda req: req.client[0]  # IP-based
)
```

---

## CORS Configuration

```python
from velocix.security.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # Specific domains
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
    max_age=600
)

# For development (NEVER in production)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_methods=["*"],
#     allow_headers=["*"]
# )
```

---

## Security Headers

```python
from velocix.core.middleware import BaseMiddleware

class SecurityHeadersMiddleware(BaseMiddleware):
    async def __call__(self, request):
        response = await self.app(request)
        
        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # Enable XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # HTTPS only
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions policy
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

---

## Secure Session Management

```python
import secrets
from datetime import datetime, timedelta

class SessionManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.session_ttl = 3600  # 1 hour
    
    async def create_session(self, user_id: int) -> str:
        """Create secure session"""
        # Generate cryptographically secure token
        session_id = secrets.token_urlsafe(32)
        
        # Store session data
        session_data = {
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "ip": request.client[0]
        }
        
        await self.redis.setex(
            f"session:{session_id}",
            self.session_ttl,
            json.dumps(session_data)
        )
        
        return session_id
    
    async def get_session(self, session_id: str) -> dict:
        """Retrieve session data"""
        data = await self.redis.get(f"session:{session_id}")
        if not data:
            raise Unauthorized("Invalid session")
        
        return json.loads(data)
    
    async def destroy_session(self, session_id: str):
        """Destroy session"""
        await self.redis.delete(f"session:{session_id}")
    
    async def refresh_session(self, session_id: str):
        """Extend session lifetime"""
        await self.redis.expire(f"session:{session_id}", self.session_ttl)

# Usage
@app.post("/login")
async def login(username: str, password: str):
    user = await authenticate(username, password)
    session_id = await session_manager.create_session(user.id)
    
    return {
        "session_id": session_id,
        "expires_in": 3600
    }
```

---

**Security is not optional - implement these practices from day one! 🔒**
