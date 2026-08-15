"""Simplified OpenAPI interface with decorator-style syntax"""

from typing import Any

from .decorators import operation as _operation
from .decorators import parameter as _parameter
from .decorators import response as _response
from .generator import OpenAPIGenerator
from .models import ParameterIn


# Simplified decorators with automatic defaults
def get(
    path: str,
    summary: str | None = None,
    tags: list[str] | None = None,
    response_model: type[Any] | None = None,
):
    """GET decorator with automatic OpenAPI generation"""

    def decorator(func):
        # Auto-generate summary from function name if not provided
        if not summary:
            func_summary = func.__name__.replace("_", " ").title()
        else:
            func_summary = summary

        # Apply operation decorator
        decorated = _operation(summary=func_summary, tags=tags or [])(func)

        # Add default 200 response
        if response_model:
            decorated = _response(200, "Success", schema={"type": "object"})(decorated)
        else:
            decorated = _response(200, "Success")(decorated)

        return decorated

    return decorator


def patch(
    path: str,
    summary: str | None = None,
    tags: list[str] | None = None,
    response_model: type[Any] | None = None,
):
    """PATCH decorator with automatic OpenAPI generation"""

    def decorator(func):
        # Auto-generate summary from function name if not provided
        if not summary:
            func_summary = func.__name__.replace("_", " ").title()
        else:
            func_summary = summary

        # Apply operation decorator
        decorated = _operation(summary=func_summary, tags=tags or [])(func)

        # Add default 200 response
        if response_model:
            decorated = _response(200, "Success", schema={"type": "object"})(decorated)

        return decorated

    return decorator


def post(
    path: str,
    summary: str | None = None,
    tags: list[str] | None = None,
    response_model: type[Any] | None = None,
):
    """Velocix-style POST decorator"""

    def decorator(func):
        if not summary:
            func_summary = func.__name__.replace("_", " ").title()
        else:
            func_summary = summary

        decorated = _operation(summary=func_summary, tags=tags or [])(func)

        if response_model:
            decorated = _response(201, "Created", schema={"type": "object"})(decorated)
        else:
            decorated = _response(201, "Created")(decorated)

        return decorated

    return decorator


def put(
    path: str,
    summary: str | None = None,
    tags: list[str] | None = None,
    response_model: type[Any] | None = None,
):
    """Velocix-style PUT decorator"""

    def decorator(func):
        if not summary:
            func_summary = func.__name__.replace("_", " ").title()
        else:
            func_summary = summary

        decorated = _operation(summary=func_summary, tags=tags or [])(func)

        decorated = _response(200, "Success")(decorated)
        return decorated

    return decorator


def delete(path: str, summary: str | None = None, tags: list[str] | None = None):
    """Velocix-style DELETE decorator"""

    def decorator(func):
        if not summary:
            func_summary = func.__name__.replace("_", " ").title()
        else:
            func_summary = summary

        decorated = _operation(summary=func_summary, tags=tags or [])(func)

        decorated = _response(204, "Deleted")(decorated)
        return decorated

    return decorator


# Path parameter helper
def Path(description: str = "", example: Any = None):
    """Velocix-style Path parameter"""

    def wrapper(func):
        import inspect

        sig = inspect.signature(func)
        for param_name in sig.parameters:
            func = _parameter(
                param_name,
                ParameterIn.PATH,
                description=description or f"Path parameter {param_name}",
                required=True,
                example=example,
            )(func)
        return func

    return wrapper


# Query parameter helper
def Query(default: Any = None, description: str = "", example: Any = None):
    """Velocix-style Query parameter"""

    def wrapper(func):
        import inspect

        sig = inspect.signature(func)
        for param_name in sig.parameters:
            func = _parameter(
                param_name,
                ParameterIn.QUERY,
                description=description or f"Query parameter {param_name}",
                required=default is None,
                example=example or default,
            )(func)
        return func

    return wrapper


# Body parameter helper
def Body(description: str = "Request body", example: Any = None):
    """Velocix-style Body parameter"""

    def wrapper(func):
        from .decorators import request_body

        return request_body(
            description=description,
            schema={"type": "object", "example": example} if example else {"type": "object"},
        )(func)

    return wrapper


# Response helper
def responses(**status_responses):
    """Velocix-style multiple responses"""

    def wrapper(func):
        for status_code, response_data in status_responses.items():
            if isinstance(response_data, str):
                func = _response(status_code, response_data)(func)
            elif isinstance(response_data, dict):
                func = _response(
                    status_code,
                    response_data.get("description", "Response"),
                    schema=response_data.get("model"),
                )(func)
        return func

    return wrapper


# Tags helper
def tags(*tag_names: str):
    """Velocix-style tags"""

    def wrapper(func):
        return _operation(tags=list(tag_names))(func)

    return wrapper


# Complete Velocix-style app setup
class VelocixStyleDocs:
    """Velocix-style documentation setup"""

    def __init__(
        self,
        title: str = "Velocix",
        description: str | None = None,
        version: str = "0.1.0",
        openapi_url: str = "/openapi.json",
        docs_url: str = "/docs",
        redoc_url: str = "/redoc",
    ):
        self.generator = OpenAPIGenerator(title=title, version=version, description=description)
        self.openapi_url = openapi_url
        self.docs_url = docs_url
        self.redoc_url = redoc_url

    def setup_docs(self, router):
        """Setup documentation routes on router"""
        from .generator import setup_docs_routes

        setup_docs_routes(router, self.generator)


# Convenience function for quick setup
def create_docs(
    title: str = "API", description: str | None = None, version: str = "1.0.0"
) -> VelocixStyleDocs:
    """Create Velocix-style docs with minimal setup"""
    return VelocixStyleDocs(title=title, description=description, version=version)


# Export commonly used items
__all__ = [
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "Path",
    "Query",
    "Body",
    "responses",
    "tags",
    "VelocixStyleDocs",
    "create_docs",
]
