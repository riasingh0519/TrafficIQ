import os
import time
import joblib
import numpy as np
import pandas as pd
import shap
from datetime import datetime, timezone
from typing import Dict, Any, List
from models import TrafficSensorInput, PredictionResponse, ShapFeatureDriver

class MLEngine:
    def __init__(self, model_path: str = "congestion_model.joblib"):
        self.model_path = model_path
        self.model = None
        self.features: List[str] = []
        self.classes: List[str] = []
        self.explainer: Optional[shap.TreeExplainer] = None
        self.load_model()

    def load_model(self):
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found at: {self.model_path}")
        
        artifact = joblib.load(self.model_path)
        if isinstance(artifact, dict) and "model" in artifact:
            self.model = artifact["model"]
            self.features = artifact.get("features", [
                "vehicle_flow_rate", "average_speed_kmh", "occupancy_rate",
                "queue_length_meters", "weather_factor", "peak_hour", "incident_flag"
            ])
            self.classes = list(artifact.get("classes", self.model.classes_))
        else:
            self.model = artifact
            self.features = [
                "vehicle_flow_rate", "average_speed_kmh", "occupancy_rate",
                "queue_length_meters", "weather_factor", "peak_hour", "incident_flag"
            ]
            self.classes = list(self.model.classes_)
            
        # Initialize SHAP TreeExplainer
        self.explainer = shap.TreeExplainer(self.model)
        print(f"[MLEngine] Loaded model from {self.model_path} with classes: {self.classes}")

    def predict(self, sensor_input: TrafficSensorInput) -> PredictionResponse:
        t_start = time.perf_counter()
        
        input_data = {
            "vehicle_flow_rate": sensor_input.vehicle_flow_rate,
            "average_speed_kmh": sensor_input.average_speed_kmh,
            "occupancy_rate": sensor_input.occupancy_rate,
            "queue_length_meters": sensor_input.queue_length_meters,
            "weather_factor": sensor_input.weather_factor,
            "peak_hour": sensor_input.peak_hour,
            "incident_flag": sensor_input.incident_flag
        }
        
        df = pd.DataFrame([input_data])[self.features]
        
        # Probabilities
        probs = self.model.predict_proba(df)[0]
        class_prob_map = {cls_name: round(float(prob), 4) for cls_name, prob in zip(self.classes, probs)}
        
        # Predicted class
        pred_class_idx = int(np.argmax(probs))
        predicted_class = self.classes[pred_class_idx]
        
        # SHAP calculation
        shap_raw = self.explainer.shap_values(df)
        shap_arr = np.array(shap_raw)
        
        # Handle SHAP output dimensions:
        # Depending on shap version, shape can be (1, n_features, n_classes) or list of (1, n_features)
        if isinstance(shap_raw, list):
            class_shap = shap_raw[pred_class_idx][0]
        elif len(shap_arr.shape) == 3:
            # (1, n_features, n_classes)
            class_shap = shap_arr[0, :, pred_class_idx]
        else:
            class_shap = shap_arr[0]
            
        drivers: List[Dict[str, Any]] = []
        for feat_name, shap_val in zip(self.features, class_shap):
            val = float(input_data[feat_name])
            s_val = float(shap_val)
            
            # Determine impact relative to congestion
            if predicted_class in ["MODERATE", "HEAVY"]:
                impact = "INCREASES_CONGESTION" if s_val > 0 else "DECREASES_CONGESTION"
            else:
                impact = "DECREASES_CONGESTION" if s_val > 0 else "INCREASES_CONGESTION"
                
            drivers.append({
                "feature": feat_name,
                "value": round(val, 3),
                "shap_value": round(s_val, 4),
                "abs_shap": abs(s_val),
                "impact": impact
            })
            
        # Rank by absolute SHAP impact
        drivers.sort(key=lambda d: d["abs_shap"], reverse=True)
        shap_feature_drivers = [
            ShapFeatureDriver(
                feature=d["feature"],
                value=d["value"],
                shap_value=d["shap_value"],
                impact=d["impact"],
                importance_rank=rank + 1
            )
            for rank, d in enumerate(drivers)
        ]
        
        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
        
        return PredictionResponse(
            intersection_id="SC-INT-74",
            intersection_name="Oak Street & 5th Avenue",
            timestamp=datetime.now(timezone.utc),
            predicted_congestion_level=predicted_class,
            confidence_scores=class_prob_map,
            shap_feature_drivers=shap_feature_drivers,
            inference_latency_ms=latency_ms
        )

# Global singleton
ml_engine = MLEngine()

