"""OpenAPI support for Velocix"""
from .models import (
    OpenAPISpec, Info, Server, PathItem, Operation,
    Parameter, Response, Schema, Tag, SecurityScheme,
    ParameterIn, SchemaType
)
from .decorators import (
    operation, parameter, response, tag, request_body, security,
    get_operation_for_function, clear_operations, string_schema, integer_schema,
    array_schema, object_schema
)
from .generator import (
    OpenAPIGenerator, SwaggerUIHandler, ReDocHandler,
    create_openapi_generator, setup_docs_routes
)
from .decorators_style import (
    get, post, put, delete, Path, Query, Body, responses, tags,
    VelocixStyleDocs, create_docs
)
from .auto_docs import (
    AutoDocRouter, enable_auto_docs, create_auto_router,
    auto_document_function, generate_operation_from_function
)

__all__ = [
    # Models
    'OpenAPISpec', 'Info', 'Server', 'PathItem', 'Operation',
    'Parameter', 'Response', 'Schema', 'Tag', 'SecurityScheme',
    'ParameterIn', 'SchemaType',
    
    # Decorators (low-level)
    'operation', 'parameter', 'response', 'tag', 'request_body', 'security',
    'get_operation_for_function', 'clear_operations',
    
    # Schema helpers
    'string_schema', 'integer_schema', 'array_schema', 'object_schema',
    
    # Generator
    'OpenAPIGenerator', 'SwaggerUIHandler', 'ReDocHandler',
    'create_openapi_generator', 'setup_docs_routes',
    
    # Velocix-style (recommended)
    'get', 'post', 'put', 'delete', 'Path', 'Query', 'Body', 'responses', 'tags',
    'VelocixStyleDocs', 'create_docs',
    
    # Auto-documentation (zero decorators!)
    'AutoDocRouter', 'enable_auto_docs', 'create_auto_router',
    'auto_document_function', 'generate_operation_from_function'
]