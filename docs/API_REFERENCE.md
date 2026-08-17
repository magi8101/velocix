# API Reference

Complete reference for all Velocix APIs and features.

---

## Table of Contents

- [Application](#application)
- [Routing](#routing)
- [Request Object](#request-object)
- [Response Objects](#response-objects)
- [Middleware](#middleware)
- [Security](#security)
- [Dependency Injection](#dependency-injection)
- [Validation](#validation)
- [WebSocket](#websocket)
- [Monitoring & Metrics](#monitoring--metrics)
- [OpenAPI Documentation](#openapi-documentation)
- [Error Handling](#error-handling)
- [Testing](#testing)

---

## Application

### Creating an App

```python
from velocix import Velocix

app = Velocix(
    title="My API",           # OpenAPI title
    version="1.0.0",          # API version
    debug=False               # Debug mode (enables detailed errors)
)
```

### Configuration Options

- `title` (str): API title for OpenAPI documentation
- `version` (str): API version
- `debug` (bool): Enable debug mode with detailed error messages
- `docs_url` (str): Path for Swagger UI (default: "/docs")
- `redoc_url` (str): Path for ReDoc (default: "/redoc")
- `openapi_url` (str): Path for OpenAPI JSON (default: "/openapi.json")

---

## Routing

### Route Decorators

```python
@app.get("/path")           # GET request
@app.post("/path")          # POST request
@app.put("/path")           # PUT request
@app.delete("/path")        # DELETE request
@app.patch("/path")         # PATCH request

# Multiple methods on one route
@app.route("/path", methods={"GET", "POST"})
async def multi(request):
    return {"ok": True}

# WebSocket route
@app.websocket("/ws")
async def websocket_handler(websocket):
    await websocket.accept()
    # ... handle WebSocket communication
```

**Route options** (all decorators accept these):

- `status_code` — default status for non-`Response` returns (dict/str -> 200,
  `None` -> 204; an explicit `Response` return wins)
- `response_model` — a msgspec `Struct`; validates and filters the returned
  dict and serializes via `msgspec`
- `name` — route name for `request.url_for(name, ...)` reverse routing

### Path Parameters

```python
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"user_id": user_id}

@app.get("/items/{item_id}/reviews/{review_id}")
async def get_review(item_id: int, review_id: int):
    return {"item_id": item_id, "review_id": review_id}
```

**Supported Types:**
- `int` - Integer path parameter
- `str` - String path parameter
- `float` - Float path parameter
- `bool` - Boolean path parameter

### Query Parameters

Any handler parameter that is not a path parameter becomes a query parameter:

```python
@app.get("/search")
async def search(q: str, limit: int = 10, offset: int = 0):
    return {"query": q, "limit": limit, "offset": offset}
```

**Features:**
- Automatic type conversion
- Default values
- Optional parameters (use `Optional[T]` or `T | None`)
- Missing required parameter -> 422

### Parameter Markers: Query, Header, Cookie, Form, File

For explicit control over where a value comes from, use the markers. The
`Annotated` style is preferred (mypy-clean); the classic `= Query(...)` style
also works.

```python
from typing import Annotated
from velocix import Cookie, File, Form, Header, Query, UploadFile

@app.get("/users")
async def list_users(
    page: Annotated[int, Query()] = 1,
    per_page: Annotated[int, Query(alias="per_page")] = 10,
    user_agent: Annotated[str | None, Header()] = None,   # "user-agent" header
    session_id: Annotated[str | None, Cookie()] = None,
):
    ...

@app.post("/upload")
async def upload(
    title: Annotated[str, Form()],
    doc: Annotated[UploadFile, File()],
):
    content = await doc.read()
    ...
```

**Markers:**

- `Query(default, *, alias)` — query-string parameter
- `Header(default, *, alias, convert_underscores=True)` — request header;
  `_` converts to `-` unless `convert_underscores=False`
- `Cookie(default, *, alias)` — request cookie
- `Form(default, *, alias)` — form field (urlencoded or multipart)
- `File(default, *, alias)` — multipart file part -> `UploadFile`
- Required (no default) + missing -> **422**; values convert to the annotated
  type

### Request Body

```python
from velocix.validation.models import Struct

class CreateUser(Struct):
    name: str
    email: str
    age: int

@app.post("/users")
async def create_user(user: CreateUser):
    return {"created": True, "user": user}
```

### Route Metadata

```python
@app.get(
    "/users/{user_id}",
    summary="Get user by ID",
    description="Retrieve detailed user information",
    response_description="User details",
    tags=["users"],
    status_code=200
)
async def get_user(user_id: int):
    return {"user_id": user_id}
```

### Sub-Routers

```python
from velocix import Router

# Create sub-router (prefix is applied at include time)
users_router = Router()

@users_router.get("/{user_id}")
async def get_user(user_id: int):
    return {"user_id": user_id}

@users_router.post("/")
async def create_user(name: str, email: str):
    return {"created": True}

# Include in main app, optionally under a prefix
app.include_router(users_router, prefix="/users")
```

Named routes on a sub-router keep working after inclusion: the prefix is
applied to the route path, and `request.url_for("user", ...)` returns the
prefixed URL.

---

## Request Object

The `Request` object provides access to all incoming HTTP data:

```python
from velocix.core.request import Request

@app.get("/info")
async def request_info(request: Request):
    return {
        "method": request.method,              # HTTP method
        "path": request.path,                  # Request path
        "query": request.query_params,         # Query parameters dict
        "headers": dict(request.headers),      # Headers dict
        "cookies": request.cookies,            # Cookies dict
        "client": request.client,              # Client IP and port
        "url": request.url,                    # Full URL string
        "base_url": request.base_url,          # Scheme + host
    }
```

#### `.url_for(name, **path_params)`
Build a URL for a named route (reverse routing):
```python
@app.get("/items/{item_id}", name="item")
async def get_item(request: Request, item_id: int):
    return {"url": request.url_for("item", item_id=item_id)}
# -> {"url": "http://host/items/7"}
```

Returns the absolute URL (base URL + path). Unknown names raise
`velocix.NoMatchFound`; use `Router.url_path_for(name, **params)` for the
path only.

### Request Methods

#### `.json()`
Get JSON body:
```python
@app.post("/json")
async def handle_json(request: Request):
    data = await request.json()
    return {"received": data}
```

#### `.form()`
Get form data:
```python
@app.post("/form")
async def handle_form(request: Request):
    form = await request.form()
    return {"received": dict(form)}
```

#### `.body()`
Get raw body bytes:
```python
@app.post("/raw")
async def handle_raw(request: Request):
    body = await request.body()
    return {"size": len(body)}
```

#### `.stream()`
Stream large body:
```python
@app.post("/upload")
async def upload_file(request: Request):
    async for chunk in request.stream():
        # Process chunk
        pass
    return {"uploaded": True}
```

### Request Properties

- `request.method` - HTTP method (GET, POST, etc.)
- `request.path` - URL path
- `request.query_params` - Query string parameters (dict-like)
- `request.headers` - HTTP headers (dict-like)
- `request.cookies` - Cookies (dict)
- `request.client` - Client address tuple (host, port)
- `request.url` - Full URL object
- `request.base_url` - Base URL
- `request.path_params` - Path parameters from route

---

## Response Objects

### JSONResponse (Default)

```python
@app.get("/data")
async def get_data():
    # Automatically returns JSONResponse
    return {"key": "value"}
```

### Response Types

#### HTMLResponse
```python
from velocix.core.response import HTMLResponse

@app.get("/html")
async def get_html():
    return HTMLResponse("<h1>Hello, World!</h1>")
```

#### PlainTextResponse
```python
from velocix.core.response import PlainTextResponse

@app.get("/text")
async def get_text():
    return PlainTextResponse("Hello, World!")
```

#### Custom Response
```python
from velocix.core.response import Response

@app.get("/custom")
async def get_custom():
    return Response(
        content=b"Custom content",
        status_code=200,
        headers={"X-Custom": "Header"},
        media_type="application/octet-stream"
    )
```

#### StreamingResponse
```python
from velocix.core.response import StreamingResponse

@app.get("/stream")
async def stream_data():
    async def generate():
        for i in range(100):
            yield f"data: {i}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
```

#### FileResponse
```python
from velocix.core.response import FileResponse

@app.get("/download")
async def download_file():
    return FileResponse(
        path="./file.pdf",
        filename="download.pdf",
        media_type="application/pdf"
    )
```

### Response Options

```python
Response(
    content=...,                    # Response body
    status_code=200,                # HTTP status code
    headers={...},                  # Custom headers
    media_type="application/json",  # Content-Type
    background=BackgroundTask(...)  # Background task
)
```

---

## Middleware

### Built-in Middleware

Middleware classes are instantiated by the app with the wrapped handler, so
configuration goes through `functools.partial`:

```python
from functools import partial

app.add_middleware(partial(MiddlewareClass, option=value))
```

#### CompressionMiddleware
```python
from functools import partial
from velocix.middleware.compression import CompressionMiddleware

app.add_middleware(partial(CompressionMiddleware, minimum_size=1000))
```

#### RequestIDMiddleware
```python
from functools import partial
from velocix.middleware.request_id import RequestIDMiddleware

app.add_middleware(partial(RequestIDMiddleware, header_name="X-Request-ID"))
```

#### CORSMiddleware
```python
from functools import partial
from velocix import CORSMiddleware

app.add_middleware(
    partial(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
        max_age=600,
        allow_origin_regex=r"https://.*\.example\.com",  # optional
    )
)
```

`allow_origin_regex` accepts a string or compiled `re.Pattern`; origins are
allowed if they `fullmatch` it. Pass `allow_origins=[]` with a regex to allow
regex-matched origins only.

### Custom Middleware

```python
from velocix.core.middleware import BaseMiddleware

class CustomMiddleware(BaseMiddleware):
    def __init__(self, app, custom_param="value"):
        super().__init__(app)
        self.custom_param = custom_param
    
    async def __call__(self, request):
        # Before request
        print(f"Incoming: {request.path}")
        
        # Process request
        response = await self.app(request)
        
        # After request
        response.headers["X-Custom"] = self.custom_param
        
        return response

app.add_middleware(CustomMiddleware, custom_param="my-value")
```

---

## Security

### JWT Authentication

```python
from velocix.security.jwt import JWTManager
from datetime import timedelta

jwt_manager = JWTManager(
    secret_key="your-secret-key-here",
    algorithm="HS256",
    access_token_expire_minutes=30
)

# Create token
@app.post("/login")
async def login(username: str, password: str):
    # Verify credentials...
    token = jwt_manager.create_access_token(
        data={"sub": username},
        expires_delta=timedelta(hours=1)
    )
    return {"access_token": token, "token_type": "bearer"}

# Verify token
@app.get("/protected")
async def protected_route(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        payload = jwt_manager.decode(token)
        return {"user": payload["sub"]}
    except Exception:
        raise HTTPException(401, "Unauthorized")
```

### Password Hashing

```python
from velocix.security.password import PasswordHasher, Argon2Hasher

# Scrypt hasher (default, fast)
hasher = PasswordHasher()
hashed = hasher.hash_password("secret123")
is_valid = hasher.verify_password("secret123", hashed)

# Argon2 hasher (more secure)
argon2 = Argon2Hasher()
hashed = argon2.hash_password("secret123")
is_valid = argon2.verify_password("secret123", hashed)
```

### Rate Limiting

```python
from velocix.security.ratelimit import RateLimitMiddleware, ProductionRateLimiter

limiter = ProductionRateLimiter()

# Global rate limit
limiter.set_global_bucket(capacity=100, refill_rate=10)  # 100 req, refill 10/sec

app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter,
    key_func=lambda req: req.client[0]  # Rate limit by IP
)

# Per-route rate limit
@app.get("/limited")
async def limited_route():
    return {"message": "Rate limited endpoint"}
```

### CORS Configuration

```python
from functools import partial
from velocix import CORSMiddleware

app.add_middleware(
    partial(
        CORSMiddleware,
        allow_origins=["https://example.com", "https://app.example.com"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
        allow_credentials=True,
        max_age=600,
        allow_origin_regex=r"https://.*\.example\.com",  # optional
    )
)
```

`allow_origin_regex` accepts a string or compiled `re.Pattern`; an origin is
allowed if it `fullmatch`es the pattern (checked after the `allow_origins`
list). Pass `allow_origins=[]` with a regex to allow regex-matched origins
only.

### Session Middleware

Signed, cookie-based sessions (Starlette-compatible):

```python
from functools import partial
from velocix import SessionMiddleware

app.add_middleware(partial(SessionMiddleware, secret_key="change-me", max_age=3600))

@app.get("/counter")
async def counter(request: Request):
    request.session["count"] = request.session.get("count", 0) + 1
    return {"count": request.session["count"]}
```

- `request.session` is a dict stored in a signed, timestamped cookie
  (itsdangerous); tampered/expired cookies fall back to an empty session
- The cookie is rewritten only when the session changes
- Options: `session_cookie` (default `session`), `max_age`, `path`,
  `same_site`, `https_only`, `domain`
- Without the middleware, `request.session` raises `AttributeError`

### Static Files

```python
from velocix import StaticFiles

app.mount("/static", StaticFiles(directory="./public", html=True))
```

- Serves files with detected MIME types; `HEAD` supported; `html=True` serves
  `index.html` for directories
- Path traversal is blocked
- `app.mount(path, asgi_app)` also accepts any ASGI application

---

## Dependency Injection

```python
from velocix.core.depends import Depends

# Simple dependency
async def get_db():
    db = Database()
    try:
        yield db
    finally:
        await db.close()

@app.get("/users")
async def get_users(db = Depends(get_db)):
    users = await db.fetch_all("SELECT * FROM users")
    return {"users": users}

# Nested dependencies
async def get_token(request: Request):
    return request.headers.get("Authorization", "").replace("Bearer ", "")

async def get_current_user(token: str = Depends(get_token)):
    payload = jwt_manager.decode(token)
    return payload["sub"]

@app.get("/me")
async def get_me(user = Depends(get_current_user)):
    return {"user": user}

# Class-based dependencies
class Pagination:
    def __init__(self, skip: int = 0, limit: int = 100):
        self.skip = skip
        self.limit = limit

@app.get("/items")
async def list_items(pagination: Pagination = Depends()):
    return {"skip": pagination.skip, "limit": pagination.limit}
```

---

## Validation

### Using Struct Models

```python
from velocix.validation.models import Struct
from typing import Optional

class User(Struct):
    name: str
    email: str
    age: int
    is_active: bool = True
    bio: Optional[str] = None

@app.post("/users")
async def create_user(user: User):
    # user is automatically validated
    return {"created": True, "user": user}
```

### Nested Models

```python
class Address(Struct):
    street: str
    city: str
    country: str

class UserWithAddress(Struct):
    name: str
    email: str
    address: Address

@app.post("/users/full")
async def create_user_full(user: UserWithAddress):
    return {"user": user}
```

### Manual Validation

```python
from velocix.validation.validators import validate_field

@app.post("/validate")
async def validate_data(email: str, age: int):
    # Validate email
    validate_field(email, "email") \
        .required() \
        .email() \
        .raise_if_invalid()
    
    # Validate age
    validate_field(age, "age") \
        .required() \
        .min_value(18) \
        .max_value(120) \
        .raise_if_invalid()
    
    return {"valid": True}
```

---

## WebSocket

### Basic WebSocket

```python
from velocix.websocket.connection import WebSocket

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            
            # Send response
            await websocket.send_text(f"Echo: {data}")
    
    except Exception:
        pass
    finally:
        await websocket.close()
```

### WebSocket Methods

- `await websocket.accept()` - Accept connection
- `await websocket.receive_text()` - Receive text message
- `await websocket.receive_bytes()` - Receive binary message
- `await websocket.receive_json()` - Receive JSON message
- `await websocket.send_text(data)` - Send text message
- `await websocket.send_bytes(data)` - Send binary message
- `await websocket.send_json(data)` - Send JSON message
- `await websocket.close(code=1000)` - Close connection

### Broadcasting

```python
active_connections = []

@app.websocket("/chat")
async def chat(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        while True:
            message = await websocket.receive_text()
            
            # Broadcast to all connections
            for connection in active_connections:
                await connection.send_text(message)
    finally:
        active_connections.remove(websocket)
```

---

## Monitoring & Metrics

### Prometheus Metrics

```python
from velocix.monitoring.metrics import MetricsMiddleware, metrics_endpoint

# Add metrics middleware
app.add_middleware(MetricsMiddleware)

# Expose metrics endpoint
@app.get("/metrics")
async def get_metrics(request):
    return metrics_endpoint(request)
```

### Available Metrics

- `velocix_http_requests_total` - Total HTTP requests (counter)
- `velocix_http_request_duration_seconds` - Request duration (histogram)
- `velocix_http_requests_in_progress` - Current requests (gauge)
- `velocix_http_errors_total` - Total errors (counter)
- `velocix_websocket_connections_active` - Active WebSocket connections (gauge)
- `velocix_cache_operations_total` - Cache hits/misses (counter)

### Health Check

```python
from velocix.monitoring.health import health_endpoint

@app.get("/health")
async def health_check(request):
    return health_endpoint(request)
```

Returns:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-09T12:00:00Z"
}
```

---

## OpenAPI Documentation

### Automatic Documentation

Velocix automatically generates OpenAPI documentation:

```python
app = Velocix(
    title="My API",
    version="1.0.0",
    description="API description here",
    docs_url="/docs",      # Swagger UI
    redoc_url="/redoc",    # ReDoc
    openapi_url="/openapi.json"
)
```

Access at:
- `http://localhost:8000/docs` - Swagger UI
- `http://localhost:8000/redoc` - ReDoc
- `http://localhost:8000/openapi.json` - OpenAPI spec

### Route Documentation

```python
@app.get(
    "/users/{user_id}",
    summary="Get user by ID",
    description="Retrieve detailed user information by their unique identifier",
    response_description="User details with all fields",
    tags=["users"],
    status_code=200
)
async def get_user(user_id: int):
    """
    Get a specific user by ID.
    
    - **user_id**: The user's unique identifier
    """
    return {"user_id": user_id}
```

---

## Error Handling

### Built-in Exceptions

```python
from velocix.core.exceptions import HTTPException, NotFound, MethodNotAllowed

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = db.get_user(user_id)
    
    if not user:
        raise NotFound("User not found")
    
    return {"user": user}

# Custom HTTP exception
@app.post("/items")
async def create_item(name: str):
    if not name:
        raise HTTPException(
            status_code=400,
            detail="Name is required"
        )
    
    return {"created": True}
```

### Custom Error Handlers

```python
from velocix.core.response import JSONResponse

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        {"error": str(exc)},
        status_code=400
    )

@app.exception_handler(Exception)
async def generic_error_handler(request, exc):
    return JSONResponse(
        {"error": "Internal server error"},
        status_code=500
    )
```

---

## Testing

### Test Client

```python
from velocix.testing.client import TestClient

# Create test client
client = TestClient(app)

# Test GET request
response = client.get("/")
assert response.status_code == 200
assert response.json() == {"message": "Hello, World!"}

# Test POST request
response = client.post(
    "/users",
    json={"name": "John", "email": "john@example.com", "age": 30}
)
assert response.status_code == 200

# Test with headers
response = client.get(
    "/protected",
    headers={"Authorization": "Bearer token123"}
)

# Test with cookies
response = client.get(
    "/",
    cookies={"session": "abc123"}
)
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_endpoint():
    async with TestClient(app) as client:
        response = await client.get("/async-endpoint")
        assert response.status_code == 200
```

### Testing Best Practices

```python
import pytest
from velocix.testing.client import TestClient

@pytest.fixture
def client():
    return TestClient(app)

def test_create_user(client):
    response = client.post(
        "/users",
        json={"name": "John", "email": "john@test.com", "age": 30}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] is True

def test_get_user_not_found(client):
    response = client.get("/users/999")
    assert response.status_code == 404
```

---

## Advanced Features

### Background Tasks

```python
from velocix.core.response import BackgroundTask, Response

def send_email(email: str, message: str):
    # Synchronous task
    print(f"Sending email to {email}: {message}")

@app.post("/send")
async def send_notification(email: str):
    task = BackgroundTask(send_email, email, "Welcome!")
    return Response(
        content={"sent": True},
        background=task
    )
```

### Custom Response Classes

```python
from velocix.core.response import Response

class XMLResponse(Response):
    def __init__(self, content: str, **kwargs):
        super().__init__(
            content=content.encode(),
            media_type="application/xml",
            **kwargs
        )

@app.get("/xml")
async def get_xml():
    return XMLResponse("<root><message>Hello</message></root>")
```

---

For more examples and guides, see the [User Guide](GUIDE.md).
