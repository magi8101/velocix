"""FastAPI-style parameter markers for handler signature injection.

Usage:
    @app.get("/items")
    async def items(q: str | None = Query(None), skip: int = Query(0)):
        ...

    @app.get("/secure")
    async def secure(x_token: str = Header(...)):
        ...

    @app.get("/prefs")
    async def prefs(theme: str = Cookie("light")):
        ...

Plain annotated parameters (no marker) resolve as path parameters when
their name appears in the route, otherwise as query parameters with the
default from the signature (required if no default).
"""

from typing import Any

# Sentinel for required parameters (FastAPI uses Ellipsis: `Query(...)`)
_REQUIRED: Any = Ellipsis


class Query:
    """Query-string parameter marker.

    Args:
        default: Default value, or Ellipsis (`...`) to require the parameter
        description: OpenAPI description
        alias: Override the query-string key (defaults to the param name)
    """

    __slots__ = ("default", "description", "alias")

    def __init__(
        self,
        default: Any = _REQUIRED,
        *,
        description: str = "",
        alias: str | None = None,
    ) -> None:
        self.default = default
        self.description = description
        self.alias = alias

    def __repr__(self) -> str:
        return f"Query(default={self.default!r})"


class Header:
    """Request-header parameter marker.

    Args:
        default: Default value, or Ellipsis (`...`) to require the parameter
        description: OpenAPI description
        alias: Override the header name (defaults to the param name)
        convert_underscores: Map `_` to `-` in the header name (default True)
    """

    __slots__ = ("default", "description", "alias", "convert_underscores")

    def __init__(
        self,
        default: Any = _REQUIRED,
        *,
        description: str = "",
        alias: str | None = None,
        convert_underscores: bool = True,
    ) -> None:
        self.default = default
        self.description = description
        self.alias = alias
        self.convert_underscores = convert_underscores

    def __repr__(self) -> str:
        return f"Header(default={self.default!r})"


class Cookie:
    """Cookie parameter marker.

    Args:
        default: Default value, or Ellipsis (`...`) to require the parameter
        description: OpenAPI description
        alias: Override the cookie key (defaults to the param name)
    """

    __slots__ = ("default", "description", "alias")

    def __init__(
        self,
        default: Any = _REQUIRED,
        *,
        description: str = "",
        alias: str | None = None,
    ) -> None:
        self.default = default
        self.description = description
        self.alias = alias

    def __repr__(self) -> str:
        return f"Cookie(default={self.default!r})"


class Form:
    """Form-field parameter marker (multipart or urlencoded bodies).

    Args:
        default: Default value, or Ellipsis (`...`) to require the parameter
        description: OpenAPI description
        alias: Override the form-field key (defaults to the param name)
    """

    __slots__ = ("default", "description", "alias")

    def __init__(
        self,
        default: Any = _REQUIRED,
        *,
        description: str = "",
        alias: str | None = None,
    ) -> None:
        self.default = default
        self.description = description
        self.alias = alias

    def __repr__(self) -> str:
        return f"Form(default={self.default!r})"


class File:
    """Uploaded-file parameter marker (multipart bodies).

    Injects an `UploadFile` for the named part; requires the request
    content-type to be `multipart/form-data`.

    Args:
        default: Default value, or Ellipsis (`...`) to require the file
        description: OpenAPI description
        alias: Override the form-field key (defaults to the param name)
    """

    __slots__ = ("default", "description", "alias")

    def __init__(
        self,
        default: Any = _REQUIRED,
        *,
        description: str = "",
        alias: str | None = None,
    ) -> None:
        self.default = default
        self.description = description
        self.alias = alias

    def __repr__(self) -> str:
        return f"File(default={self.default!r})"
