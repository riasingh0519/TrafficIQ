import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from train_model import generate_traffic_dataset

def evaluate():
    print("=" * 65)
    print("      CONGESTION MODEL ACCURACY & PERFORMANCE EVALUATION      ")
    print("=" * 65)
    
    # 1. Load trained model artifact
    artifact = joblib.load("congestion_model.joblib")
    if isinstance(artifact, dict) and "model" in artifact:
        model = artifact["model"]
        features = artifact["features"]
        classes = artifact["classes"]
    else:
        model = artifact
        features = ["vehicle_flow_rate", "average_speed_kmh", "occupancy_rate", "queue_length_meters", "weather_factor", "peak_hour", "incident_flag"]
        classes = list(model.classes_)
        
    print(f"\n[+] Loaded Model: {type(model).__name__}")
    print(f"[+] Target Classes: {classes}")
    print(f"[+] Input Features: {features}\n")
    
    # 2. Generate a held-out test dataset
    df_test = generate_traffic_dataset(n_samples=2000, random_state=999)
    X_test = df_test[features]
    y_test = df_test["congestion_level"]
    
    # 3. Predict
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    
    print(f"{' OVERALL TEST ACCURACY ':^65}")
    print(f"{'':-^65}")
    print(f"{acc * 100:.2f}% ({np.sum(y_pred == y_test)} / {len(y_test)} samples correctly classified)")
    print(f"{'':-^65}\n")
    
    # 4. Detailed Classification Report
    print("--- Detailed Classification Report ---")
    print(classification_report(y_test, y_pred, digits=4))
    
    # 5. Confusion Matrix
    print("--- Confusion Matrix ---")
    cm = confusion_matrix(y_test, y_pred, labels=classes)
    cm_df = pd.DataFrame(cm, index=[f"Actual {c}" for c in classes], columns=[f"Pred {c}" for c in classes])
    print(cm_df)
    
    # 6. Feature Importances
    if hasattr(model, "feature_importances_"):
        print("\n--- Gini Feature Importances ---")
        fi = sorted(zip(features, model.feature_importances_), key=lambda x: x[1], reverse=True)
        for rank, (feat, imp) in enumerate(fi, 1):
            bar = "█" * int(imp * 40)
            print(f"  #{rank} {feat:<22}: {imp:.4f} {bar}")
            
    print("\n" + "=" * 65)

if __name__ == "__main__":
    evaluate()

