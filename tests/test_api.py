from fastapi.testclient import TestClient

from app.main import app


def test_consumer_isolated_from_admin_and_admin_can_replay_trace():
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/admin").status_code == 200
        consumer = client.post("/api/auth/consumer").json()
        consumer_headers = {"Authorization": f"Bearer {consumer['access_token']}"}

        response = client.post(
            "/api/consumer/chat",
            headers=consumer_headers,
            json={"question": "预算 100 元，手冲新手想买巧克力坚果风味的咖啡豆", "budget": 100, "brew_method": "hand_drip", "experience": "beginner"},
        )
        assert response.status_code == 200
        decision = response.json()
        assert decision["recommendations"]
        assert all(item["price"] <= 100 for item in decision["recommendations"])
        assert decision["citations"]

        assert client.get("/api/admin/insights", headers=consumer_headers).status_code == 403

        admin = client.post("/api/auth/admin", json={"email": "merchant@shopsage.demo", "password": "demo-admin-password"}).json()
        admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
        assert client.get("/api/admin/insights", headers=admin_headers).status_code == 200
        trace = client.get(f"/api/admin/agent-runs/{decision['trace_id']}", headers=admin_headers)
        assert trace.status_code == 200
        assert any(step["name"] == "citation_validator" for step in trace.json()["steps"])
