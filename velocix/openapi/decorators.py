"""OpenAPI decorators for route documentation"""
from typing import Any, Dict, List, Optional, Callable, Union, TypeVar, cast
from functools import wraps
from .models import Operation, Parameter, Response, Schema, Tag as TagModel, ParameterIn, SchemaType

F = TypeVar('F', bound=Callable[..., Any])

# Global registry for route operations
_route_operations: Dict[str, Operation] = {}


def operation(
    summary: Optional[str] = None,
    description: Optional[str] = None,
    operation_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    deprecated: bool = False
) -> Callable[[F], F]:
    """Add operation documentation to a route handler"""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        
        # Store operation metadata
        op = Operation(
            summary=summary,
            description=description,
            operation_id=operation_id or f"{func.__module__}.{func.__name__}",
            tags=tags,
            deprecated=deprecated,
            parameters=[],
            responses={}
        )
        
        # Use function's full name as key
        key = f"{func.__module__}.{func.__name__}"
        _route_operations[key] = op
        
        # Store key on wrapper for retrieval
        setattr(wrapper, '_openapi_key', key)
        return cast(F, wrapper)
    return decorator


def parameter(
    name: str,
    in_: ParameterIn,
    description: Optional[str] = None,
    required: bool = False,
    schema: Optional[Dict[str, Any]] = None,
    example: Any = None
) -> Callable[[F], F]:
    """Add parameter documentation to a route handler"""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        
        # Get or create operation
        key = f"{func.__module__}.{func.__name__}"
        if key not in _route_operations:
            _route_operations[key] = Operation(
                operation_id=key,
                parameters=[],
                responses={}
            )
        
        # Add parameter
        param = Parameter(
            name=name,
            in_=in_,
            description=description,
            required=required,
            schema=Schema(
                type=schema.get('type', SchemaType.STRING) if schema else SchemaType.STRING,
                format=schema.get('format') if schema else None,
                example=example
            ) if schema or example else None
        )
        
        if _route_operations[key].parameters is not None:
            _route_operations[key].parameters.append(param)
        setattr(wrapper, '_openapi_key', key)
        return cast(F, wrapper)
    return decorator


def response(
    status_code: Union[int, str],
    description: str,
    schema: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Dict[str, Any]]] = None
) -> Callable[[F], F]:
    """Add response documentation to a route handler"""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        
        # Get or create operation
        key = f"{func.__module__}.{func.__name__}"
        if key not in _route_operations:
            _route_operations[key] = Operation(
                operation_id=key,
                parameters=[],
                responses={}
            )
        
        # Add response (simplified - no complex headers for now)
        resp = Response(
            description=description,
            content={
                'application/json': {
                    'schema': schema
                }
            } if schema else {},
            headers=None
        )
        
        if _route_operations[key].responses is not None:
            _route_operations[key].responses[str(status_code)] = resp
        setattr(wrapper, '_openapi_key', key)
        return cast(F, wrapper)
    return decorator


def tag(*tags: str) -> Callable[[F], F]:
    """Add tags to a route handler"""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        
        # Get or create operation
        key = f"{func.__module__}.{func.__name__}"
        if key not in _route_operations:
            _route_operations[key] = Operation(
                operation_id=key,
                parameters=[],
                responses={},
                tags=[]
            )
        
        # Add tags
        if _route_operations[key].tags is not None:
            for tag_name in tags:
                if tag_name not in _route_operations[key].tags:
                    _route_operations[key].tags.append(tag_name)
        
        setattr(wrapper, '_openapi_key', key)
        return cast(F, wrapper)
    return decorator


def request_body(
    description: str,
    content_type: str = 'application/json',
    schema: Optional[Dict[str, Any]] = None,
    required: bool = True
) -> Callable[[F], F]:
    """Add request body documentation to a route handler"""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        
        # Get or create operation
        key = f"{func.__module__}.{func.__name__}"
        if key not in _route_operations:
            _route_operations[key] = Operation(
                operation_id=key,
                parameters=[],
                responses={}
            )
        
        # Add request body
        _route_operations[key].request_body = {
            'description': description,
            'required': required,
            'content': {
                content_type: {
                    'schema': schema
                }
            } if schema else {}
        }
        
        setattr(wrapper, '_openapi_key', key)
        return cast(F, wrapper)
    return decorator


def security(scheme_name: str) -> Callable[[F], F]:
    """Add security requirement to a route handler"""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        
        # Get or create operation
        key = f"{func.__module__}.{func.__name__}"
        if key not in _route_operations:
            _route_operations[key] = Operation(
                operation_id=key,
                parameters=[],
                responses={}
            )
        
        # Add security
        if not _route_operations[key].security:
            _route_operations[key].security = []
        
        _route_operations[key].security.append({scheme_name: []})
        setattr(wrapper, '_openapi_key', key)
        return cast(F, wrapper)
    return decorator


def get_operation_for_function(func: Callable[..., Any]) -> Optional[Operation]:
    """Get the OpenAPI operation for a function"""
    key = getattr(func, '_openapi_key', None)
    if key:
        return _route_operations.get(key)
    
    # Fallback to function name
    fallback_key = f"{func.__module__}.{func.__name__}"
    return _route_operations.get(fallback_key)


def clear_operations() -> None:
    """Clear all registered operations (for testing)"""
    global _route_operations
    _route_operations.clear()


# Schema helper functions
def string_schema(
    format_: Optional[str] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    pattern: Optional[str] = None,
    example: Any = None
) -> Dict[str, Any]:
    """Create a string schema"""
    schema: Dict[str, Any] = {'type': 'string'}
    if format_:
        schema['format'] = format_
    if min_length is not None:
        schema['minLength'] = min_length
    if max_length is not None:
        schema['maxLength'] = max_length
    if pattern:
        schema['pattern'] = pattern
    if example is not None:
        schema['example'] = example
    return schema


def integer_schema(
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
    example: Any = None
) -> Dict[str, Any]:
    """Create an integer schema"""
    schema: Dict[str, Any] = {'type': 'integer'}
    if minimum is not None:
        schema['minimum'] = minimum
    if maximum is not None:
        schema['maximum'] = maximum
    if example is not None:
        schema['example'] = example
    return schema


def array_schema(
    items: Dict[str, Any],
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
    example: Any = None
) -> Dict[str, Any]:
    """Create an array schema"""
    schema: Dict[str, Any] = {
        'type': 'array',
        'items': items
    }
    if min_items is not None:
        schema['minItems'] = min_items
    if max_items is not None:
        schema['maxItems'] = max_items
    if example is not None:
        schema['example'] = example
    return schema


def object_schema(
    properties: Dict[str, Dict[str, Any]],
    required: Optional[List[str]] = None,
    example: Any = None
) -> Dict[str, Any]:
    """Create an object schema"""
    schema: Dict[str, Any] = {
        'type': 'object',
        'properties': properties
    }
    if required:
        schema['required'] = required
    if example is not None:
        schema['example'] = example
    return schema