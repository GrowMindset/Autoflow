from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


class FormFieldOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class FormFieldBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str | None = None
    label: str = Field(min_length=1)
    required: bool = False
    placeholder: str | None = None

    @model_validator(mode="after")
    def require_key(self) -> "FormFieldBase":
        if self.name or self.id:
            return self
        raise ValueError("Form field must include a non-empty name or id")


class TextFormFieldConfig(FormFieldBase):
    type: Literal["text"] = "text"


class EmailFormFieldConfig(FormFieldBase):
    type: Literal["email"] = "email"


class NumberFormFieldConfig(FormFieldBase):
    type: Literal["number"] = "number"


class TextareaFormFieldConfig(FormFieldBase):
    type: Literal["textarea"] = "textarea"


class SelectFormFieldConfig(FormFieldBase):
    type: Literal["select"] = "select"
    options: list[FormFieldOption] = Field(min_length=1)


class RadioFormFieldConfig(FormFieldBase):
    type: Literal["radio"] = "radio"
    options: list[FormFieldOption] = Field(min_length=1)
    layout: Literal["inline", "stacked"] = "stacked"


class CheckboxFormFieldConfig(FormFieldBase):
    type: Literal["checkbox"] = "checkbox"
    default_checked: bool = False


class CheckboxGroupFormFieldConfig(FormFieldBase):
    type: Literal["checkbox_group"] = "checkbox_group"
    options: list[FormFieldOption] = Field(min_length=1)


class DateFormFieldConfig(FormFieldBase):
    type: Literal["date"] = "date"
    min_date: str | None = None
    max_date: str | None = None

    @field_validator("min_date", "max_date")
    @classmethod
    def validate_date_bound(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        _parse_date(value, "date bound")
        return value


class TimeFormFieldConfig(FormFieldBase):
    type: Literal["time"] = "time"
    min_time: str | None = None
    max_time: str | None = None

    @field_validator("min_time", "max_time")
    @classmethod
    def validate_time_bound(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        _parse_time(value, "time bound")
        return value


class DatetimeFormFieldConfig(FormFieldBase):
    type: Literal["datetime"] = "datetime"
    min_datetime: str | None = None
    max_datetime: str | None = None

    @field_validator("min_datetime", "max_datetime")
    @classmethod
    def validate_datetime_bound(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        _parse_datetime(value, "datetime bound")
        return value


class UrlFormFieldConfig(FormFieldBase):
    type: Literal["url"] = "url"


class PhoneFormFieldConfig(FormFieldBase):
    type: Literal["phone"] = "phone"
    default_country_code: str | None = None


class RatingFormFieldConfig(FormFieldBase):
    type: Literal["rating"] = "rating"
    max_stars: int = Field(default=5, ge=1, le=5)


FormFieldConfig = Annotated[
    TextFormFieldConfig
    | EmailFormFieldConfig
    | NumberFormFieldConfig
    | TextareaFormFieldConfig
    | SelectFormFieldConfig
    | RadioFormFieldConfig
    | CheckboxFormFieldConfig
    | CheckboxGroupFormFieldConfig
    | DateFormFieldConfig
    | TimeFormFieldConfig
    | DatetimeFormFieldConfig
    | UrlFormFieldConfig
    | PhoneFormFieldConfig
    | RatingFormFieldConfig,
    Field(discriminator="type"),
]

FORM_FIELD_CONFIG_ADAPTER = TypeAdapter(FormFieldConfig)
FORM_FIELD_TYPES = {
    "text",
    "email",
    "number",
    "textarea",
    "select",
    "radio",
    "checkbox",
    "checkbox_group",
    "date",
    "time",
    "datetime",
    "url",
    "phone",
    "rating",
}
COMMON_FORM_FIELD_KEYS = {"id", "name", "type", "label", "required", "placeholder"}
FORM_FIELD_EXTRA_KEYS_BY_TYPE = {
    "select": {"options"},
    "radio": {"options", "layout"},
    "checkbox_group": {"options"},
    "checkbox": {"default_checked"},
    "date": {"min_date", "max_date"},
    "time": {"min_time", "max_time"},
    "datetime": {"min_datetime", "max_datetime"},
    "phone": {"default_country_code"},
    "rating": {"max_stars"},
}


def normalize_form_field_config(raw_field: Any, *, index: int = 0) -> dict[str, Any] | None:
    if not isinstance(raw_field, dict):
        return None

    candidate = dict(raw_field)
    raw_type = str(candidate.get("type") or "text").strip().lower() or "text"
    candidate["type"] = raw_type if raw_type in FORM_FIELD_TYPES else "text"
    allowed_keys = COMMON_FORM_FIELD_KEYS | FORM_FIELD_EXTRA_KEYS_BY_TYPE.get(candidate["type"], set())
    candidate = {key: value for key, value in candidate.items() if key in allowed_keys}
    candidate["type"] = raw_type if raw_type in FORM_FIELD_TYPES else "text"
    for key in ("id", "name", "label", "placeholder"):
        if key in candidate and isinstance(candidate[key], str):
            candidate[key] = candidate[key].strip()
    if not str(candidate.get("label") or "").strip():
        fallback = str(candidate.get("name") or candidate.get("id") or f"field_{index + 1}").strip()
        candidate["label"] = fallback or f"Field {index + 1}"
    if not str(candidate.get("name") or candidate.get("id") or "").strip():
        candidate["name"] = f"field_{index + 1}"
    if candidate["type"] in {"select", "radio", "checkbox_group"} and not isinstance(candidate.get("options"), list):
        candidate["options"] = [{"label": "Option 1", "value": "option_1"}]

    return FORM_FIELD_CONFIG_ADAPTER.validate_python(candidate).model_dump(exclude_none=True)


def validate_form_submission(fields: Any, form_data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(fields, list) or not fields:
        raise ValueError("FormTriggerRunner: config must have a non-empty 'fields' list")

    payload = dict(form_data or {})
    normalized_fields: list[dict[str, Any]] = []
    for index, raw_field in enumerate(fields):
        field = normalize_form_field_config(raw_field, index=index)
        if field is None:
            raise ValueError("FormTriggerRunner: each field definition must be an object")
        normalized_fields.append(field)

    for field in normalized_fields:
        field_name = _field_key(field)
        if not field_name:
            raise ValueError("FormTriggerRunner: each field definition must include a non-empty 'name'")

        value = payload.get(field_name)
        has_value = field_name in payload and value is not None and value != ""
        if field.get("required") and field.get("type") == "checkbox_group" and value == []:
            raise ValueError(f"FormTriggerRunner: required field '{field_name}' must include at least one selected option")
        if field.get("required") and not has_value:
            raise ValueError(f"FormTriggerRunner: required field '{field_name}' is missing from form submission")
        if not has_value:
            continue

        field_type = field.get("type") or "text"
        if field_type in {"select", "radio"}:
            allowed_values = {str(option.get("value")) for option in field.get("options", [])}
            if value not in allowed_values:
                raise ValueError(f"FormTriggerRunner: field '{field_name}' must match one of its configured options")
        elif field_type == "checkbox":
            if not isinstance(value, bool):
                raise ValueError(f"FormTriggerRunner: field '{field_name}' must be a boolean")
        elif field_type == "checkbox_group":
            allowed_values = {str(option.get("value")) for option in field.get("options", [])}
            if not isinstance(value, list):
                raise ValueError(f"FormTriggerRunner: field '{field_name}' must be a list")
            for item in value:
                if not isinstance(item, str) or item not in allowed_values:
                    raise ValueError(f"FormTriggerRunner: field '{field_name}' must only include configured options")
        elif field_type == "date":
            _parse_date(value, f"field '{field_name}'")
        elif field_type == "time":
            _parse_time(value, f"field '{field_name}'")
        elif field_type == "datetime":
            _parse_datetime(value, f"field '{field_name}'")
        elif field_type == "url":
            if not _is_valid_url(value):
                raise ValueError(f"FormTriggerRunner: field '{field_name}' must be a valid URL")
        elif field_type == "rating":
            max_stars = int(field.get("max_stars") or 5)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > max_stars:
                raise ValueError(f"FormTriggerRunner: field '{field_name}' must be an integer from 1 to {max_stars}")

    return payload


def _field_key(field: dict[str, Any]) -> str:
    return str(field.get("name") or field.get("id") or "").strip()


def _parse_date(value: Any, label: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"FormTriggerRunner: {label} must be a valid YYYY-MM-DD date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"FormTriggerRunner: {label} must be a valid YYYY-MM-DD date") from exc


def _parse_time(value: Any, label: str) -> time:
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValueError(f"FormTriggerRunner: {label} must be a valid HH:MM time")
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"FormTriggerRunner: {label} must be a valid HH:MM time") from exc


def _parse_datetime(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"FormTriggerRunner: {label} must be a valid ISO 8601 datetime")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"FormTriggerRunner: {label} must be a valid ISO 8601 datetime") from exc


def _is_valid_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
