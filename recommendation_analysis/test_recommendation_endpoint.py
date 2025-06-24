import requests
import json
import os

# --- Configuration ---
# Update with your local server URL
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000/api') 

# ** IMPORTANT **
# You must replace this with a valid JWT token for a test user.
# You can obtain this by logging in with a user account.
USER_TOKEN = os.environ.get('USER_TOKEN', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc1MDczMzE0NiwianRpIjoiYmJkZWZiMTYtYTE3MS00YzM5LTk0NDItMjRjOTcyMjBlNjVjIiwidHlwZSI6ImFjY2VzcyIsInN1YiI6IjRlOGE4Zjg3LTgwMjItNDJmMC1iNDQ2LThkMmIyMDRkZDNjZCIsIm5iZiI6MTc1MDczMzE0NiwiY3NyZiI6ImExODE0MDE0LTA4ZGMtNDcwNy05YWI1LWE5N2EyYjc1YTUwMCIsImV4cCI6MTc1MDgxOTU0Nn0.iY9sq3OSSIVD4g0qSp8IYHB2tpL9jLGEQq7G_mJfzr4')

# --- Test Parameters ---
# Modify these parameters to test different scenarios
RECOMMENDATION_PARAMS = {
    'place_type': 'all',  # 'all', 'hotels', 'restaurants', 'things-to-do'
    'page': 1,
    'size': 10,
    'min_rating': 4.0,
    # 'user_lat': 16.06,   # Optional: User's current latitude
    # 'user_lng': 108.22,  # Optional: User's current longitude
    # 'max_distance_km': 5 # Optional: Max distance from user
}


def test_recommendations():
    """
    Fetches and prints personalized recommendations for the configured user.
    """
    if not USER_TOKEN or USER_TOKEN == 'YOUR_JWT_TOKEN_HERE':
        print("="*60)
        print("!! ERROR: Please update the 'USER_TOKEN' variable in this script")
        print("!! with a valid JWT token from a logged-in user.")
        print("="*60)
        return

    headers = {
        'Authorization': f'Bearer {USER_TOKEN}'
    }

    url = f"{API_BASE_URL}/recommendations/"

    print(f"[*] Fetching recommendations from: {url}")
    print(f"[*] Parameters: {json.dumps(RECOMMENDATION_PARAMS, indent=2)}")

    try:
        response = requests.get(url, headers=headers, params=RECOMMENDATION_PARAMS)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        data = response.json()

        print("\n[+] Recommendations received successfully!")
        print("-" * 40)
        
        print(f"Paging Info: {data.get('paging')}")
        
        recommendations = data.get('data', [])
        print(f"Total recommendations in this page: {len(recommendations)}")
        print("-" * 40)

        if not recommendations:
            print("No recommendations found with the current filters.")
            return

        for i, rec in enumerate(recommendations, 1):
            print(f"\n{i}. {rec.get('name')} ({rec.get('type')})")
            print(f"   - Place ID: {rec.get('element_id')}")
            print(f"   - Rating: {rec.get('rating', 'N/A')}")
            print(f"   - Similarity Score: {rec.get('similarity_score', 'N/A'):.4f}")
            print(f"   - Reason: {rec.get('recommendation_reason', 'N/A')}")
            print(f"   - Is Favorite: {rec.get('is_favorite')}")
            if rec.get('city'):
                print(f"   - City: {rec['city'].get('name')}")

    except requests.exceptions.RequestException as e:
        print(f"\n[!] An error occurred: {e}")
        if e.response:
            print(f"    Status Code: {e.response.status_code}")
            try:
                print(f"    Response Body: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"    Response Body: {e.response.text}")

if __name__ == "__main__":
    test_recommendations() 