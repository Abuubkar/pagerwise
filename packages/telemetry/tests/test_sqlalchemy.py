import subprocess
import sys

# instrument_engine on SQLAlchemy 2.1, which the instrumentation's declared range (< 2.1) excludes: without
# skip_dep_check it logged one error and made no spans at all.
SQL_SPANS = """
from types import SimpleNamespace
import sqlalchemy
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pagerwise_telemetry
exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)
engine = sqlalchemy.create_engine("sqlite://")
pagerwise_telemetry.instrument_engine([SimpleNamespace(sync_engine=engine)])
with engine.connect() as conn:
    conn.execute(sqlalchemy.text("SELECT :x"), {"x": "user text"})
print([(s.name, s.attributes.get("db.statement")) for s in exporter.get_finished_spans()])
"""


def test_instrument_engine_makes_sql_spans_on_sqlalchemy_2_1() -> None:
    result = subprocess.run([sys.executable, "-c", SQL_SPANS], check=False, capture_output=True, text=True,
                            timeout=60, env={"PATH": ""})
    assert result.returncode == 0, result.stderr
    assert "('SELECT', 'SELECT ?')" in result.stdout  # a span, with the bound value left out of the statement
