import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib
import os

def generate_traffic_dataset(n_samples=4000, random_state=42):
    np.random.seed(random_state)
    
    # 1. vehicle_flow_rate (vehicles per minute): 5 to 65
    vehicle_flow = np.random.uniform(5, 65, n_samples)
    
    # 2. average_speed_kmh: 5 to 75 km/h
    # In general, higher flow implies lower speed, but with stochastic variations
    base_speed = 70 - (vehicle_flow * 0.8) + np.random.normal(0, 5, n_samples)
    average_speed = np.clip(base_speed, 6, 75)
    
    # 3. occupancy_rate (0.0 to 1.0 / 0% to 100%)
    occupancy = np.clip((vehicle_flow / 70.0) * 0.75 + (1 - average_speed / 75.0) * 0.25 + np.random.normal(0, 0.05, n_samples), 0.02, 0.98)
    
    # 4. queue_length_meters: 0 to 220m
    queue_len = np.clip(occupancy * 180 + (vehicle_flow > 40) * 35 + np.random.normal(0, 10, n_samples), 0, 250)
    
    # 5. weather_factor: 0=Clear (0.0), 1=Rain (0.3), 2=Snow/Ice (0.7)
    weather_factor = np.random.choice([0.0, 0.3, 0.7], size=n_samples, p=[0.70, 0.22, 0.08])
    
    # 6. peak_hour: 0 or 1
    peak_hour = np.random.choice([0, 1], size=n_samples, p=[0.65, 0.35])
    
    # 7. incident_flag: 0 or 1
    incident_flag = np.random.choice([0, 1], size=n_samples, p=[0.95, 0.05])
    
    # Adjust parameters if incident occurs
    queue_len[incident_flag == 1] += np.random.uniform(40, 90, np.sum(incident_flag == 1))
    average_speed[incident_flag == 1] = np.clip(average_speed[incident_flag == 1] * 0.45, 5, 20)
    occupancy[incident_flag == 1] = np.clip(occupancy[incident_flag == 1] + 0.35, 0.1, 0.99)
    
    # Composite congestion score (0 to 100)
    score = (
        (occupancy * 40.0) +
        ((75 - average_speed) / 75.0 * 25.0) +
        (np.clip(queue_len / 200.0, 0, 1) * 25.0) +
        (weather_factor * 10.0) +
        (incident_flag * 20.0) +
        np.random.normal(0, 3, n_samples)
    )
    
    # Classes: FREE (0-30), LIGHT (30-55), MODERATE (55-75), HEAVY (75+)
    classes = []
    for s in score:
        if s < 32:
            classes.append("FREE")
        elif s < 56:
            classes.append("LIGHT")
        elif s < 76:
            classes.append("MODERATE")
        else:
            classes.append("HEAVY")
            
    df = pd.DataFrame({
        "vehicle_flow_rate": np.round(vehicle_flow, 2),
        "average_speed_kmh": np.round(average_speed, 2),
        "occupancy_rate": np.round(occupancy, 3),
        "queue_length_meters": np.round(queue_len, 2),
        "weather_factor": weather_factor,
        "peak_hour": peak_hour,
        "incident_flag": incident_flag,
        "congestion_level": classes
    })
    return df

def train_and_save():
    print("Generating synthetic traffic telemetry dataset...")
    df = generate_traffic_dataset(n_samples=5000)
    print(f"Dataset generated: {len(df)} samples")
    print(df['congestion_level'].value_counts())
    
    feature_cols = [
        "vehicle_flow_rate",
        "average_speed_kmh",
        "occupancy_rate",
        "queue_length_meters",
        "weather_factor",
        "peak_hour",
        "incident_flag"
    ]
    
    X = df[feature_cols]
    y = df["congestion_level"]
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    clf = RandomForestClassifier(
        n_estimators=100,
        max_depth=12,
        min_samples_split=4,
        random_state=42,
        n_jobs=-1
    )
    
    print("Training RandomForestClassifier...")
    clf.fit(X_train, y_train)
    
    y_pred = clf.predict(X_test)
    print("\nModel Evaluation Report:")
    print(classification_report(y_test, y_pred))
    
    artifact = {
        "model": clf,
        "features": feature_cols,
        "classes": list(clf.classes_),
        "version": "1.0.0",
        "intersection_id": "SC-INT-74"
    }
    
    model_filename = "congestion_model.joblib"
    joblib.dump(artifact, model_filename)
    print(f"Model successfully saved to {model_filename} (size: {os.path.getsize(model_filename) / 1024:.1f} KB)")

if __name__ == "__main__":
    train_and_save()

