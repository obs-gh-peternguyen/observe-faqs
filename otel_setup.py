import os
import streamlit as st

def _get_secret(key, default=None):
    try:
        return st.secrets["otel"][key]
    except (KeyError, AttributeError):
        return os.environ.get(key, default)

_initialized = False

def init_otel():
    global _initialized
    if _initialized:
        return
    _initialized = True

    observe_id = _get_secret("OBSERVE_ID")
    observe_token = _get_secret("OBSERVE_TOKEN")
    service_name = _get_secret("OTEL_SERVICE_NAME", "observe-faqs")
    service_version = _get_secret("OTEL_SERVICE_VERSION", "20260514")
    deployment_env = _get_secret("OTEL_DEPLOYMENT_ENV", "production")

    if not observe_id or not observe_token:
        return

    traces_endpoint = f"https://{observe_id}.collect.observeinc.com/v2/otel/v1/traces"
    metrics_endpoint = f"https://{observe_id}.collect.observeinc.com/v2/otel/v1/metrics"
    logs_endpoint = f"https://{observe_id}.collect.observeinc.com/v2/otel/v1/logs"

    common_headers = f"Authorization=Bearer {observe_token}"

    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", traces_endpoint)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_HEADERS", f"Content-Type=application/x-protobuf,{common_headers},x-observe-target-package=Tracing")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")

    os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", metrics_endpoint)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_HEADERS", f"Content-Type=application/x-protobuf,{common_headers},x-observe-target-package=Metrics")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", "http/protobuf")

    os.environ.setdefault("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", logs_endpoint)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_LOGS_HEADERS", f"Content-Type=application/x-protobuf,{common_headers},x-observe-target-package=Host Explorer")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_LOGS_PROTOCOL", "http/protobuf")

    os.environ.setdefault("OTEL_RESOURCE_ATTRIBUTES",
        f"service.name={service_name},"
        f"service.instance.id=streamlit,"
        f"service.namespace=streamlit-community-cloud,"
        f"service.version={service_version},"
        f"deployment.environment.name={deployment_env}"
    )

    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

    resource = Resource.create({
        "service.name": service_name,
        "service.instance.id": "streamlit",
        "service.namespace": "streamlit-community-cloud",
        "service.version": service_version,
        "deployment.environment.name": deployment_env,
    })

    trace_headers = {
        "Content-Type": "application/x-protobuf",
        "Authorization": f"Bearer {observe_token}",
        "x-observe-target-package": "Tracing",
    }
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=traces_endpoint, headers=trace_headers, timeout=30),
            max_export_batch_size=64,
            schedule_delay_millis=10000,
        )
    )
    trace.set_tracer_provider(tracer_provider)

    metric_headers = {
        "Content-Type": "application/x-protobuf",
        "Authorization": f"Bearer {observe_token}",
        "x-observe-target-package": "Metrics",
    }
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=metrics_endpoint, headers=metric_headers, timeout=30),
        export_interval_millis=120000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    log_headers = {
        "Content-Type": "application/x-protobuf",
        "Authorization": f"Bearer {observe_token}",
        "x-observe-target-package": "Host Explorer",
    }
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=logs_endpoint, headers=log_headers, timeout=30),
            max_export_batch_size=64,
            schedule_delay_millis=10000,
        )
    )
    set_logger_provider(logger_provider)

    from opentelemetry.instrumentation.tornado import TornadoInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.threading import ThreadingInstrumentor
    from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
    from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor

    TornadoInstrumentor().instrument()
    RequestsInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    ThreadingInstrumentor().instrument()
    URLLib3Instrumentor().instrument()
    SystemMetricsInstrumentor().instrument()
