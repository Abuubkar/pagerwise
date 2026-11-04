import subprocess
import sys

# A fresh interpreter, with httpx and redis made unimportable the way docs-mock's and the simulator's images lack
# them. Before the fix, setup() imported both instrumentations unconditionally and those images crashed on start.
WITHOUT_CLIENTS = """
import sys
sys.modules["httpx"] = None
sys.modules["redis"] = None
import pagerwise_telemetry
pagerwise_telemetry.setup("test-service")
print("ok")
"""


def test_setup_without_httpx_or_redis_installed() -> None:
    result = subprocess.run([sys.executable, "-c", WITHOUT_CLIENTS], check=False, capture_output=True, text=True,
                            timeout=60, env={"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:1", "PATH": ""})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("ok")
