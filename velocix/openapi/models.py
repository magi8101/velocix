"""OpenAPI 3.1 data models"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import json

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


class SchemaType(Enum):
    """OpenAPI schema types"""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"


class ParameterIn(Enum):
    """Parameter location"""
    QUERY = "query"
    HEADER = "header"
    PATH = "path"
    COOKIE = "cookie"


@dataclass
class Schema:
    """OpenAPI Schema object"""
    type: Optional[SchemaType] = None
    format: Optional[str] = None
    items: Optional['Schema'] = None
    properties: Optional[Dict[str, 'Schema']] = None
    required: Optional[List[str]] = None
    enum: Optional[List[Any]] = None
    default: Any = None
    example: Any = None
    description: Optional[str] = None
    nullable: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.type:
            result['type'] = self.type.value
        if self.format:
            result['format'] = self.format
        if self.items:
            result['items'] = self.items.to_dict()
        if self.properties:
            result['properties'] = {k: v.to_dict() for k, v in self.properties.items()}
        if self.required:
            result['required'] = self.required
        if self.enum:
            result['enum'] = self.enum
        if self.default is not None:
            result['default'] = self.default
        if self.example is not None:
            result['example'] = self.example
        if self.description:
            result['description'] = self.description
        if self.nullable:
            result['nullable'] = self.nullable
        return result


@dataclass
class Parameter:
    """OpenAPI Parameter object"""
    name: str
    in_: ParameterIn
    description: Optional[str] = None
    required: bool = False
    deprecated: bool = False
    schema: Optional[Schema] = None
    style: Optional[str] = None
    explode: Optional[bool] = None
    example: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'name': self.name,
            'in': self.in_.value,
            'required': self.required
        }
        if self.description:
            result['description'] = self.description
        if self.deprecated:
            result['deprecated'] = self.deprecated
        if self.schema:
            result['schema'] = self.schema.to_dict()
        if self.style:
            result['style'] = self.style
        if self.explode is not None:
            result['explode'] = self.explode
        if self.example is not None:
            result['example'] = self.example
        return result


@dataclass
class Response:
    """OpenAPI Response object"""
    description: str
    headers: Optional[Dict[str, Parameter]] = None
    content: Optional[Dict[str, Dict[str, Any]]] = None
    links: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {'description': self.description}
        if self.headers:
            result['headers'] = {k: v.to_dict() for k, v in self.headers.items()}
        if self.content:
            result['content'] = self.content
        if self.links:
            result['links'] = self.links
        return result


@dataclass 
class Tag:
    """OpenAPI Tag object"""
    name: str
    description: Optional[str] = None
    external_docs: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {'name': self.name}
        if self.description:
            result['description'] = self.description
        if self.external_docs:
            result['externalDocs'] = self.external_docs
        return result
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tag):
            return False
        return self.name == other.name


@dataclass
class Operation:
    """OpenAPI Operation object"""
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    external_docs: Optional[Dict[str, str]] = None
    operation_id: Optional[str] = None
    parameters: Optional[List[Parameter]] = None
    request_body: Optional[Dict[str, Any]] = None
    responses: Optional[Dict[str, Response]] = None
    callbacks: Optional[Dict[str, Any]] = None
    deprecated: bool = False
    security: Optional[List[Dict[str, List[str]]]] = None
    servers: Optional[List[Dict[str, str]]] = None
    
    def __post_init__(self) -> None:
        if self.parameters is None:
            self.parameters = []
        if self.responses is None:
            self.responses = {}
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.tags:
            result['tags'] = self.tags
        if self.summary:
            result['summary'] = self.summary
        if self.description:
            result['description'] = self.description
        if self.external_docs:
            result['externalDocs'] = self.external_docs
        if self.operation_id:
            result['operationId'] = self.operation_id
        if self.parameters:
            result['parameters'] = [p.to_dict() for p in self.parameters]
        if self.request_body:
            result['requestBody'] = self.request_body
        if self.responses:
            result['responses'] = {k: v.to_dict() for k, v in self.responses.items()}
        if self.callbacks:
            result['callbacks'] = self.callbacks
        if self.deprecated:
            result['deprecated'] = self.deprecated
        if self.security:
            result['security'] = self.security
        if self.servers:
            result['servers'] = self.servers
        return result


@dataclass
class PathItem:
    """OpenAPI PathItem object"""
    ref: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    get: Optional[Operation] = None
    put: Optional[Operation] = None
    post: Optional[Operation] = None
    delete: Optional[Operation] = None
    options: Optional[Operation] = None
    head: Optional[Operation] = None
    patch: Optional[Operation] = None
    trace: Optional[Operation] = None
    servers: Optional[List[Dict[str, str]]] = None
    parameters: Optional[List[Parameter]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.ref:
            result['$ref'] = self.ref
        if self.summary:
            result['summary'] = self.summary
        if self.description:
            result['description'] = self.description
        
        for method in ['get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace']:
            operation = getattr(self, method)
            if operation:
                result[method] = operation.to_dict()
        
        if self.servers:
            result['servers'] = self.servers
        if self.parameters:
            result['parameters'] = [p.to_dict() for p in self.parameters]
        return result


@dataclass
class Info:
    """OpenAPI Info object"""
    title: str
    version: str
    description: Optional[str] = None
    terms_of_service: Optional[str] = None
    contact: Optional[Dict[str, str]] = None
    license: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'title': self.title,
            'version': self.version
        }
        if self.description:
            result['description'] = self.description
        if self.terms_of_service:
            result['termsOfService'] = self.terms_of_service
        if self.contact:
            result['contact'] = self.contact
        if self.license:
            result['license'] = self.license
        return result


@dataclass
class Server:
    """OpenAPI Server object"""
    url: str
    description: Optional[str] = None
    variables: Optional[Dict[str, Dict[str, Any]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {'url': self.url}
        if self.description:
            result['description'] = self.description
        if self.variables:
            result['variables'] = self.variables
        return result


@dataclass
class SecurityScheme:
    """OpenAPI Security Scheme object"""
    type: str
    description: Optional[str] = None
    name: Optional[str] = None
    in_: Optional[str] = None
    scheme: Optional[str] = None
    bearer_format: Optional[str] = None
    flows: Optional[Dict[str, Any]] = None
    open_id_connect_url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {'type': self.type}
        if self.description:
            result['description'] = self.description
        if self.name:
            result['name'] = self.name
        if self.in_:
            result['in'] = self.in_
        if self.scheme:
            result['scheme'] = self.scheme
        if self.bearer_format:
            result['bearerFormat'] = self.bearer_format
        if self.flows:
            result['flows'] = self.flows
        if self.open_id_connect_url:
            result['openIdConnectUrl'] = self.open_id_connect_url
        return result


@dataclass
class OpenAPISpec:
    """OpenAPI 3.1 specification"""
    openapi: str
    info: Info
    servers: Optional[List[Server]] = None
    paths: Optional[Dict[str, PathItem]] = None
    webhooks: Optional[Dict[str, PathItem]] = None
    components: Optional[Dict[str, Any]] = None
    security: Optional[List[Dict[str, List[str]]]] = None
    tags: Optional[List[Tag]] = None
    external_docs: Optional[Dict[str, str]] = None
    
    def __post_init__(self) -> None:
        if self.paths is None:
            self.paths = {}
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'openapi': self.openapi,
            'info': self.info.to_dict()
        }
        
        if self.servers:
            result['servers'] = [s.to_dict() for s in self.servers]
        if self.paths:
            result['paths'] = {k: v.to_dict() for k, v in self.paths.items()}
        if self.webhooks:
            result['webhooks'] = {k: v.to_dict() for k, v in self.webhooks.items()}
        if self.components:
            result['components'] = self.components
        if self.security:
            result['security'] = self.security
        if self.tags:
            result['tags'] = [t.to_dict() for t in self.tags]
        if self.external_docs:
            result['externalDocs'] = self.external_docs
        
        return result
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent)
    
    def to_yaml(self) -> str:
        """Convert to YAML string"""
        if yaml is None:
            raise ImportError("PyYAML is required for YAML export")
        return yaml.dump(self.to_dict(), default_flow_style=False)