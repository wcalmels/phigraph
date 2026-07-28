from __future__ import annotations

import contextvars
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Iterator

_trace_id = contextvars.ContextVar("phigraph_trace_id", default=None)
_parent_span_id = contextvars.ContextVar("phigraph_parent_span_id", default=None)
_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    parent_span_id: str | None = None
    flags: str = "01"

    @classmethod
    def parse(cls, value: str | None) -> "TraceContext | None":
        if not value:
            return None
        match = _TRACEPARENT.match(value.strip().lower())
        if not match or set(match.group(1)) == {"0"} or set(match.group(2)) == {"0"}:
            raise ValueError("invalid_traceparent")
        return cls(match.group(1), match.group(2), match.group(3))

    def header(self, span_id: str) -> str:
        return f"00-{self.trace_id}-{span_id}-{self.flags}"


@dataclass(frozen=True)
class SpanRecord:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    started_at: float
    duration_ms: float
    status: str
    attributes: dict[str, Any]

    def to_dict(self):
        return asdict(self)


class TraceRecorder:
    def __init__(self, max_spans: int = 1000, otlp_endpoint: str | None = None, service_name: str = "phigraph-core"):
        self.max_spans = max_spans
        self.spans: list[SpanRecord] = []
        self._otel_tracer = None
        if otlp_endpoint:
            self._configure_otlp(otlp_endpoint, service_name)

    def _configure_otlp(self, endpoint: str, service_name: str) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:
            raise RuntimeError("OTLP export requires opentelemetry-sdk and opentelemetry-exporter-otlp") from exc
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        self._otel_tracer = provider.get_tracer(service_name)

    @contextmanager
    def use_context(self, context: TraceContext | None) -> Iterator[None]:
        if context is None:
            yield
            return
        token_trace = _trace_id.set(context.trace_id)
        token_parent = _parent_span_id.set(context.parent_span_id)
        try:
            yield
        finally:
            _parent_span_id.reset(token_parent)
            _trace_id.reset(token_trace)

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[str]:
        trace_id = _trace_id.get() or uuid.uuid4().hex
        parent_span_id = _parent_span_id.get()
        token_trace = _trace_id.set(trace_id)
        span_id = uuid.uuid4().hex[:16]
        token_parent = _parent_span_id.set(span_id)
        started = time.time()
        status = "ok"
        otel_context = self._otel_tracer.start_as_current_span(name, attributes=attributes) if self._otel_tracer else None
        try:
            if otel_context:
                otel_context.__enter__()
            yield trace_id
        except Exception as exc:
            status = "error"
            if otel_context:
                otel_context.__exit__(type(exc), exc, exc.__traceback__)
                otel_context = None
            raise
        finally:
            if otel_context:
                otel_context.__exit__(None, None, None)
            duration = (time.time() - started) * 1000
            self.spans.append(SpanRecord(trace_id, span_id, parent_span_id, name, started, duration, status, attributes))
            self.spans[:] = self.spans[-self.max_spans :]
            _parent_span_id.reset(token_parent)
            _trace_id.reset(token_trace)

    def snapshot(self, limit: int = 100):
        return [span.to_dict() for span in self.spans[-limit:]]
