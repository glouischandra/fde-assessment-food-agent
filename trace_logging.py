import contextlib
import json
import logging
import re
import traceback
from datetime import datetime, timezone
from typing import Any, Generator
from opentelemetry import trace

# PII Pattern Regular Expressions
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
GOOGLE_TOKEN_REGEX = re.compile(r"ya29\.[a-zA-Z0-9_-]+")

# Exact match sensitive keys to avoid collisons on names like taskName
EXACT_SENSITIVE_KEYS = {
    "name": "[REDACTED_NAME]",
    "user_id": "[REDACTED_ID]",
    "userid": "[REDACTED_ID]",
    "email": "[REDACTED_EMAIL]",
    "phone": "[REDACTED_PHONE]",
    "latitude": "[REDACTED_LOCATION]",
    "longitude": "[REDACTED_LOCATION]",
    "location": "[REDACTED_LOCATION]"
}

# Substring match sensitive keys
SUBSTRING_SENSITIVE_KEYS = {
    "user_name": "[REDACTED_NAME]",
    "username": "[REDACTED_NAME]",
    "first_name": "[REDACTED_NAME]",
    "last_name": "[REDACTED_NAME]",
    "fullname": "[REDACTED_NAME]",
    "credentials": "[REDACTED_SECRET]",
    "token": "[REDACTED_SECRET]",
    "refresh_token": "[REDACTED_SECRET]",
    "client_id": "[REDACTED_SECRET]",
    "client_secret": "[REDACTED_SECRET]"
}

def redact_string(val: str) -> str:
    """Redacts standard PII text patterns from strings."""
    if not isinstance(val, str):
        return val
    val = EMAIL_REGEX.sub("[REDACTED_EMAIL]", val)
    val = PHONE_REGEX.sub("[REDACTED_PHONE]", val)
    val = GOOGLE_TOKEN_REGEX.sub("[REDACTED_SECRET]", val)
    return val

def sanitize_value(key: str, val: Any) -> Any:
    """Recursively checks and masks sensitive dictionary keys and values."""
    key_lower = key.lower()
    
    # 1. Check exact matches
    if key_lower in EXACT_SENSITIVE_KEYS:
        return EXACT_SENSITIVE_KEYS[key_lower]
        
    # 2. Check substring matches
    for sens_k, mask in SUBSTRING_SENSITIVE_KEYS.items():
        if sens_k in key_lower:
            return mask
            
    if isinstance(val, dict):
        return {k: sanitize_value(k, v) for k, v in val.items()}
    elif isinstance(val, list):
        return [sanitize_value(key, item) for item in val]
    elif isinstance(val, str):
        return redact_string(val)
    return val

class OpenTelemetryJsonFormatter(logging.Formatter):
    """Structured JSON formatter aligned with OpenTelemetry Logging best practices, PII redaction, and intent/outcome tracking."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Get active OpenTelemetry span context for trace-log correlation
        span = trace.get_current_span()
        span_context = span.get_span_context() if span else None
        
        # Redact raw messages
        message = redact_string(record.getMessage())
        
        # Core structured log attributes following OpenTelemetry resource and semantic conventions
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "service.name": "food_agent"
        }
        
        # Inject standard trace identifiers if trace/span is active
        if span_context and span_context.is_valid:
            log_data["trace_id"] = f"{span_context.trace_id:032x}"
            log_data["span_id"] = f"{span_context.span_id:16x}"
            log_data["trace_flags"] = f"{span_context.trace_flags:02x}"
            
        # Exception details formatted as standard OpenTelemetry semantic exception fields (redacted)
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            log_data["exception.type"] = exc_type.__name__ if exc_type else "Exception"
            log_data["exception.message"] = redact_string(str(exc_value))
            log_data["exception.stacktrace"] = redact_string("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
            
        # Filter standard LogRecord fields to capture custom 'extra' log parameters
        standard_fields = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "module", "msecs",
            "msg", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "thread", "threadName"
        }
        custom_attrs = {}
        for key, val in record.__dict__.items():
            if key not in standard_fields:
                custom_attrs[key] = sanitize_value(key, val)
                
        # Move event.kind to the root level if present in attributes for first-class convention visibility
        if "event.kind" in custom_attrs:
            log_data["event.kind"] = custom_attrs.pop("event.kind")
            
        if custom_attrs:
            log_data["attributes"] = custom_attrs
            
        return json.dumps(log_data)

# Re-configure the root logger to use the structured OpenTelemetryJsonFormatter
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Clear default handlers to prevent duplicate output formats
for h in list(root_logger.handlers):
    root_logger.removeHandler(h)

# Add a streaming stdout handler using the custom formatter
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(OpenTelemetryJsonFormatter())
root_logger.addHandler(stream_handler)

# Export standard logger instance
logger = logging.getLogger("food_agent")

@contextlib.contextmanager
def log_operation(operation_name: str, attributes: dict = None) -> Generator[None, None, None]:
    """Context manager to automatically log agent intent (start) and outcome (success/failure) of an operation."""
    start_time = datetime.now(timezone.utc)
    logger.info(
        f"Intent to execute operation: {operation_name}",
        extra={
            **(attributes or {}),
            "event.kind": "intent",
            "operation": operation_name
        }
    )
    try:
        yield
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        logger.info(
            f"Outcome of operation: {operation_name} - SUCCESS",
            extra={
                **(attributes or {}),
                "event.kind": "outcome",
                "operation": operation_name,
                "operation.status": "success",
                "operation.duration_ms": duration_ms
            }
        )
    except Exception as e:
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        logger.error(
            f"Outcome of operation: {operation_name} - FAILURE",
            exc_info=True,
            extra={
                **(attributes or {}),
                "event.kind": "outcome",
                "operation": operation_name,
                "operation.status": "failure",
                "operation.duration_ms": duration_ms,
                "error.message": str(e)
            }
        )
        raise
