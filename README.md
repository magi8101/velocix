# Velocix

<p align="center">
  <img src="docs/logo.png" alt="Velocix Logo" width="400">
</p>

<p align="center">
  <strong>A learning project where I rebuilt Starlette's core patterns to understand how modern async Python web frameworks work.</strong>
</p>

---

## What This Is

- A study project built during my B.Tech CSE studies
- Heavily inspired by Starlette's architecture and patterns
- An exercise in understanding ASGI and async Python
- A way to learn performance optimization concepts
- A minimal framework experiment

## What This Is NOT

- A production-ready framework
- Faster than existing solutions (FastAPI/Starlette)
- Something you should use instead of established frameworks
- A unique or groundbreaking implementation

## What I Learned

- How ASGI works under the hood
- Async Python patterns and best practices
- Why performance optimization requires actual measurement, not assumptions
- How routing, middleware, and request handling work internally
- That framework overhead is usually negligible compared to database queries and business logic
- The importance of honest benchmarking and documentation

---

## 📦 Installation

### Prerequisites
- Python 3.10 or higher
- pip

### Install from PyPI

```bash
pip install velocix
```

### Core Dependencies
- **orjson** - Fast JSON serialization
- **msgspec** - Fast validation and serialization
- **httptools** - HTTP request parsing
- Any ASGI server (uvicorn, granian, hypercorn)

---

## 🚀 Quick Start

```python
from velocix import Velocix
from velocix.core.response import JSONResponse

app = Velocix()

@app.get("/")
async def hello():
    return {"message": "Hello World"}

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"user_id": user_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 🏗️ Code Structure

```
velocix/
├── core/           # Core ASGI application and routing (based on Starlette patterns)
├── http/           # HTTP utilities
├── middleware/     # Middleware implementations
├── security/       # Authentication and security utilities
├── validation/     # Request validation (msgspec)
├── websocket/      # WebSocket support
├── monitoring/     # Health checks and metrics
└── testing/        # Test client utilities
```

---

## 📚 Documentation

- **[API Reference](docs/API_REFERENCE.md)** - Complete API documentation
- **[User Guide](docs/GUIDE.md)** - How to use Velocix features
- **[Security Guide](docs/SECURITY.md)** - Security best practices
- **[Internals](docs/INTERNALS.md)** - Architecture details

---

## 🤝 Contributing

This is a learning project, but if you find it useful or want to suggest improvements, feel free to open an issue or PR.

---

## 🙏 Acknowledgments

This project is heavily inspired by:
- **Starlette** - Most patterns and architecture are based on Starlette's design
- **FastAPI** - For the elegant decorator-based API
- **msgspec** - For fast validation
- **orjson** - For efficient JSON serialization

Special thanks to the authors of these frameworks for their excellent documentation and open-source code that made this learning project possible.

---

## 📖 Learning Resources

If you want to build something similar, I recommend:
- Reading Starlette's source code (it's very well written)
- Understanding the ASGI specification
- Studying async Python patterns
- Actually measuring performance instead of assuming optimizations work

---

## 📄 License

MIT License - See LICENSE file for details

---

**Built as a learning exercise by a CSE student**

*NOTE:This is an educational project with no affiliation to velocix ltd or any other comapnies using similar names*

*feel free to read src code any time and contribute*

*A minimal framework experiment - use Starlette or FastAPI for real projects.*
