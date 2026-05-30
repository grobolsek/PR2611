"""Advanced crime prediction model using Random Forest.

Fixes the 0% probability issue by refining negative sampling and incorporating
more detailed temporal (day of week, month, hour) and spatial features.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def prepare_advanced_dataset(df_crimes: pd.DataFrame, df_imm: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, LabelEncoder]]:
    """Prepare a richer feature set and perform smarter negative sampling."""
    df = df_crimes.copy()

    # 1. Cleaning and preparing temporal features
    df["Hour"] = pd.to_numeric(df["UraStoritve"], errors="coerce").fillna(12).astype(int)
    df["MesecStoritve"] = df["MesecStoritve"].astype(str).str.strip()
    df_imm["MesecStoritve"] = df_imm["MesecStoritve"].astype(str).str.strip()

    # Assume the database contains a 'DanVTednu' column (e.g., 1-7 or MON-SUN)
    if "DanVTednu" in df.columns:
        df["Day"] = df["DanVTednu"].astype(str).str.strip()
    else:
        df["Day"] = "MON"  # Fallback value if the column does not exist

    # Use a more precise location (if UEStoritveKD or ObcinaStoritveKD exists)
    # If UE is not available, replace below with 'PUStoritveKD'
    location_col = "UEStoritveKD" if "UEStoritveKD" in df.columns else "PUStoritveKD"
    df["Location"] = df[location_col].astype(str).str.strip()

    # Merge with immigration data
    df = pd.merge(df, df_imm, on="MesecStoritve", how="left")
    df["Izdana_Dovoljenja_Mesec"] = df["Izdana_Dovoljenja_Mesec"].fillna(df["Izdana_Dovoljenja_Mesec"].mean())

    # Label actual crimes
    df["Crime_Occurred"] = 1

    # Keep only the important columns for the model
    features_to_keep = ["Hour", "Day", "Location", "Izdana_Dovoljenja_Mesec", "Crime_Occurred", "KD_SKUPINA"]
    df_real = df[features_to_keep].copy()

    # Instead of completely random numbers, we take real rows and shuffle their locations and hours,
    # thereby creating realistic "fake" events where no crime actually occurred.
    logger.info("Performing advanced negative sample generation...")
    df_fake = df_real.copy()
    df_fake["Crime_Occurred"] = 0
    df_fake["KD_SKUPINA"] = "NO_CRIME"
    df_fake["Location"] = df_fake["Location"].sample(frac=1).reset_index(drop=True)  # Shuffle locations
    df_fake["Hour"] = df_fake["Hour"].sample(frac=1).reset_index(drop=True)  # Shuffle hours

    # Combine into the final dataset
    df_combined = pd.concat([df_real, df_fake], ignore_index=True)

    # 3. Label Encoding for textual data (Day, Location)
    encoders = {}
    for col in ["Day", "Location"]:
        le = LabelEncoder()
        df_combined[f"{col}_Encoded"] = le.fit_transform(df_combined[col])
        encoders[col] = le

    return df_combined, encoders


def main() -> None:
    base_dir = Path(__file__).parents[2]

    crime_file = base_dir / "data" / "formatted" / "kd2024.csv"
    imm_file = base_dir / "data" / "immigration" / "monthly_immigration_trends.csv"

    if not crime_file.exists() or not imm_file.exists():
        logger.error("Please check the file paths for kd2024.csv and monthly_immigration_trends.csv")
        return

    df_crimes = pd.read_csv(crime_file, encoding="utf-8", quoting=1, low_memory=False)
    df_imm = pd.read_csv(imm_file, encoding="utf-8")

    # Prepare data and retrieve encoders
    data, encoders = prepare_advanced_dataset(df_crimes, df_imm)

    # Features for the model
    feature_cols = ["Hour", "Day_Encoded", "Location_Encoded", "Izdana_Dovoljenja_Mesec"]
    X = data[feature_cols]

    # --- TRAINING MODEL 1 (Probability) ---
    y_prob = data["Crime_Occurred"]
    X_train, X_test, y_train, y_test = train_test_split(X, y_prob, test_size=0.2, random_state=42)

    # Set min_samples_leaf to prevent the model from overfitting
    # This drastically helps to avoid getting constant 0% or 100% probabilities
    model_prob = RandomForestClassifier(n_estimators=100, min_samples_leaf=5, random_state=42)
    logger.info("Training advanced model for probability prediction...")
    model_prob.fit(X_train, y_train)

    # --- TRAINING MODEL 2 (Crime Type) ---
    real_crimes = data[data["Crime_Occurred"] == 1].copy()
    le_type = LabelEncoder()
    real_crimes["KD_SKUPINA_Encoded"] = le_type.fit_transform(real_crimes["KD_SKUPINA"].astype(str))

    X_type = real_crimes[feature_cols]
    y_type = real_crimes["KD_SKUPINA_Encoded"]

    X_t_train, X_t_test, y_t_train, y_t_test = train_test_split(X_type, y_type, test_size=0.2, random_state=42)
    model_type = RandomForestClassifier(n_estimators=100, min_samples_leaf=3, random_state=42)
    logger.info("Training advanced model for type prediction...")
    model_type.fit(X_t_train, y_t_train)

    # INPUT SIMULATION (You can modify these parameters for testing)
    input_hour = 10
    input_day = "PONEDELJEK"  # Example: 'PONEDELJEK', 'TOREK', 'PETEK'...
    input_location = "PU LJUBLJANA"  # Enter UE or PU using uppercase (e.g., 'PU LJUBLJANA', 'PU MARIBOR', 'PU CELJE')
    input_immigration = 7000

    try:
        # Convert input using the trained encoders
        day_encoded = encoders["Day"].transform([input_day])[0]
        location_encoded = encoders["Location"].transform([input_location])[0]

        test_input = pd.DataFrame(
            [[input_hour, day_encoded, location_encoded, input_immigration]],
            columns=feature_cols,
        )

        # 1. Probability Calculation
        prob = model_prob.predict_proba(test_input)[0][1] * 100
        print(f"Input: Hour={input_hour}, Day={input_day}, Location={input_location}, Immigration={input_immigration}")
        print(f"-> Crime Probability: {prob:.2f}%")

        # 2. Crime Type Calculation
        type_encoded = model_type.predict(test_input)
        type_name = le_type.inverse_transform(type_encoded)[0]
        print(f"-> If it occurs, it will most likely be: '{type_name}'")

    except ValueError as e:
        logger.error(f"Error during test data input processing: {e}")
        print("Hint: Verify that you entered a day or location that actually exists in your database!")


if __name__ == "__main__":
    main()
