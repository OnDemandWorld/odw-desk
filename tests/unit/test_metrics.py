"""
ODW.ai Desk — Unit Tests for the Prometheus /metrics Endpoint

The README claims Prometheus metrics at /metrics; these tests confirm the
endpoint is mounted and exposes the metrics defined in desk.observability.metrics.
"""

from fastapi.testclient import TestClient

from desk.main import app


def test_metrics_endpoint_returns_200():
    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    # Prometheus text exposition format content type.
    assert response.headers["content-type"].startswith("text/plain")


def test_metrics_endpoint_exposes_desk_metrics():
    client = TestClient(app)
    response = client.get("/metrics")

    body = response.text
    # A representative sample of the defined collectors is present.
    assert "desk_messages_received_total" in body
    assert "desk_app_info" in body
