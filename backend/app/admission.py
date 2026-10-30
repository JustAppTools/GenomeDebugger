"""Checks for new submissions, separate from reading immutable saved models."""

from pydantic import BaseModel


def require_text(value: str, path: str) -> None:
    if not any(not char.isspace() and char != '\ufeff' for char in value):
        raise ValueError(f'{path} must contain non-whitespace text')


def validate_required_text(model: BaseModel, path: str = '') -> None:
    for name, field in type(model).model_fields.items():
        value = getattr(model, name)
        label = f'{path}.{name}' if path else name
        if isinstance(value, str) and any((getattr(rule, 'min_length', None) or 0) >= 1 for rule in field.metadata):
            require_text(value, label)
        elif isinstance(value, BaseModel):
            validate_required_text(value, label)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if isinstance(child, BaseModel):
                    validate_required_text(child, f'{label}[{index}]')
