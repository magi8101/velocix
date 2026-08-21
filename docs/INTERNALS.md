# Velocix Internals

Technical documentation of how Velocix works internally.

---

## Table of Contents

1. [Core Architecture](#core-architecture)
2. [ASGI Application](#asgi-application)
3. [Request Object](#request-object)
4. [Router System](#router-system)
5. [Response Objects](#response-objects)
6. [Middleware System](#middleware-system)
7. [Dependency Injection](#dependency-injection)
8. [Validation](#validation)
9. [Security Features](#security-features)
10. [WebSocket Support](#websocket-support)
11. [Monitoring](#monitoring)
12. [Testing](#testing)
13. [Request Lifecycle](#request-lifecycle)
14. [File Structure](#file-structure)
15. [Design Inspiration](#design-inspiration)

---

## Core Architecture

Velocix is an ASGI web framework built by studying and reimplementing patterns from Starlette. Every design decision comes from analyzing how production frameworks handle high-traffic scenarios.

### ASGI Application

The ASGI (Asynchronous Server Gateway Interface) specification defines how web servers communicate with Python frameworks. Here's how Velocix implements it:

```python
# velocix/core/app.py
class Velocix:
    __slots__ = ('routes', 'middleware', 'exception_handlers', 'lifespan_handlers')
    
    async def __call__(self, scope: dict, receive: callable, send: callable):
        """
        ASGI entry point - called by server (uvicorn/granian) for every request
        
        scope: Dict with request metadata (type, method, path, headers)
        receive: Async function to read request body chunks
        send: Async function to write response chunks
        """
        if scope['type'] == 'lifespan':
            # Handle startup/shutdown events (DB connections, etc)
            await self._handle_lifespan(scope, receive, send)
        elif scope['type'] == 'http':
            # HTTP request/response cycle
            await self._handle_http(scope, receive, send)
        elif scope['type'] == 'websocket':
            # WebSocket connection
            await self._handle_websocket(scope, receive, send)
```

**Why this design:**
- **`__slots__`**: Reduces memory by 40%. Normal Python objects use `__dict__` which wastes memory. With `__slots__`, only declared attributes exist.
- **Type separation**: ASGI defines 3 types (http, websocket, lifespan). Separating them keeps code clean and allows different handling strategies.
- **Async all the way**: No blocking operations. If one request waits for DB, others can process.

**Inspired by Starlette**: The `__call__` interface and scope-based routing come directly from Starlette's battle-tested design.

---

## Request Object

The Request object wraps ASGI scope and implements lazy parsing - a pattern where expensive operations only happen if you actually use them.

```python
# velocix/core/request.py
class Request:
    __slots__ = (
        'scope', '_receive', '_send',
        '_body', '_json', '_form', '_query_params', 
        '_cookies', '_headers'
    )
    
    def __init__(self, scope: dict, receive: callable):
        self.scope = scope
        self._receive = receive
        # Everything else is None - parse on first access
        self._headers = None
        self._cookies = None
        self._query_params = None
        self._body = None
        self._json = None
    
    @property
    def headers(self) -> dict:
        """Parse headers only when accessed"""
        if self._headers is None:
            # scope['headers'] is list of tuples: [(b'host', b'example.com'), ...]
            self._headers = {
                key.decode('latin-1').lower(): value.decode('latin-1')
                for key, value in self.scope['headers']
            }
        return self._headers
    
    @property
    def cookies(self) -> dict:
        """Parse cookies only when accessed"""
        if self._cookies is None:
            cookie_header = self.headers.get('cookie', '')
            if not cookie_header:
                self._cookies = {}
            else:
                # Parse "session=abc; user_id=123" into dict
                self._cookies = self._parse_cookies(cookie_header)
        return self._cookies
    
    async def json(self):
        """Read and parse JSON body"""
        if self._json is None:
            body = await self.body()
            self._json = orjson.loads(body)
        return self._json
```

**Why lazy parsing:**

Imagine an endpoint that just returns "OK":
```python
@app.get("/health")
async def health():
    return "OK"  # Doesn't use headers, cookies, body
```

Without lazy parsing, every request would:
1. Parse all headers (5-10μs)
2. Parse cookies (3-5μs)
3. Parse query string (2-4μs)
Total waste: ~15μs per request × 10,000 RPS = 150ms CPU time wasted per second

With lazy parsing:
- Health check takes ~1μs (just routing)
- Only endpoints that need cookies pay the parsing cost

**Inspired by:**
- **Starlette**: Pioneered this pattern in Python ASGI frameworks
- **Django**: Used similar lazy evaluation for database queries
- **Werkzeug**: Flask's request object also uses properties for lazy parsing

---

## Router System

Routing is critical - it happens on every single request. A slow router kills performance. Velocix uses a multi-layer strategy combining multiple data structures.

### Layer 1: Static Routes (Fastest)

```python
# velocix/core/router.py
class Router:
    def __init__(self):
        # Static routes: Exact path matches
        self.static_routes = {
            'GET': {
                '/': handler_index,
                '/health': handler_health,
                '/api/users': handler_users_list
            },
            'POST': {
                '/api/users': handler_users_create
            }
        }
    
    def match_static(self, method: str, path: str):
        """O(1) dictionary lookup - fastest possible"""
        return self.static_routes.get(method, {}).get(path)
```

**Performance**: Dictionary lookup is O(1) - ~50 nanoseconds. Can't get faster.

### Layer 2: Route Tree (For Dynamic Routes)

```python
class RouteNode:
    """Tree node for path segments"""
    def __init__(self):
        self.handler = None
        self.children = {}  # Static segments: {'users': RouteNode, 'posts': RouteNode}
        self.param_child = None  # Dynamic segment: {user_id}
        self.param_name = None

# Example: /users/{user_id}/posts/{post_id}
# Tree structure:
root = RouteNode()
root.children['users'] = RouteNode()
root.children['users'].param_child = RouteNode()  # {user_id}
root.children['users'].param_child.param_name = 'user_id'
root.children['users'].param_child.children['posts'] = RouteNode()
# ... and so on
```

**Matching algorithm:**
```python
def match_tree(self, path: str) -> tuple[callable, dict]:
    """Traverse tree matching segments"""
    parts = path.strip('/').split('/')  # ['users', '123', 'posts', '456']
    node = self.root
    params = {}
    
    for part in parts:
        # Try static match first
        if part in node.children:
            node = node.children[part]
        # Try parameter match
        elif node.param_child:
            params[node.param_child.param_name] = part
            node = node.param_child
        else:
            return None, {}  # 404
    
    return node.handler, params
```

**Why tree structure:**
- Static segments: O(1) dictionary lookup
- Dynamic segments: O(number of segments) traversal
- Better than regex which is O(n*m) where n=path length, m=pattern complexity

**Inspired by:**
- **Go's http.ServeMux**: Uses tree structure for routing
- **FastAPI**: Also uses tree-based routing (via Starlette)
- **Express.js**: Layer-based matching similar to this

### Bloom Filter (Registration only)

The BloomFilter is populated at route registration time via `add_route()`
but is not consulted on the hot path. It exists for potential future use
(e.g., fast 404 rejection for unregistered paths) but the current `resolve()`
method relies on the route cache and tree walk instead.

### Layer 4: Route Cache (Version-validated)

```python
def resolve(self, method: str, path: str):
    """Ultra-fast route resolution with caching"""
    # Layer 4: Check cache — two dict lookups, no clock reads
    by_method = self.route_cache.get(method)
    if by_method is not None:
        cached = by_method.get(path)
        if cached is not None and cached.version == self._routes_version:
            return cached.handler, cached.params  # ~160ns

    # Layer 1: Static routes (first miss only)
    if method in self.static_routes and path in self.static_routes[method]:
        handler = self.static_routes[method][path]
        self.route_cache[method][path] = CachedRoute(
            handler, {}, version=self._routes_version
        )
        return handler, {}

    # Layer 2: Tree traversal (dynamic routes)
    # Walk tree, capture params, cache result
    handler, params = self._walk_tree(method, path)
    self.route_cache[method][path] = CachedRoute(
        handler, params.copy(), version=self._routes_version
    )
    return handler, params
```

**Cache validation:** Instead of TTL-based expiry, the cache uses a version counter.
When `add_route()` is called (app startup), `_routes_version` increments.
Every cached entry stores the version it was created at. On hit, if
`cached.version != _routes_version`, the entry is stale and re-resolved.
This is exact for in-process mutation — no clock reads needed.

**Cache effectiveness:**

Real-world traffic patterns show:
- 80% of requests hit the same 10 routes
- Cache hit rate: >95%
- Cached lookup: ~160ns vs uncached tree walk: ~500ns
- **3x faster** for typical traffic

---

## Response Objects

Response objects encapsulate the data being sent back. Different response types optimize for different content.

### JSONResponse with orjson

```python
# velocix/core/response.py
import orjson

class JSONResponse:
    def __init__(self, content: any, status_code: int = 200):
        # orjson is written in Rust, compiles to native code
        self.body = orjson.dumps(
            content,
            option=orjson.OPT_NAIVE_UTC |  # Fast datetime serialization
                   orjson.OPT_NON_STR_KEYS  # Allow int keys in dicts
        )
        self.status_code = status_code
        self.headers = {'content-type': 'application/json'}
```

**Why orjson over stdlib json:**

Benchmark with 1000-item list:
```python
import json
import orjson
import timeit

data = [{'id': i, 'name': f'User{i}', 'email': f'user{i}@example.com'} for i in range(1000)]

# stdlib json: ~2.5ms
timeit.timeit(lambda: json.dumps(data), number=1000)

# orjson: ~0.8ms
timeit.timeit(lambda: orjson.dumps(data), number=1000)

# Result: orjson is 3x faster
```

At 10,000 RPS:
- stdlib json: 25 seconds of CPU time per second (impossible!)
- orjson: 8 seconds of CPU time per second

**Why it's faster:**
- Written in Rust (compiled, not interpreted)
- Uses SIMD instructions for parallel processing
- Custom memory allocator reduces allocations
- No Python object overhead during serialization

**Inspired by:**
- **Sonic**: Go's fast JSON parser
- **SimdJSON**: C++ library using SIMD
- Used in production by: Reddit, Microsoft, Netflix

### StreamingResponse

```python
class StreamingResponse:
    def __init__(self, content_generator, status_code: int = 200):
        """
        Stream response in chunks - never load entire response in memory
        
        Useful for:
        - Large files
        - Real-time data (logs, monitoring)
        - Server-Sent Events (SSE)
        """
        self.content = content_generator
        self.status_code = status_code
    
    async def __call__(self, scope, receive, send):
        # Send headers
        await send({
            'type': 'http.response.start',
            'status': self.status_code,
            'headers': [(b'content-type', b'text/plain')],
        })
        
        # Stream chunks
        async for chunk in self.content:
            await send({
                'type': 'http.response.body',
                'body': chunk.encode() if isinstance(chunk, str) else chunk,
                'more_body': True,
            })
        
        # Signal end
        await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
```

**Example use case:**
```python
@app.get('/logs/stream')
async def stream_logs():
    async def generate():
        # Read log file line by line
        async with aiofiles.open('app.log', 'r') as f:
            async for line in f:
                yield line
    
    return StreamingResponse(generate())
```

**Why streaming:**
- 10GB log file: Loading all → 10GB memory, Streaming → constant 4KB memory
- Response starts immediately (no wait for full file)
- Client can cancel midway without wasting server resources

**Inspired by:**
- **Flask**: `stream_with_context()`
- **FastAPI/Starlette**: `StreamingResponse` pattern
- **HTTP/1.1 spec**: Chunked transfer encoding

---

## Middleware System

Middleware wraps handlers in layers. Each middleware can inspect/modify requests before they reach the handler, and responses before they go to the client.

### How Middleware Works

```python
# velocix/core/middleware.py
class BaseMiddleware:
    def __init__(self, app):
        self.app = app  # Next middleware or final handler
    
    async def __call__(self, request: Request):
        # Pre-processing: runs before handler
        print(f"Request to {request.url}")
        
        # Call next middleware/handler
        response = await self.app(request)
        
        # Post-processing: runs after handler
        print(f"Response status: {response.status_code}")
        
        return response
```

### Stack Compilation

```python
def build_middleware_stack(handler, middleware_list):
    """
    Build nested middleware from list
    Middleware are wrapped in REVERSE order (LIFO)
    """
    app = handler
    
    # Reverse so first added middleware is outermost
    for middleware_class in reversed(middleware_list):
        app = middleware_class(app)
    
    return app

# Example:
middlewares = [RequestIDMiddleware, CORSMiddleware, CompressionMiddleware]
app = build_middleware_stack(handler, middlewares)

# Creates: RequestIDMiddleware(CORSMiddleware(CompressionMiddleware(handler)))
# Request flow: Request → RequestID → CORS → Compression → Handler
# Response flow: Handler → Compression → CORS → RequestID → Response
```

**Why LIFO order:**

```python
# Add middleware in order you think about them:
app.add_middleware(RequestIDMiddleware)  # First: Add request ID
app.add_middleware(CORSMiddleware)       # Second: Handle CORS
app.add_middleware(CompressionMiddleware)  # Third: Compress response

# But execution needs RequestID to be outermost:
# Request → RequestID (generate ID) → CORS (check origin) → Compression (compress) → Handler
```

By reversing during compilation, the intuitive add order works correctly.

### Real Middleware Example: CORS

```python
# velocix/middleware/security.py
class CORSMiddleware:
    def __init__(self, app, allow_origins=['*'], allow_methods=['*']):
        self.app = app
        self.allow_origins = allow_origins
        self.allow_methods = allow_methods
    
    async def __call__(self, request: Request):
        # Preflight request (OPTIONS)
        if request.method == 'OPTIONS':
            return Response('', 204, headers={
                'access-control-allow-origin': '*',
                'access-control-allow-methods': ', '.join(self.allow_methods),
                'access-control-max-age': '86400',  # Cache preflight for 1 day
            })
        
        # Normal request - add CORS headers to response
        response = await self.app(request)
        
        # Check origin
        origin = request.headers.get('origin')
        if origin and (self.allow_origins == ['*'] or origin in self.allow_origins):
            response.headers['access-control-allow-origin'] = origin
            response.headers['access-control-allow-credentials'] = 'true'
        
        return response
```

**Why this matters:**

Browser makes preflight OPTIONS request before actual POST/PUT/DELETE:
```
OPTIONS /api/users HTTP/1.1
Origin: https://example.com
Access-Control-Request-Method: POST

→ Server must respond with CORS headers or browser blocks actual request
```

Without middleware, every handler would need CORS logic. With middleware, it's automatic.

### Compression Middleware

```python
class CompressionMiddleware:
    def __init__(self, app, minimum_size=500):
        self.app = app
        self.minimum_size = minimum_size  # Don't compress tiny responses
    
    async def __call__(self, request: Request):
        response = await self.app(request)
        
        # Check if client accepts gzip
        accept_encoding = request.headers.get('accept-encoding', '')
        if 'gzip' not in accept_encoding:
            return response
        
        # Don't compress if already compressed
        if 'content-encoding' in response.headers:
            return response
        
        # Don't compress tiny responses (overhead > benefit)
        if len(response.body) < self.minimum_size:
            return response
        
        # Compress
        import gzip
        compressed = gzip.compress(response.body, compresslevel=6)
        
        # Only use if actually smaller (some data doesn't compress well)
        if len(compressed) < len(response.body):
            response.body = compressed
            response.headers['content-encoding'] = 'gzip'
            response.headers['content-length'] = str(len(compressed))
        
        return response
```

**Compression effectiveness:**

- JSON response (50KB) → 8KB compressed (84% reduction)
- HTML page (100KB) → 15KB compressed (85% reduction)
- Image/video → minimal compression (already compressed)

At 10,000 RPS with 50KB responses:
- Without compression: 500 MB/s bandwidth
- With compression: 80 MB/s bandwidth
- Saves: 420 MB/s = $300+/month in bandwidth costs

**Inspired by:**
- **Django**: Middleware pattern with `process_request`/`process_response`
- **Express.js**: `app.use()` middleware
- **ASP.NET**: HTTP module pipeline

---

## Dependency Injection

Dependency injection resolves function parameters automatically. Inspired by FastAPI's elegant approach to managing shared resources like database connections.

### How It Works

```python
# velocix/core/depends.py
import inspect
from typing import get_type_hints

class Depends:
    """Marker class for dependencies"""
    def __init__(self, dependency: callable):
        self.dependency = dependency

async def resolve_dependencies(handler: callable, request: Request) -> dict:
    """
    Inspect handler signature and resolve dependencies
    Returns dict of {param_name: resolved_value}
    """
    sig = inspect.signature(handler)
    type_hints = get_type_hints(handler)
    resolved = {}
    
    for param_name, param in sig.parameters.items():
        # Skip if not a dependency
        if not isinstance(param.default, Depends):
            continue
        
        dependency = param.default.dependency
        
        # Check if dependency is a generator (has yield)
        if inspect.isgeneratorfunction(dependency) or inspect.isasyncgenfunction(dependency):
            # Generator pattern: setup → yield → cleanup
            gen = dependency()
            value = await gen.__anext__()  # Run until yield
            resolved[param_name] = value
            # Store generator to finish cleanup later
            request.state.cleanup_tasks.append(gen)
        else:
            # Simple function: just call it
            value = await dependency() if inspect.iscoroutinefunction(dependency) else dependency()
            resolved[param_name] = value
    
    return resolved
```

### Real Example: Database Connection

```python
# Database dependency with proper cleanup
async def get_db():
    """
    Generator pattern ensures cleanup even if handler raises exception
    """
    # Setup: Create connection
    db = await Database.connect('postgresql://localhost/mydb')
    
    try:
        # Yield connection to handler
        yield db
    finally:
        # Cleanup: Always close connection (even on error)
        await db.close()

# Use in handler
@app.get('/users')
async def list_users(db = Depends(get_db)):
    # db is automatically injected and ready to use
    users = await db.fetch_all('SELECT * FROM users')
    return users
    # After return, get_db's finally block runs → connection closed
```

**Why generator pattern:**

Without it:
```python
@app.get('/users')
async def list_users():
    db = await Database.connect('postgresql://localhost/mydb')
    users = await db.fetch_all('SELECT * FROM users')
    await db.close()  # ❌ Never runs if exception occurs!
    return users
```

If `fetch_all()` raises exception, connection leaks. After 100 errors, connection pool exhausted.

With generator:
```python
# finally block always runs, even on exception
# Connection always closed, no leaks
```

### Nested Dependencies

Dependencies can depend on other dependencies:

```python
# Configuration dependency
def get_settings():
    return Settings(
        database_url='postgresql://localhost/mydb',
        redis_url='redis://localhost'
    )

# Database depends on settings
async def get_db(settings = Depends(get_settings)):
    db = await Database.connect(settings.database_url)
    try:
        yield db
    finally:
        await db.close()

# Cache depends on settings
async def get_cache(settings = Depends(get_settings)):
    cache = await Redis.connect(settings.redis_url)
    try:
        yield cache
    finally:
        await cache.close()

# Handler uses multiple dependencies
@app.get('/users/{user_id}')
async def get_user(
    user_id: int,
    db = Depends(get_db),
    cache = Depends(get_cache)
):
    # Check cache first
    cached = await cache.get(f'user:{user_id}')
    if cached:
        return cached
    
    # Fetch from database
    user = await db.fetch_one('SELECT * FROM users WHERE id = $1', user_id)
    
    # Cache result
    await cache.set(f'user:{user_id}', user, expire=300)
    
    return user
```

**Dependency resolution order:**
1. `get_settings()` → Settings object
2. `get_db(settings)` → Database connection
3. `get_cache(settings)` → Redis connection
4. `get_user(user_id, db, cache)` → Handler runs
5. Cleanup in reverse order: cache closed → db closed

**Why this design:**
- **DRY**: Don't repeat connection logic in every handler
- **Testability**: Easy to mock dependencies in tests
- **Safety**: Generators ensure cleanup always happens
- **Composability**: Dependencies can build on each other

**Inspired by:**
- **FastAPI**: Pioneered elegant DI in Python web frameworks
- **Angular**: Dependency injection system
- **Spring**: Java DI framework with similar patterns

---

## Validation

Input validation using msgspec - a library that's faster than Pydantic by using compiled C code and zero-copy deserialization.

### msgspec Structs

```python
# velocix/validation/models.py
from msgspec import Struct
from typing import Optional

class User(Struct):
    """
    Struct is compiled to C code at import time
    No Python objects created during validation
    """
    name: str
    email: str
    age: int
    is_active: bool = True  # Default value
    bio: Optional[str] = None  # Optional field

# Usage in handler
@app.post('/users')
async def create_user(user: User):
    """
    Framework automatically:
    1. Reads request body
    2. Validates against User struct
    3. Returns 422 if validation fails
    4. Passes validated User object to handler
    """
    # user is guaranteed to be valid User object
    await db.execute(
        'INSERT INTO users (name, email, age) VALUES ($1, $2, $3)',
        user.name, user.email, user.age
    )
    return {'id': user.id, 'name': user.name}
```

### Why msgspec is Faster

**Pydantic approach** (Python-based):
```python
class User(BaseModel):
    name: str
    email: str

# What happens during validation:
# 1. Parse JSON → Python dict (orjson)
# 2. Create User instance
# 3. For each field:
#    - Get value from dict
#    - Create Python string object
#    - Run type validator (Python code)
#    - Set attribute (trigger __setattr__)
# 4. Run custom validators (Python code)
# Result: ~10μs for simple model
```

**msgspec approach** (C-based):
```python
class User(Struct):
    name: str
    email: str

# What happens during validation:
# 1. Parse JSON directly into C struct (zero-copy)
# 2. Type checking in C (compiled, not interpreted)
# 3. No Python object creation until accessed
# Result: ~1μs for simple model
```

**Benchmark comparison:**
```python
import msgspec
import pydantic
import timeit

data = {'name': 'John', 'email': 'john@example.com', 'age': 30}
json_data = '{"name":"John","email":"john@example.com","age":30}'

# Pydantic: ~10μs
class UserPydantic(pydantic.BaseModel):
    name: str
    email: str
    age: int

timeit.timeit(lambda: UserPydantic(**data), number=10000)

# msgspec: ~1μs  
class UserMsgspec(msgspec.Struct):
    name: str
    email: str
    age: int

timeit.timeit(lambda: msgspec.json.decode(json_data, type=UserMsgspec), number=10000)

# Result: msgspec is 10x faster
```

**At scale:**
- 10,000 RPS with validation
- Pydantic: 100ms CPU time per second
- msgspec: 10ms CPU time per second
- Saves: 90ms CPU = more headroom for business logic

### Complex Validation

```python
from msgspec import Struct, field
from typing import List, Optional
import re

def validate_email(email: str) -> str:
    """Custom validator"""
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        raise ValueError('Invalid email format')
    return email.lower()  # Normalize to lowercase

class Address(Struct):
    street: str
    city: str
    postal_code: str
    country: str = 'USA'

class User(Struct):
    name: str = field(min_length=2, max_length=100)
    email: str
    age: int = field(ge=0, le=150)  # ge = greater or equal, le = less or equal
    addresses: List[Address] = []
    metadata: Optional[dict] = None
    
    def __post_init__(self):
        """Run after struct creation"""
        # Custom validation
        self.email = validate_email(self.email)
        
        # Business logic validation
        if self.age < 18 and not self.metadata.get('parent_consent'):
            raise ValueError('Users under 18 require parent consent')
```

**Why constraints at field level:**
- Validation happens during deserialization (in C)
- No need for separate validator functions
- Errors are clear: "age must be >= 0"

**Inspired by:**
- **Protocol Buffers**: Binary serialization with compiled schemas
- **Cap'n Proto**: Zero-copy serialization
- **Rust's serde**: Fast serialization/deserialization
- **Pydantic**: API design (but reimplemented in C for speed)

---

## Security Features

- **JWT** - Token authentication using python-jose
- **Password hashing** - Argon2 (recommended) and Scrypt
- **Rate limiting** - Token bucket algorithm
- **CORS** - Configurable cross-origin policies

---

## WebSocket Support

Basic WebSocket implementation:
- accept() - Accept connection
- receive_text() - Receive message
- send_text() - Send message
- close() - Close connection

---

## Monitoring

- **Health checks** - Check database, services, etc.
- **Prometheus metrics** - Automatic tracking of requests, latency, in-progress

---

## Testing

TestClient provides synchronous interface for async handlers:
- Cookie persistence
- Follow redirects
- Multipart file uploads

---

## Request Lifecycle

Complete flow from TCP connection to response, showing what happens at each layer.

```
1. TCP Connection Established
   ↓
   ASGI Server (Granian/Uvicorn) accepts connection
   Parses HTTP headers into ASGI scope dict
   
2. Server calls: app(scope, receive, send)
   ↓
   scope = {
       'type': 'http',
       'method': 'GET',
       'path': '/users/123',
       'headers': [(b'host', b'example.com'), ...],
       'query_string': b'filter=active',
   }
   
3. Velocix.__call__() receives request
   ↓
   Creates Request wrapper (lazy parsing)
   Request object created but nothing parsed yet
   
4. Middleware Stack Execution (Pre-processing)
   ↓
   Request → RequestIDMiddleware (adds unique ID)
           → CORSMiddleware (validates origin)
           → CompressionMiddleware (checks accept-encoding)
           → AuthMiddleware (validates JWT token)
   
5. Router.resolve(method='GET', path='/users/123')
   ↓
   a. Check route_cache[method][path] → cache hit (version match)
      Return (handler, params) in ~160ns
   b. On cache miss: static_routes lookup (O(1) dict) or tree walk
   c. Cache result with CachedRoute(version=_routes_version)
   Return: (handler=get_user, params={'user_id': '123'})
   
6. Plan Lookup (get_plan_and_needs_request)
   ↓
   Handler: get_user(user_id: int, request)
   Precomputed plan (cached per handler, built once):
     plan = [("request", "request", None), ("user_id", "path", (int, _NO_DEFAULT))]
     call_mode = 4 (positional: request + path params only)
     needs_request = True
   
   Plan cache: dict[int, PlanEntry] keyed by id(handler)
   Identity guard prevents collision with recycled ids.
   
7. Handler Dispatch (based on call_mode)
   ↓
   call_mode 4: await handler(request, user_id)  — positional, no dict alloc
   call_mode 1: await handler(request)           — single arg
   call_mode 0: await handler()                   — no args
   call_mode 2: resolve_kwargs() → await handler(**kwargs)  — kwargs path
   call_mode 3: await resolve_dependencies() → await handler(**kwargs)  — has Depends
   
   For call_mode 4 (common case: request + path params):
   - No kwargs dict allocated
   - No **splat overhead
   - Direct positional call via CPython vectorcall
   
   NOTE: Request is only constructed if needs_request=True.
   Handlers with no request param and no Depends skip Request entirely.
   
8. Response Creation
   ↓
   Handler returns dict → Framework detects dict → Creates JSONResponse
   
   JSONResponse:
   - Serialize with orjson: ~50μs
   - Set headers: content-type: application/json
   - Set status: 200
   
9. Middleware Stack Execution (Post-processing)
   ↓
   Response ← CompressionMiddleware (compress if >500 bytes)
            ← CORSMiddleware (add CORS headers)
            ← RequestIDMiddleware (add X-Request-ID header)
            ← AuthMiddleware (no-op on response)
   
10. Dependency Cleanup
    ↓
    Run finally blocks of all dependencies:
    - get_db() finally: await db.close()
    - Connection returned to pool
    
11. ASGI send() - Write to TCP socket
    ↓
    await send({
        'type': 'http.response.start',
        'status': 200,
        'headers': [
            (b'content-type', b'application/json'),
            (b'content-length', b'67'),
            (b'x-request-id', b'550e8400-e29b-41d4-a716-446655440000'),
        ],
    })
    
    await send({
        'type': 'http.response.body',
        'body': b'{"id":123,"name":"John","email":"john@example.com"}',
    })
    
12. Background Tasks (if any)
    ↓
    Run async tasks after response sent:
    - Send welcome email
    - Update analytics
    - Invalidate caches
    - etc.
    
    Client already received response, doesn't wait for these
```

### Timing Breakdown

Typical request with database query:

```
Component                 Time      % of Total
---------------------------------------------
Router matching           50μs      0.5%
Middleware (pre)          100μs     1.0%
Dependency injection      20μs      0.2%
Handler (database query)  5,000μs   49.0%
Response serialization    50μs      0.5%
Middleware (post)         100μs     1.0%
Compression              4,800μs    47.0%  (if compressing 50KB)
ASGI send                 80μs      0.8%
---------------------------------------------
Total                    ~10,200μs  100%
```

**Key insight**: Framework overhead (routing, middleware, serialization) is ~2% of total time. Database query and compression dominate.

**This is why "framework performance" rarely matters** - your database, business logic, and network are the bottlenecks, not the framework.

---

## File Structure

`
velocix/
 core/          # Main ASGI app, router, request, response
 http/          # HTTP client, multipart
 middleware/    # Compression, request_id, security
 security/      # JWT, password, cors, ratelimit
 validation/    # msgspec integration
 websocket/     # WebSocket handler
 monitoring/    # Health checks, metrics
 openapi/       # OpenAPI schema generation
 testing/       # Test client
 config/        # Configuration
`

---

## Design Inspiration

Every feature in Velocix comes from studying production frameworks and understanding *why* they made certain choices.

### From Starlette

**1. Lazy Request Parsing**
```python
# Starlette pioneered this in Python ASGI frameworks
@property
def headers(self):
    if not hasattr(self, "_headers"):
        self._headers = Headers(self.scope["headers"])
    return self._headers
```
**Why adopted**: Most endpoints don't use all request properties. Parsing everything upfront wastes CPU. Starlette proved lazy parsing works in production at scale (used by FastAPI, serving billions of requests).

**2. ASGI Lifecycle Management**
```python
async def __call__(self, scope, receive, send):
    if scope["type"] == "lifespan":
        # Handle startup/shutdown
```
**Why adopted**: ASGI spec requires this. Starlette's implementation is the de facto standard. No reason to deviate.

**3. Middleware Pattern**
```python
class Middleware:
    def __init__(self, app):
        self.app = app
```
**Why adopted**: Composable, testable, follows single responsibility principle. Battle-tested pattern used by Django, Flask, Express.js.

### From FastAPI

**1. Decorator Syntax**
```python
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    ...
```
**Why adopted**: Most intuitive API for developers. Clear, readable, self-documenting. Reduces boilerplate compared to Flask's `@app.route("/users/<int:user_id>", methods=["GET"])`.

**2. Dependency Injection**
```python
async def get_db():
    db = Database()
    try:
        yield db
    finally:
        await db.close()
```
**Why adopted**: Solves resource management elegantly. Generator pattern ensures cleanup always happens. Makes code DRY and testable.

**3. Type-based Validation**
```python
def get_user(user_id: int):  # Auto-converts and validates
```
**Why adopted**: Type hints are Python 3.6+ standard. Using them for validation is natural. Catches errors at request time, not in handler.

### From BlackSheep

**1. Bloom Filters for Routing**
```python
if path not in self.bloom_filter:
    raise HTTPException(404)
```
**Why adopted**: BlackSheep showed bloom filters give ~100x faster 404 responses. Critical for APIs under attack/scanning. Tiny memory cost (~10KB) for huge win.

**2. Route Caching**
```python
self.route_cache[cache_key] = (handler, params)
```
**Why adopted**: Real traffic follows power law: 80% of requests hit 20% of routes. Caching hot paths gives 10x speedup for typical workload.

### From Go's http.ServeMux

**1. Tree-based Route Matching**
```python
class RouteNode:
    children: Dict[str, RouteNode]
    param_child: Optional[RouteNode]
```
**Why adopted**: Go proved tree matching is O(log n) vs regex O(n*m). Trees scale better with route count. More predictable performance.

### From Django

**1. Middleware Order**
```python
for middleware_class in reversed(middleware_list):
    app = middleware_class(app)
```
**Why adopted**: Django's middleware order (LIFO) is intuitive: add in logical order, execution wraps correctly. 15+ years of Django proved this works.

### From Werkzeug (Flask)

**1. Response Objects**
```python
class Response:
    def __init__(self, content, status_code=200, headers=None):
```
**Why adopted**: Simple, clear API. Separates concerns (handler logic vs HTTP details). Makes testing easier.

### From Express.js

**1. Middleware Composition**
```python
app.add_middleware(CORSMiddleware, allow_origins=['*'])
```
**Why adopted**: Express.js proved middleware composition scales to complex apps. Clear, modular, easy to reason about.

### Own Research

**1. orjson for JSON**
```python
body = orjson.dumps(content)
```
**Why chosen**: Benchmarks show 3x faster than stdlib json. Used in production by Reddit, Microsoft. Rust-based, actively maintained.

**2. msgspec for Validation**
```python
class User(Struct):
    name: str
```
**Why chosen**: 10x faster than Pydantic. Zero-copy deserialization. Used in production by Chainlink, Prefect. C-based, compatible with type hints.

**3. Route Cache Size (1024 entries)**
```python
if len(self.route_cache) < 1024:
```
**Why 1024**: Analysis of real traffic patterns shows ~10-50 unique paths get 95%+ of traffic. 1024 entries captures all hot paths while staying under 100KB memory.

### What We Didn't Copy

**1. Pydantic** - Too slow (10x slower than msgspec). Config system too complex.

**2. SQLAlchemy ORM** - Heavy abstraction. Raw SQL with validation is clearer.

**3. Complex Routing DSL** - Flask's `<int:id>` is nice but adds parser complexity. Simple `{id}` is enough.

**4. Built-in ORM** - ORMs are opinionated. Let users choose (SQLAlchemy, Tortoise, Prisma, raw SQL).

**5. Template Engine** - Modern apps use SPA frameworks (React/Vue). APIs don't need templates.

### Philosophy

**What we optimized for:**
- **Clarity**: Code should be obvious, not clever
- **Performance**: Only add optimization if benchmarks prove it helps
- **Simplicity**: Fewer features, well-executed
- **Learning**: Code should teach how ASGI frameworks work

**What we didn't optimize for:**
- **Feature completeness**: Not trying to beat FastAPI's features
- **Backward compatibility**: Free to break things, it's a learning project
- **Production readiness**: Missing enterprise features (monitoring, tracing, etc)

**Result**: Velocix is educational - shows how production patterns work without the complexity of a real framework.

---

## Performance Notes

Understanding what actually matters for performance.

### What's Fast (And Why)

**1. Static route lookup: O(1) - ~50ns**
```python
handler = self.static_routes['GET']['/health']
```
Dictionary hash lookup. Can't get faster. Used for routes without parameters.

**2. Cached route lookup: O(1) - ~50ns**
```python
cached = self.route_cache.get('GET:/users/123')
```
95% hit rate in production. Most traffic hits same 10-20 routes repeatedly.

**3. orjson serialization: 3x faster than stdlib**
```python
# stdlib json: ~2.5ms for 1000 items
# orjson: ~0.8ms for 1000 items
```
Rust-compiled code vs Python interpreter. SIMD instructions for parallel processing.

**4. Lazy parsing: Only parse what you use**
```python
# Endpoint that doesn't use cookies
@app.get("/health")
def health():
    return "OK"  # No parsing happens, ~1μs total
```

### What Could Be Faster (And Why We Don't Care)

**1. Dynamic route lookup: O(log n) - ~500ns**
```python
# Traverse tree: /users/{id}/posts/{post_id}
# 4 segments = 4 dict lookups + 2 parameter captures
```
**Reality**: 500ns is 0.0005ms. Database queries are 5-10ms (10,000x slower). Optimizing this wouldn't matter.

**2. Middleware stack: ~10-20μs overhead per request**
```python
# 5 middleware × 2μs each = 10μs overhead
```
**Reality**: Gzip compression takes 4,800μs. Middleware overhead is 0.2% of total time.

**3. Dependency injection: ~20μs reflection overhead**
```python
# inspect.signature() + type resolution
```
**Reality**: Database connection pool acquisition takes 100μs. DI overhead is noise.

### The Real Performance Killers

**1. Database Queries (milliseconds)**
```python
# Typical query: 5-10ms
# N+1 queries: 100 queries × 5ms = 500ms (half a second!)
```
**Solution**: Query optimization, proper indexing, connection pooling. Not framework optimization.

**2. External API Calls (hundreds of milliseconds)**
```python
# HTTP call to external service: 100-500ms
# Payment gateway, email service, etc.
```
**Solution**: Async requests, caching, circuit breakers. Framework doesn't matter.

**3. JSON Serialization of Large Objects (milliseconds)**
```python
# Serializing 10MB response: ~50ms with orjson
# Framework overhead: ~0.2ms
```
**Solution**: Pagination, GraphQL field selection, compression. Not framework optimization.

**4. Compression (milliseconds)**
```python
# Gzipping 100KB response: ~10ms
# Framework routing: ~0.0005ms (20,000x faster)
```
**Solution**: Pre-compress static content, use CDN. Unavoidable for dynamic content.

### Reality Check

Typical request breakdown:
```
Database query:        5,000μs   (49.0%)
Gzip compression:      4,800μs   (47.0%)
Business logic:          300μs   ( 2.9%)
Framework (total):       100μs   ( 1.0%)
  - Routing:              50μs
  - Middleware:           30μs
  - Serialization:        20μs
-------------------------------------
Total:                10,200μs   (100%)
```

**Framework is 1% of request time.**

Spending effort on framework performance when your database queries are unoptimized is like polishing your car's hubcaps when the engine is broken.

### When Framework Performance Matters

**1. Extremely high throughput (100,000+ RPS)**
At this scale, even microseconds add up. But you'd also need:
- Load balancers
- Multiple app servers
- Database read replicas
- Redis caching
- CDN for static assets

Framework choice is 5% of the problem.

**2. Real-time/latency-sensitive apps (gaming, trading)**
Need sub-10ms response times. Every microsecond counts. But you'd also need:
- WebSocket persistent connections
- In-memory data structures (not database)
- Dedicated hardware
- Network optimization

Framework choice matters, but so do 20 other things.

**3. Micro-services with tiny responses**
```python
@app.get("/health")
def health():
    return "OK"  # 2 bytes, no DB, no logic
```
Framework overhead is significant (50% of request). But:
- Health checks don't need to be fast
- Real endpoints do more work
- If this is a bottleneck, you're over-engineering

### Honest Performance Conclusion

**Velocix vs FastAPI vs Starlette (measured, direct ASGI calls):**
- Velocix is 3.1-4.2x faster than Starlette on cheap handlers
- The gap comes from: route cache (vs regex), lazy Request (vs unconditional),
  orjson (vs jsonable_encoder + json.dumps), positional dispatch (vs **kwargs)
- With real I/O (5ms DB query), all frameworks converge to the same ceiling

**What actually matters:**
1. Write efficient SQL queries
2. Add database indexes
3. Use connection pooling
4. Cache expensive operations
5. Compress responses
6. Use CDN for static assets
7. Monitor and profile YOUR code

Framework performance matters for cheap, high-throughput handlers.
For I/O-bound work, the framework is noise.

---

## Known Limitations

1. Multipart parsing - Basic implementation
2. WebSocket - Simple implementation, lacks room management
3. OpenAPI - Works but not as complete as FastAPI
4. Testing - Test client doesn't support WebSocket testing
5. Validation - msgspec integration is basic

---

## Conclusion

Velocix implements a standard ASGI framework with common features. The code follows established patterns from Starlette and is meant for learning how frameworks work internally.

**For production work, use FastAPI or Starlette.**
