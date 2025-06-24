import requests
import json
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# --- Configuration ---
# Update with your local server URL
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000/api')

# ** IMPORTANT **
# You must replace this with a valid JWT token for a test user.
# You can obtain this by logging in with a user account.
USER_TOKEN = os.environ.get('USER_TOKEN', 'Key')

# --- Chart Configuration ---
OUTPUT_DIR = 'recommendation_analysis'


def fetch_user_stats():
    """
    Fetches recommendation statistics for the configured user.
    """
    if not USER_TOKEN or USER_TOKEN == 'YOUR_JWT_TOKEN_HERE':
        print("="*60)
        print("!! ERROR: Please update the 'USER_TOKEN' variable in this script")
        print("!! with a valid JWT token from a logged-in user.")
        print("="*60)
        return None

    headers = {'Authorization': f'Bearer {USER_TOKEN}'}
    url = f"{API_BASE_URL}/recommendations/stats"

    print(f"[*] Fetching user preference stats from: {url}")

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        stats = response.json()
        print("[+] Stats received successfully!")
        print(json.dumps(stats, indent=2))
        return stats
    except requests.exceptions.RequestException as e:
        print(f"\n[!] An error occurred: {e}")
        if e.response:
            print(f"    Status Code: {e.response.status_code}")
            try:
                print(f"    Response Body: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"    Response Body: {e.response.text}")
        return None


def plot_preferences(data, key, title, filename):
    """
    Generates and saves a bar chart for user preferences.
    """
    if not data or not data.get(key):
        print(f"\nNo data found for '{key}'. Skipping plot.")
        return

    pref_data = data[key]
    if not isinstance(pref_data, dict) or not pref_data:
        print(f"Data for '{key}' is not in the expected format. Skipping plot.")
        return
        
    df = pd.DataFrame(list(pref_data.items()), columns=['Category', 'Score'])
    df = df.sort_values('Score', ascending=False)

    plt.figure(figsize=(12, 8))
    sns.barplot(x='Score', y='Category', data=df, palette='viridis', orient='h')
    
    plt.title(title, fontsize=16)
    plt.xlabel('Preference Score (Normalized)', fontsize=12)
    plt.ylabel('Category', fontsize=12)
    plt.tight_layout()

    # Create directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    output_path = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(output_path)
    print(f"\n[+] Chart saved to: {output_path}")
    plt.close()


def main():
    stats = fetch_user_stats()
    if stats:
        # Plot top subcategories
        plot_preferences(
            stats,
            'top_subcategories',
            'User Preference: Top 5 Subcategories',
            'subcategory_preferences.png'
        )

        # Plot top subtypes
        plot_preferences(
            stats,
            'top_subtypes',
            'User Preference: Top 5 Subtypes',
            'subtype_preferences.png'
        )


if __name__ == "__main__":
    main() 