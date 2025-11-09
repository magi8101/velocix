"""Validation utilities with comprehensive error handling"""
import msgspec
from typing import Any, TypeVar, Callable, Type, Union, get_origin, get_args
from collections.abc import Mapping, Sequence
import re

T = TypeVar("T")


class ValidationContext:
    """Context for validation with error accumulation"""
    
    __slots__ = ("_errors", "_path")
    
    def __init__(self) -> None:
        self._errors: list[dict[str, Any]] = []
        self._path: list[str] = []
    
    def add_error(self, field: str, message: str, value: Any = None) -> None:
        """Add validation error"""
        path = ".".join(self._path + [field]) if self._path else field
        error = {
            "field": path,
            "message": message
        }
        if value is not None:
            error["value"] = value
        self._errors.append(error)
    
    def push_path(self, segment: str) -> None:
        """Push path segment for nested validation"""
        self._path.append(segment)
    
    def pop_path(self) -> None:
        """Pop path segment"""
        if self._path:
            self._path.pop()
    
    def has_errors(self) -> bool:
        """Check if any errors exist"""
        return len(self._errors) > 0
    
    def get_errors(self) -> list[dict[str, Any]]:
        """Get all validation errors"""
        return self._errors.copy()
    
    def clear(self) -> None:
        """Clear all errors"""
        self._errors.clear()
        self._path.clear()


def validate_json(data: bytes | str, model: type[T], strict: bool = True) -> T:
    """Validate and parse JSON with msgspec"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    
    try:
        return msgspec.json.decode(data, type=model, strict=strict)
    except msgspec.ValidationError as e:
        raise ValueError(f"JSON validation failed: {str(e)}")
    except msgspec.DecodeError as e:
        raise ValueError(f"JSON decode failed: {str(e)}")


def validate_query(params: dict[str, str | list[str]], model: type[T]) -> T:
    """Validate query parameters with type coercion"""
    try:
        cleaned = {}
        for key, value in params.items():
            if isinstance(value, list):
                cleaned[key] = value[0] if len(value) == 1 else value
            else:
                cleaned[key] = value
        
        return msgspec.convert(cleaned, type=model, strict=False)
    except msgspec.ValidationError as e:
        raise ValueError(f"Query parameter validation failed: {str(e)}")


def validate_form(data: dict[str, Any], model: type[T]) -> T:
    """Validate form data"""
    try:
        return msgspec.convert(data, type=model, strict=False)
    except msgspec.ValidationError as e:
        raise ValueError(f"Form validation failed: {str(e)}")


def to_json(obj: Any, indent: int | None = None) -> bytes:
    """Serialize object to JSON with optional indentation"""
    try:
        if indent:
            return msgspec.json.format(msgspec.json.encode(obj), indent=indent)
        return msgspec.json.encode(obj)
    except Exception as e:
        raise ValueError(f"JSON serialization failed: {str(e)}")


def to_json_str(obj: Any, indent: int | None = None) -> str:
    """Serialize object to JSON string"""
    return to_json(obj, indent=indent).decode('utf-8')


def to_dict(obj: Any) -> dict[str, Any]:
    """Convert Struct to dict recursively"""
    result = msgspec.to_builtins(obj)
    return dict(result) if isinstance(result, dict) else {}


def from_dict(data: dict[str, Any], model: type[T]) -> T:
    """Convert dictionary to model instance"""
    try:
        return msgspec.convert(data, type=model)
    except msgspec.ValidationError as e:
        raise ValueError(f"Dictionary conversion failed: {str(e)}")


class Validator:
    """Functional validator with chaining"""
    
    __slots__ = ("_value", "_field_name", "_errors")
    
    def __init__(self, value: Any, field_name: str = "value") -> None:
        self._value = value
        self._field_name = field_name
        self._errors: list[str] = []
    
    def required(self, message: str = "Field is required") -> "Validator":
        """Check if value is not None"""
        if self._value is None:
            self._errors.append(message)
        return self
    
    def min_length(self, min_len: int, message: str | None = None) -> "Validator":
        """Check minimum length"""
        if self._value is not None and len(self._value) < min_len:
            msg = message or f"Must be at least {min_len} characters"
            self._errors.append(msg)
        return self
    
    def max_length(self, max_len: int, message: str | None = None) -> "Validator":
        """Check maximum length"""
        if self._value is not None and len(self._value) > max_len:
            msg = message or f"Must be at most {max_len} characters"
            self._errors.append(msg)
        return self
    
    def pattern(self, regex: str, message: str | None = None) -> "Validator":
        """Check regex pattern"""
        if self._value is not None and not re.match(regex, str(self._value)):
            msg = message or f"Must match pattern {regex}"
            self._errors.append(msg)
        return self
    
    def email(self, message: str = "Invalid email format") -> "Validator":
        """Validate email"""
        if self._value is not None:
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(pattern, str(self._value)):
                self._errors.append(message)
        return self
    
    def url(self, message: str = "Invalid URL format") -> "Validator":
        """Validate URL"""
        if self._value is not None:
            pattern = r'^https?://[^\s/$.?#].[^\s]*$'
            if not re.match(pattern, str(self._value)):
                self._errors.append(message)
        return self
    
    def min_value(self, min_val: int | float, message: str | None = None) -> "Validator":
        """Check minimum value"""
        if self._value is not None and self._value < min_val:
            msg = message or f"Must be at least {min_val}"
            self._errors.append(msg)
        return self
    
    def max_value(self, max_val: int | float, message: str | None = None) -> "Validator":
        """Check maximum value"""
        if self._value is not None and self._value > max_val:
            msg = message or f"Must be at most {max_val}"
            self._errors.append(msg)
        return self
    
    def custom(self, func: Callable[[Any], bool], message: str) -> "Validator":
        """Custom validation function"""
        if self._value is not None:
            try:
                if not func(self._value):
                    self._errors.append(message)
            except Exception:
                self._errors.append(message)
        return self
    
    def is_valid(self) -> bool:
        """Check if validation passed"""
        return len(self._errors) == 0
    
    def get_errors(self) -> list[str]:
        """Get validation errors"""
        return self._errors.copy()
    
    def raise_if_invalid(self) -> Any:
        """Raise ValueError if validation failed, otherwise return value"""
        if not self.is_valid():
            error_msg = f"Validation failed for '{self._field_name}': " + "; ".join(self._errors)
            raise ValueError(error_msg)
        return self._value


def validate_field(value: Any, field_name: str = "value") -> Validator:
    """Create a validator for a field"""
    return Validator(value, field_name)


class SchemaValidator:
    """Schema-based validation for complex objects"""
    
    __slots__ = ("_schema",)
    
    def __init__(self, schema: dict[str, Any]) -> None:
        self._schema = schema
    
    def validate(self, data: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
        """Validate data against schema"""
        errors: list[dict[str, Any]] = []
        
        for field, rules in self._schema.items():
            value = data.get(field)
            field_errors = self._validate_field(field, value, rules)
            errors.extend(field_errors)
        
        return len(errors) == 0, errors
    
    def _validate_field(self, field: str, value: Any, rules: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate single field"""
        errors: list[dict[str, Any]] = []
        
        if rules.get("required", False) and value is None:
            errors.append({"field": field, "message": "Field is required"})
            return errors
        
        if value is None:
            return errors
        
        if "type" in rules:
            expected_type = rules["type"]
            if not isinstance(value, expected_type):
                errors.append({
                    "field": field,
                    "message": f"Expected type {expected_type.__name__}, got {type(value).__name__}"
                })
        
        if "min_length" in rules and len(value) < rules["min_length"]:
            errors.append({
                "field": field,
                "message": f"Must be at least {rules['min_length']} characters"
            })
        
        if "max_length" in rules and len(value) > rules["max_length"]:
            errors.append({
                "field": field,
                "message": f"Must be at most {rules['max_length']} characters"
            })
        
        if "pattern" in rules and not re.match(rules["pattern"], str(value)):
            errors.append({
                "field": field,
                "message": f"Must match pattern {rules['pattern']}"
            })
        
        if "min_value" in rules and value < rules["min_value"]:
            errors.append({
                "field": field,
                "message": f"Must be at least {rules['min_value']}"
            })
        
        if "max_value" in rules and value > rules["max_value"]:
            errors.append({
                "field": field,
                "message": f"Must be at most {rules['max_value']}"
            })
        
        if "enum" in rules and value not in rules["enum"]:
            errors.append({
                "field": field,
                "message": f"Must be one of {rules['enum']}"
            })
        
        return errors
