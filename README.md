This is our repository for the NASA Farming Challenge, a brief explanation of how it works below.

1. We went to https://quickstats.nass.usda.gov/ and pulled a county farm yield file from the years 2025-2019 for a variety of crops that file is located under files -> usda_yields.csv
  
2. We went to cropland OS - https://www.nass.usda.gov/research-and-science/cropland/release?utm_source=chatgpt.com from the USDA.
   This site provides pixel specific data downloads of what crops are being grown in the US each year, the pixels are at a 30m resolution. In order to match this with our county level yield data we created a script that aggregates
   the cropland data into a 5 km square with a latitude and longitude located at the center. The script aggregates the pixels up and outputs a percentage of each crop grown in that 5km region as well as a pixel count.
   The script we run to aggregate the cropland data is in scripts -> Loadcdls.py and outputs files -> national_crop_rotations.py
  
3. We cleaned up the usda_yields file, pivoting the file to create a new column for every single crop yield in a given year at the county level. The script for this is pivot_yields.py and the output is county_yields_wide.csv
4. We then merged the CDL cropland OS data with our yields data at the county level. To do this we needed to geotag the lat/lon centroid of our cropland data into a specific county using geopandas. The script that does this is
   merge_cdls_to_yields.py. We weren't familiar with geopandas before this challenge so we used some gpt to help us write the script although it was much more straightforward then the cdl load. The output file from this process is
   is cdl_with_yields.py

6. Next we cleaned the cdl_with_yields.py file with the script cdl_with_yields_cleanup.py. This script primarily aggregates the cdls turning multiple rows per county into one county total that aggregates the total percentage of each crop
 in the county based on the weighted pixel count from each of the 5km square regions tagged to that county.

7. We then merged in the NASA_Power dataset acquired from https://power.larc.nasa.gov/ using nasa_data_merge.py to produce the final file nasa_data_merged.py.


For yield prediction training - training_data_files_generation.py creates our training data csvs. We then tested three different ML models on the corn, oats and soybean datasets

The results of the models were:

### MLP Neural Network Results

| Crop | MAE | MSE | R² |
|---|---:|---:|---:|
| Corn | 19.30 | 669.10 | 0.553 |
| Oats | 14.95 | 444.97 | -0.459 |
| Soybeans | 5.54 | 52.12 | 0.607 |

### Linear Regression Results

| Crop | MAE | MSE | R² |
|---|---:|---:|---:|
| Corn | 27.02 | 1178.28 | 0.212 |
| Oats | 12.89 | 298.16 | 0.022 |
| Soybeans | 8.07 | 110.90 | 0.165 |

### Random Forest Regression Results

| Crop | MAE | MSE | R² |
|---|---:|---:|---:|
| Corn | **15.76** | **447.60** | **0.701** |
| Oats | **10.92** | **211.87** | **0.305** |
| Soybeans | **4.74** | **37.95** | **0.714** |

As Random Forest performed the best we ran our entire original training datasets through the RandomForestRegressor in order to come up with a predicted yield for every year and every county for our three crops.

AI USAGE

Given this was a 48 hour hackathon and AI/SI usage was encouraged we used SI quite a bit, most of our data aggregation and data loading scripts were made either partially or entirely with chatgpt, the training of the models was not done with any substantial amount of gpt usage.

Scripts with heavy ai usage

loadcdls.py
cld_with_yields_cleanup.py
merge_cdls_to_yields.py
pivot_yields.py
training_data_files_generation.py

Scripts with minimal AI usage

linear_reg.py
neural_net.py
random_forest.py
nasa_data_merge.py



