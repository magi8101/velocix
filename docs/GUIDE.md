# Velocix User Guide

Complete guide to building applications with Velocix.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Basic Concepts](#basic-concepts)
3. [Routing](#routing)
4. [Request Handling](#request-handling)
5. [Response Handling](#response-handling)
6. [Validation](#validation)
7. [Dependency Injection](#dependency-injection)
8. [Middleware](#middleware)
9. [Security](#security)
10. [WebSocket](#websocket)
11. [Background Tasks](#background-tasks)
12. [Error Handling](#error-handling)
13. [Testing](#testing)

---

## Getting Started

### Installation

```bash
# Clone or create your project
mkdir my-velocix-app
cd my-velocix-app

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Velocix
pip install -r requirements.txt
```

### Your First App

Create `main.py`:

```python
from velocix import Velocix

app = Velocix()

@app.get("/")
async def root():
    return {"message": "Hello, World!"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

Run it:

```bash
python -m velocix run main:app --port 8000
```

Visit `http://localhost:8000` to see your app!

---

## Basic Concepts

### Application Instance

The `Velocix` class is the main application instance:

```python
from velocix import Velocix

app = Velocix(
    title="My API",
    version="1.0.0",
    description="My awesome API",
    debug=False
)
```

**Options:**
- `title` - API title for documentation
- `version` - API version
- `description` - API description
- `debug` - Enable debug mode (detailed errors)

### Async/Await

Velocix is built on async Python. Always use `async def` for handlers:

```python
@app.get("/users")
async def get_users():
    # Use await for async operations
    users = await db.fetch_all()
    return {"users": users}
```

---

## Routing

### Basic Routes

```python
@app.get("/items")
async def list_items():
    return {"items": []}

@app.post("/items")
async def create_item():
    return {"created": True}

@app.put("/items/{item_id}")
async def update_item(item_id: int):
    return {"updated": item_id}

@app.delete("/items/{item_id}")
async def delete_item(item_id: int):
    return {"deleted": item_id}
```

### Path Parameters

```python
# Single parameter
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"user_id": user_id}

# Multiple parameters
@app.get("/posts/{post_id}/comments/{comment_id}")
async def get_comment(post_id: int, comment_id: int):
    return {"post": post_id, "comment": comment_id}

# Type conversion
@app.get("/items/{item_id}")
async def get_item(item_id: int):  # Automatically converted to int
    return {"item_id": item_id}
```

**Supported types:**
- `int` - Integer
- `str` - String (default)
- `float` - Float
- `bool` - Boolean

### Query Parameters

```python
@app.get("/search")
async def search(
    q: str,                    # Required query param
    limit: int = 10,           # Optional with default
    offset: int = 0,           # Optional with default
    sort: str | None = None    # Optional, can be None
):
    return {
        "query": q,
        "limit": limit,
        "offset": offset,
        "sort": sort
    }
```

Example: `GET /search?q=python&limit=20&offset=10`

### Route Metadata

Add metadata for documentation:

```python
@app.get(
    "/users/{user_id}",
    summary="Get user by ID",
    description="Retrieve a user's full profile information",
    response_description="User profile data",
    tags=["users"]
)
async def get_user(user_id: int):
    return {"user_id": user_id}
```

### Sub-Routers

Organize routes into modules:

```python
# routes/users.py
from velocix.core.router import Router

router = Router(prefix="/users", tags=["users"])

@router.get("/")
async def list_users():
    return {"users": []}

@router.get("/{user_id}")
async def get_user(user_id: int):
    return {"user_id": user_id}
```

```python
# main.py
from velocix import Velocix
from routes import users

app = Velocix()
app.include_router(users.router)
```

---

## Request Handling

### Accessing the Request

```python
from velocix.core.request import Request

@app.get("/info")
async def get_info(request: Request):
    return {
        "method": request.method,
        "path": request.path,
        "headers": dict(request.headers),
        "query": request.query_params,
        "client": request.client
    }
```

### JSON Body

```python
@app.post("/users")
async def create_user(request: Request):
    data = await request.json()
    return {"received": data}
```

### Form Data

```python
@app.post("/upload")
async def upload(request: Request):
    form = await request.form()
    name = form.get("name")
    file = form.get("file")
    return {"name": name, "file": file.filename}
```

### Raw Body

```python
@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    return {"size": len(body)}
```

### Streaming

```python
@app.post("/upload-large")
async def upload_large(request: Request):
    async for chunk in request.stream():
        # Process chunk
        await process(chunk)
    return {"uploaded": True}
```

### Headers & Cookies

```python
@app.get("/auth")
async def check_auth(request: Request):
    token = request.headers.get("Authorization")
    session = request.cookies.get("session")
    return {"token": token, "session": session}
```

---

## Response Handling

### JSON Response (Default)

```python
@app.get("/data")
async def get_data():
    # Automatically converted to JSON
    return {"key": "value"}
```

### HTML Response

```python
from velocix.core.response import HTMLResponse

@app.get("/page")
async def get_page():
    return HTMLResponse("<h1>Hello World</h1>")
```

### Plain Text

```python
from velocix.core.response import PlainTextResponse

@app.get("/text")
async def get_text():
    return PlainTextResponse("Hello World")
```

### Custom Status Code

```python
from velocix.core.response import JSONResponse

@app.post("/items")
async def create_item():
    return JSONResponse(
        {"created": True},
        status_code=201
    )
```

### Custom Headers

```python
from velocix.core.response import Response

@app.get("/custom")
async def custom():
    return Response(
        content=b"Custom content",
        headers={"X-Custom": "Header"},
        media_type="text/plain"
    )
```

### File Download

```python
from velocix.core.response import FileResponse

@app.get("/download")
async def download():
    return FileResponse(
        path="./files/document.pdf",
        filename="document.pdf",
        media_type="application/pdf"
    )
```

### Streaming Response

```python
from velocix.core.response import StreamingResponse

@app.get("/stream")
async def stream():
    async def generate():
        for i in range(100):
            yield f"data: {i}\n\n"
            await asyncio.sleep(0.1)
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
```

---

## Validation

### Using Struct Models

```python
from velocix.validation.models import Struct

class User(Struct):
    name: str
    email: str
    age: int
    is_active: bool = True

@app.post("/users")
async def create_user(user: User):
    # user is validated automatically
    return {"created": True, "user": user}
```

### Nested Models

```python
class Address(Struct):
    street: str
    city: str
    zip_code: str

class User(Struct):
    name: str
    email: str
    address: Address

@app.post("/users")
async def create_user(user: User):
    return {"user": user}
```

### Optional Fields

```python
from typing import Optional

class User(Struct):
    name: str
    email: str
    phone: Optional[str] = None  # Optional field
    age: int = 18                # Default value
```

### Lists and Arrays

```python
class Tags(Struct):
    tags: list[str]

class Post(Struct):
    title: str
    content: str
    tags: list[str]

@app.post("/posts")
async def create_post(post: Post):
    return {"post": post}
```

---

## Dependency Injection

### Basic Dependencies

```python
from velocix.core.depends import Depends

async def get_db():
    db = Database()
    try:
        yield db
    finally:
        await db.close()

@app.get("/users")
async def list_users(db = Depends(get_db)):
    users = await db.fetch_all("SELECT * FROM users")
    return {"users": users}
```

### Nested Dependencies

```python
async def get_token(request: Request):
    return request.headers.get("Authorization", "").replace("Bearer ", "")

async def get_current_user(token: str = Depends(get_token)):
    user = await verify_token(token)
    return user

@app.get("/me")
async def get_me(user = Depends(get_current_user)):
    return {"user": user}
```

### Class Dependencies

```python
class Pagination:
    def __init__(self, skip: int = 0, limit: int = 100):
        self.skip = skip
        self.limit = limit

@app.get("/items")
async def list_items(pagination: Pagination = Depends()):
    return {
        "skip": pagination.skip,
        "limit": pagination.limit
    }
```

---

## Middleware

### Adding Middleware

```python
from velocix.middleware.compression import CompressionMiddleware

app.add_middleware(CompressionMiddleware, minimum_size=1000)
```

### Custom Middleware

```python
from velocix.core.middleware import BaseMiddleware

class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, request):
        print(f"Request: {request.method} {request.path}")
        
        response = await self.app(request)
        
        print(f"Response: {response.status_code}")
        return response

app.add_middleware(LoggingMiddleware)
```

### Middleware with Config

```python
class TimingMiddleware(BaseMiddleware):
    def __init__(self, app, threshold: float = 1.0):
        super().__init__(app)
        self.threshold = threshold
    
    async def __call__(self, request):
        start = time.time()
        response = await self.app(request)
        duration = time.time() - start
        
        if duration > self.threshold:
            print(f"Slow request: {duration:.2f}s")
        
        return response

app.add_middleware(TimingMiddleware, threshold=0.5)
```

---

## Security

### CORS

```python
from velocix.security.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True
)
```

### JWT Authentication

```python
from velocix.security.jwt import JWTManager

jwt_manager = JWTManager(
    secret_key="your-secret-key",
    algorithm="HS256"
)

@app.post("/login")
async def login(username: str, password: str):
    # Verify credentials
    if verify_credentials(username, password):
        token = jwt_manager.create_access_token({"sub": username})
        return {"access_token": token}
    
    raise HTTPException(401, "Invalid credentials")

@app.get("/protected")
async def protected(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    payload = jwt_manager.decode(token)
    return {"user": payload["sub"]}
```

### Password Hashing

```python
from velocix.security.password import PasswordHasher

hasher = PasswordHasher()

# Hash password
hashed = hasher.hash_password("secret123")

# Verify password
is_valid = hasher.verify_password("secret123", hashed)
```

### Rate Limiting

```python
from velocix.security.ratelimit import RateLimitMiddleware, ProductionRateLimiter

limiter = ProductionRateLimiter()
limiter.set_global_bucket(capacity=100, refill_rate=10)

app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter,
    key_func=lambda req: req.client[0]
)
```

---

## WebSocket

### Basic WebSocket

```python
from velocix.websocket.connection import WebSocket

@app.websocket("/ws")
async def websocket_handler(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
    except:
        pass
    finally:
        await websocket.close()
```

### Broadcasting

```python
connections = []

@app.websocket("/chat")
async def chat(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    
    try:
        while True:
            message = await websocket.receive_text()
            for conn in connections:
                await conn.send_text(message)
    finally:
        connections.remove(websocket)
```

---

## Background Tasks

```python
from velocix.core.response import BackgroundTask, Response

def send_email(email: str, message: str):
    # This runs after response is sent
    print(f"Sending email to {email}")

@app.post("/register")
async def register(email: str, password: str):
    # Register user...
    
    task = BackgroundTask(send_email, email, "Welcome!")
    return Response(
        content={"registered": True},
        background=task
    )
```

---

## Error Handling

### HTTP Exceptions

```python
from velocix.core.exceptions import HTTPException, NotFound

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = await db.get_user(user_id)
    if not user:
        raise NotFound("User not found")
    return {"user": user}
```

### Custom Exception Handlers

```python
from velocix.core.response import JSONResponse

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        {"error": str(exc)},
        status_code=400
    )
```

---

## Testing

### Using Test Client

```python
from velocix.testing.client import TestClient

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello, World!"}

def test_create_user():
    response = client.post(
        "/users",
        json={"name": "John", "email": "john@example.com"}
    )
    assert response.status_code == 200
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_endpoint():
    async with TestClient(app) as client:
        response = await client.get("/async")
        assert response.status_code == 200
```

---

## Next Steps

- Read the [API Reference](API_REFERENCE.md) for detailed API docs
- Check out [Best Practices](BEST_PRACTICES.md) for tips
- See [Deployment Guide](DEPLOYMENT.md) for production deployment
- Explore the [Roadmap](ROADMAP.md) for upcoming features

---

**Happy coding with Velocix! 🚀**
