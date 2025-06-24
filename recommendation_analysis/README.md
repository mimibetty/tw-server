# Recommendation Analysis

This directory contains scripts for testing, analyzing, and visualizing the recommendation system.

## Scripts

### `test_recommendation_endpoint.py`

This script allows you to test the `GET /api/recommendations` endpoint with various filters and parameters. You can use it to see the recommendations a specific user would receive.

**Setup:**

1.  Make sure you have `requests` library installed:
    ```bash
    pip install requests
    ```

2.  Update the `API_BASE_URL` and `USER_TOKEN` variables in the script with your local server address and a valid JWT token for a test user.

**Usage:**

```bash
python recommendation_analysis/test_recommendation_endpoint.py
```

### `visualize_user_preferences.py`

This script fetches a user's recommendation statistics from the `GET /api/recommendations/stats` endpoint and visualizes their learned preferences for subcategories and subtypes using `matplotlib` and `seaborn`.

**Setup:**

1.  Install required libraries:
    ```bash
    pip install requests matplotlib seaborn pandas
    ```

2.  Update the `API_BASE_URL` and `USER_TOKEN` variables in the script with your local server address and a valid JWT token for a test user.

**Usage:**

```bash
python recommendation_analysis/visualize_user_preferences.py
```
The script will generate and save bar charts (`subcategory_preferences.png` and `subtype_preferences.png`) in the `recommendation_analysis` directory. 