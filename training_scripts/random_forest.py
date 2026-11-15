import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score, ConfusionMatrixDisplay
from scipy.stats import randint
from sklearn.impute import SimpleImputer
from sklearn.model_selection import RandomizedSearchCV, train_test_split
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error


BASE = Path(__file__).resolve().parent.parent
TRAINING_FILES = BASE / "training_files"

corn_df = pd.read_csv(TRAINING_FILES / "corn_training.csv")
corn_df = corn_df.dropna()

oats_df = pd.read_csv(TRAINING_FILES / "oats_training.csv")
soybeans_df = pd.read_csv(TRAINING_FILES / "soybeans_training.csv")

drop_cols = ["county_fips", "county_name", "lat", "lon", "year", "yield"]

corn_X = corn_df.drop(columns=drop_cols)
corn_y = corn_df["yield"]

oats_X = oats_df.drop(columns=drop_cols)
oats_y = oats_df["yield"]

soybeans_X = soybeans_df.drop(columns=drop_cols)
soybeans_y = soybeans_df["yield"]

# Split the dataset into training (80%) and testing (20%) sets.
corn_X_train, corn_X_test, corn_y_train, corn_y_test = train_test_split(corn_X, corn_y, test_size=0.2, random_state=42)
oats_X_train, oats_X_test, oats_y_train, oats_y_test = train_test_split(oats_X, oats_y, test_size=0.2, random_state=42)
soybeans_X_train, soybeans_X_test, soybeans_y_train, soybeans_y_test = train_test_split(soybeans_X, soybeans_y, test_size=0.2, random_state=42)

# Instantiate linear regression models
corn_rf_model = RandomForestRegressor(n_estimators=100,
    random_state=42)
oats_rf_model = RandomForestRegressor(n_estimators=100,
    random_state=42)
soybeans_rf_model = RandomForestRegressor(n_estimators=100,
    random_state=42)

# Fit linear regression models for each crop
corn_rf_model.fit(corn_X_train, corn_y_train)
oats_rf_model.fit(oats_X_train, oats_y_train)
soybeans_rf_model.fit(soybeans_X_train, soybeans_y_train)

# Predict yields using test data
corn_predictions = corn_rf_model.predict(corn_X_test)
oats_predictions = oats_rf_model.predict(oats_X_test)
soybeans_predictions = soybeans_rf_model.predict(soybeans_X_test)

corn_mae = mean_absolute_error(corn_y_test, corn_predictions)
corn_mse = mean_squared_error(corn_y_test, corn_predictions)
corn_r2 = r2_score(corn_y_test, corn_predictions)

oats_mae = mean_absolute_error(oats_y_test, oats_predictions)
oats_mse = mean_squared_error(oats_y_test, oats_predictions)
oats_r2 = r2_score(oats_y_test, oats_predictions)

soybeans_mae = mean_absolute_error(soybeans_y_test, soybeans_predictions)
soybeans_mse = mean_squared_error(soybeans_y_test, soybeans_predictions)
soybeans_r2 = r2_score(soybeans_y_test, soybeans_predictions)

# Print results
print("\n" + "=" * 45)
print("       RANDOM FOREST REGRESSION RESULTS")
print("=" * 45)

print(f"{'Crop':<12} {'MAE':>10} {'MSE':>12} {'R²':>8}")
print("-" * 45)

print(f"{'Corn':<12} {corn_mae:>10.2f} {corn_mse:>12.2f} {corn_r2:>8.3f}")
print(f"{'Oats':<12} {oats_mae:>10.2f} {oats_mse:>12.2f} {oats_r2:>8.3f}")
print(f"{'Soybeans':<12} {soybeans_mae:>10.2f} {soybeans_mse:>12.2f} {soybeans_r2:>8.3f}")

print("=" * 45)


# Predict yields for every row in each dataset
corn_df["predicted_yield"] = corn_rf_model.predict(corn_X)
oats_df["predicted_yield"] = oats_rf_model.predict(oats_X)
soybeans_df["predicted_yield"] = soybeans_rf_model.predict(soybeans_X)

# Save datasets with predictions
corn_df.to_csv(TRAINING_FILES / "corn_with_predictions.csv", index=False)
oats_df.to_csv(TRAINING_FILES / "oats_with_predictions.csv", index=False)
soybeans_df.to_csv(TRAINING_FILES / "soybeans_with_predictions.csv", index=False)

print("Predictions generated and saved successfully!")