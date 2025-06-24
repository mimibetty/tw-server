import pandas as pd
import os

# --- Configuration ---
INPUT_CSV = 'trip_optimization_analysis/benchmark_results.csv'
OUTPUT_CSV = 'trip_optimization_analysis/benchmark_summary.csv'

def summarize_results():
    """
    Reads the raw benchmark results, calculates the average of key metrics
    for each configuration, and saves the summary to a new CSV file.
    """
    # Check if the input file exists
    if not os.path.exists(INPUT_CSV):
        print(f"[!] Error: Input file not found at '{INPUT_CSV}'")
        print("Please run 'benchmark_tsp_solvers.py' first to generate the raw data.")
        return

    print(f"[*] Reading raw data from '{INPUT_CSV}'...")
    df = pd.read_csv(INPUT_CSV)

    print("[*] Calculating averages and summarizing results...")
    
    # Group by the number of places and the algorithm
    # Then, calculate the mean for time and distance, and the sum for timeouts
    summary_df = df.groupby(['n_places', 'algorithm']).agg(
        avg_execution_time_s=('execution_time_s', 'mean'),
        avg_total_distance_m=('total_distance_m', 'mean'),
        num_timeouts=('timed_out', 'sum')
    ).reset_index()

    # Get the total number of trials to report timeout rate
    num_trials = df['trial'].max()
    summary_df['timeout_rate'] = summary_df['num_timeouts'] / num_trials

    # Round the numeric columns for cleaner output
    summary_df = summary_df.round({
        'avg_execution_time_s': 4,
        'avg_total_distance_m': 2,
        'timeout_rate': 2
    })
    
    try:
        # Save the summarized dataframe to a new CSV file
        summary_df.to_csv(OUTPUT_CSV, index=False)
        print(f"\n[+] Summary complete. Results saved to '{OUTPUT_CSV}'")
        print("\n--- Summary Data ---")
        print(summary_df.to_string())
        print("--------------------")

    except Exception as e:
        print(f"\n[!] Error saving summary to CSV: {e}")


if __name__ == "__main__":
    summarize_results() 