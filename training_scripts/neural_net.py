import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


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

# Instantiate separate scalers
corn_scaler = StandardScaler()
oats_scaler = StandardScaler()
soybeans_scaler = StandardScaler()

# Fit and transform training data
corn_X_train_scaled = corn_scaler.fit_transform(corn_X_train)
oats_X_train_scaled = oats_scaler.fit_transform(oats_X_train)
soybeans_X_train_scaled = soybeans_scaler.fit_transform(soybeans_X_train)

# Transform test data using the same fitted scalers
corn_X_test_scaled = corn_scaler.transform(corn_X_test)
oats_X_test_scaled = oats_scaler.transform(oats_X_test)
soybeans_X_test_scaled = soybeans_scaler.transform(soybeans_X_test)

# Instantiate linear regression models
corn_mlp_model = MLPRegressor(
    hidden_layer_sizes=(64, 32),
    max_iter=1000,
    random_state=42
)

oats_mlp_model = MLPRegressor(
    hidden_layer_sizes=(64, 32),
    max_iter=1000,
    random_state=42
)

soybeans_mlp_model = MLPRegressor(
    hidden_layer_sizes=(64, 32),
    max_iter=1000,
    random_state=42
)
# Fit linear regression models for each crop
corn_mlp_model.fit(corn_X_train_scaled, corn_y_train)
oats_mlp_model.fit(oats_X_train_scaled, oats_y_train)
soybeans_mlp_model.fit(soybeans_X_train_scaled, soybeans_y_train)

# Predict yields using test data
corn_predictions = corn_mlp_model.predict(corn_X_test_scaled)
oats_predictions = oats_mlp_model.predict(oats_X_test_scaled)
soybeans_predictions = soybeans_mlp_model.predict(soybeans_X_test_scaled)

# Calculate evaluation metrics
corn_mae = mean_absolute_error(corn_y_test, corn_predictions)
corn_mse = mean_squared_error(corn_y_test, corn_predictions)
corn_r2 = r2_score(corn_y_test, corn_predictions)

oats_mae = mean_absolute_error(oats_y_test, oats_predictions)
oats_mse = mean_squared_error(oats_y_test, oats_predictions)
oats_r2 = r2_score(oats_y_test, oats_predictions)

soybeans_mae = mean_absolute_error(soybeans_y_test, soybeans_predictions)
soybeans_mse = mean_squared_error(soybeans_y_test, soybeans_predictions)
soybeans_r2 = r2_score(soybeans_y_test, soybeans_predictions)

# Print formatted results
print("\n" + "=" * 50)
print("          MLP NEURAL NETWORK RESULTS")
print("=" * 50)

print(f"{'Crop':<12} {'MAE':>10} {'MSE':>12} {'R²':>8}")
print("-" * 50)

print(f"{'Corn':<12} {corn_mae:>10.2f} {corn_mse:>12.2f} {corn_r2:>8.3f}")
print(f"{'Oats':<12} {oats_mae:>10.2f} {oats_mse:>12.2f} {oats_r2:>8.3f}")
print(f"{'Soybeans':<12} {soybeans_mae:>10.2f} {soybeans_mse:>12.2f} {soybeans_r2:>8.3f}")

print("=" * 50)