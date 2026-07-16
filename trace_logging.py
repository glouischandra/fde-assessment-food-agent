import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any
from opentelemetry import trace

class OpenTelemetryJsonFormatter(logging.Formatter):
    """Structured JSON formatter aligned with OpenTelemetry Logging best practices."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Get active OpenTelemetry span context for trace-log correlation
        span = trace.get_current_span()
        span_context = span.get_span_context() if span else None
        
        # Core structured log attributes following OpenTelemetry resource and semantic conventions
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service.name": "food_agent"
        }
        
        # Inject standard trace identifiers if trace/span is active
        if span_context and span_context.is_valid:
            log_data["trace_id"] = f"{span_context.trace_id:032x}"
            log_data["span_id"] = f"{span_context.span_id:16x}"
            log_data["trace_flags"] = f"{span_context.trace_flags:02x}"
            
        # Exception details formatted as standard OpenTelemetry semantic exception fields
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            log_data["exception.type"] = exc_type.__name__ if exc_type else "Exception"
            log_data["exception.message"] = str(exc_value)
            log_data["exception.stacktrace"] = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            
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
                custom_attrs[key] = val
                
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
