import os
import json
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.preprocessing import LabelEncoder
import joblib

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "synthetic_financial_data.csv")
MODEL_FILE = os.path.join(BASE_DIR, "risk_model.json")
ENCODER_FILE = os.path.join(BASE_DIR, "label_encoder.pkl")

# Track 2 Features
FEATURES = [
    "monthly_txn_volume",
    "avg_ticket_size",
    "cash_ratio",
    "cross_border_ratio",
    "late_payment_rate",
    "business_age_years",
    "sector_risk_score",
    "director_count",
    "anomaly_risk_score"
]

def generate_synthetic_data(num_samples=10000):
    np.random.seed(42)
    
    # Generate random features
    monthly_txn_volume = np.random.randint(10, 5000, num_samples)
    avg_ticket_size = np.random.uniform(1000, 5000000, num_samples)
    cash_ratio = np.random.uniform(0.0, 1.0, num_samples)
    cross_border_ratio = np.random.uniform(0.0, 1.0, num_samples)
    late_payment_rate = np.random.uniform(0.0, 0.8, num_samples)
    business_age_years = np.random.uniform(0.1, 20.0, num_samples)
    sector_risk_score = np.random.uniform(0.1, 0.9, num_samples)
    director_count = np.random.randint(1, 10, num_samples)
    anomaly_risk_score = np.random.uniform(0.0, 5.0, num_samples)
    
    # Heuristic to assign target risk tiers
    scores = (
        (cash_ratio * 0.2) + 
        (cross_border_ratio * 0.2) + 
        (anomaly_risk_score / 5.0 * 0.4) + 
        (sector_risk_score * 0.2)
    )
    
    # Increase risk if business is very young and doing huge volumes
    risk_multiplier = np.where((business_age_years < 1.0) & (avg_ticket_size > 1000000), 1.3, 1.0)
    scores = np.clip(scores * risk_multiplier, 0.0, 1.0)
    
    tiers = []
    for s in scores:
        if s >= 0.75:
            tiers.append("critical")
        elif s >= 0.55:
            tiers.append("high")
        elif s >= 0.35:
            tiers.append("medium")
        else:
            tiers.append("low")
            
    df = pd.DataFrame({
        "monthly_txn_volume": monthly_txn_volume,
        "avg_ticket_size": avg_ticket_size,
        "cash_ratio": cash_ratio,
        "cross_border_ratio": cross_border_ratio,
        "late_payment_rate": late_payment_rate,
        "business_age_years": business_age_years,
        "sector_risk_score": sector_risk_score,
        "director_count": director_count,
        "anomaly_risk_score": anomaly_risk_score,
        "risk_tier": tiers
    })
    
    df.to_csv(DATA_FILE, index=False)
    print(f"Generated {num_samples} samples at {DATA_FILE}")
    return df

def train_model(df):
    X = df[FEATURES]
    y_labels = df["risk_tier"]
    
    le = LabelEncoder()
    y = le.fit_transform(y_labels)
    
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=42
    )
    
    model.fit(X, y)
    
    model.save_model(MODEL_FILE)
    joblib.dump(le, ENCODER_FILE)
    
    print(f"Model saved to {MODEL_FILE}")
    print(f"Label encoder saved to {ENCODER_FILE}")
    print(f"Classes: {le.classes_}")

if __name__ == "__main__":
    df = generate_synthetic_data()
    train_model(df)
