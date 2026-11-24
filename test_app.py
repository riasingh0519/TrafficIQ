import asyncio
import json
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_root_dashboard():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SC-INT-74" in response.text
    assert "Oak Street" in response.text and "5th Avenue" in response.text

def test_predict_endpoint_free():
    payload = {
        "vehicle_flow_rate": 10.0,
        "average_speed_kmh": 62.0,
        "occupancy_rate": 0.12,
        "queue_length_meters": 15.0,
        "weather_factor": 0.0,
        "peak_hour": 0,
        "incident_flag": 0
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["intersection_id"] == "SC-INT-74"
    assert data["predicted_congestion_level"] in ["FREE", "LIGHT", "MODERATE", "HEAVY"]
    assert "confidence_scores" in data
    assert len(data["shap_feature_drivers"]) == 7
    # Verify SHAP rank ordering
    for idx, driver in enumerate(data["shap_feature_drivers"]):
        assert driver["importance_rank"] == idx + 1
        assert "feature" in driver
        assert "shap_value" in driver
        assert driver["impact"] in ["INCREASES_CONGESTION", "DECREASES_CONGESTION"]

def test_predict_endpoint_heavy():
    payload = {
        "vehicle_flow_rate": 62.0,
        "average_speed_kmh": 8.5,
        "occupancy_rate": 0.92,
        "queue_length_meters": 185.0,
        "weather_factor": 0.7,
        "peak_hour": 1,
        "incident_flag": 1
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["predicted_congestion_level"] == "HEAVY"
    assert data["confidence_scores"]["HEAVY"] > 0.5
    assert data["inference_latency_ms"] > 0

def test_api_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["intersection_id"] == "SC-INT-74"
    assert "adaptive_signal_control" in data
    assert 60 <= data["adaptive_signal_control"]["cycle_time"] <= 130
    assert 1 <= data["adaptive_signal_control"]["current_phase"] <= 4
    assert "v2i_hardware_metrics" in data
    assert data["v2i_hardware_metrics"]["rsu_status"] == "ONLINE"
    assert "packets" in data["v2i_hardware_metrics"]
    assert "BSM" in data["v2i_hardware_metrics"]["packets"]
    assert "SPaT" in data["v2i_hardware_metrics"]["packets"]
    assert "MAP" in data["v2i_hardware_metrics"]["packets"]

def test_simulation_state():
    response = client.get("/api/simulation/state")
    assert response.status_code == 200
    data = response.json()
    assert "vehicles" in data
    assert "signal_heads" in data
    assert len(data["signal_heads"]) == 8

def test_signal_override():
    override_payload = {
        "override_mode": "MANUAL",
        "forced_phase": 3,
        "duration_seconds": 25,
        "reason": "Traffic Officer Intervention"
    }
    response = client.post("/api/signal/override", json=override_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["forced_phase"] == 3

    # Reset
    reset_payload = {
        "override_mode": "RESUME_AUTO"
    }
    response = client.post("/api/signal/override", json=reset_payload)
    assert response.status_code == 200
    assert response.json()["mode"] == "ADAPTIVE_DENSITY_WEBSTER"

def test_inject_event():
    inject_payload = {
        "approach": "EAST",
        "incident_type": "ACCIDENT",
        "severity": "MODERATE"
    }
    response = client.post("/api/simulate/inject-event", json=inject_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "INJECTED"
    assert data["incident"]["type"] == "ACCIDENT"

    # Clear
    clear_payload = {
        "approach": "EAST",
        "incident_type": "CLEAR_INCIDENTS"
    }
    response = client.post("/api/simulate/inject-event", json=clear_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "CLEARED"

def test_websocket_stream():
    with client.websocket_connect("/ws/traffic-stream") as websocket:
        data_text = websocket.receive_text()
        data = json.loads(data_text)
        assert data["intersection_id"] == "SC-INT-74"
        assert "adaptive_signal_control" in data
        assert "v2i_hardware_metrics" in data
        assert "intersection_flow" in data
        assert "simulation_2d_state" in data
        assert "iot_sensor_health" in data
        assert "city_command_metrics" in data

        # Test sending command over websocket
        websocket.send_text(json.dumps({"action": "ping"}))
        reply_text = websocket.receive_text()
        reply = json.loads(reply_text)
        # Reply could be pong or next broadcast frame
        assert "type" in reply or "frame_sequence" in reply

def test_model_metrics():
    response = client.get("/api/model/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["overall_accuracy_pct"] >= 90.0
    assert data["model_file"] == "congestion_model.joblib"
    assert "class_metrics" in data
    assert "FREE" in data["class_metrics"]

if __name__ == "__main__":
    print("Running Smart Intersection Backend Test Suite...")
    test_root_dashboard()
    print("  [✓] test_root_dashboard passed")
    test_model_metrics()
    print("  [✓] test_model_metrics passed")
    test_predict_endpoint_free()
    print("  [✓] test_predict_endpoint_free passed")
    test_predict_endpoint_heavy()
    print("  [✓] test_predict_endpoint_heavy passed")
    test_api_status()
    print("  [✓] test_api_status passed")
    test_simulation_state()
    print("  [✓] test_simulation_state passed")
    test_signal_override()
    print("  [✓] test_signal_override passed")
    test_inject_event()
    print("  [✓] test_inject_event passed")
    test_websocket_stream()
    print("  [✓] test_websocket_stream passed")
    print("\n>>> ALL 8 TEST SUITE ASSERTIONS PASSED SUCCESSFULLY! <<<")
