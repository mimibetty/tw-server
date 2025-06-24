import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import numpy as np

# --- Configuration ---
INPUT_CSV = 'trip_optimization_analysis/benchmark_summary.csv'
OUTPUT_DIR = 'trip_optimization_analysis'
DP_ALGORITHM_NAME = 'Dynamic Programming'
OR_TOOLS_ALGORITHM_NAME = 'Google OR-Tools'

def plot_execution_time(df):
    """Plots the average execution time vs. the number of places."""
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 8))

    # Plot data for each algorithm
    for name, group in df.groupby('algorithm'):
        ax.plot(group['n_places'], group['avg_execution_time_s'], marker='o', linestyle='-', label=name)

    # --- Formatting ---
    ax.set_title('Execution Time vs. Number of Places', fontsize=16, fontweight='bold')
    ax.set_xlabel('Number of Places (n)', fontsize=12)
    ax.set_ylabel('Average Execution Time (seconds)', fontsize=12)
    ax.set_yscale('log') # Use a logarithmic scale to see the huge difference
    ax.legend()
    
    # Add a horizontal line for the DP timeout
    dp_timeout = 10.0
    ax.axhline(y=dp_timeout, color='red', linestyle='--', label=f'DP Timeout ({dp_timeout}s)')
    ax.legend() # Call legend again to include the timeout line

    # Add text annotation for clarity
    ax.text(df['n_places'].min(), dp_timeout * 1.1, 'DP Timeout Threshold', color='red', va='bottom')
    
    plt.tight_layout()
    output_path = os.path.join(OUTPUT_DIR, '1_execution_time_comparison.png')
    plt.savefig(output_path)
    print(f"[+] Execution time plot saved to '{output_path}'")
    plt.close()


def plot_total_distance(df):
    """Plots the average total distance vs. the number of places."""
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 8))

    # Filter out timed-out/failed results as they have 'inf' distance
    df_filtered = df[df['avg_total_distance_m'] != np.inf].copy()
    df_filtered['avg_total_distance_km'] = df_filtered['avg_total_distance_m'] / 1000

    for name, group in df_filtered.groupby('algorithm'):
        ax.plot(group['n_places'], group['avg_total_distance_km'], marker='o', linestyle='-', label=name)

    # --- Formatting ---
    ax.set_title('Solution Quality vs. Number of Places', fontsize=16, fontweight='bold')
    ax.set_xlabel('Number of Places (n)', fontsize=12)
    ax.set_ylabel('Average Route Distance (km)', fontsize=12)
    ax.legend()
    
    plt.tight_layout()
    output_path = os.path.join(OUTPUT_DIR, '2_solution_quality_comparison.png')
    plt.savefig(output_path)
    print(f"[+] Solution quality plot saved to '{output_path}'")
    plt.close()


def plot_quality_difference(df):
    """
    Plots the percentage difference in route distance between OR-Tools and DP
    for cases where DP could find an optimal solution.
    """
    # Isolate DP and OR-Tools data
    dp_df = df[(df['algorithm'] == DP_ALGORITHM_NAME) & (df['timeout_rate'] == 0)]
    or_df = df[df['algorithm'] == OR_TOOLS_ALGORITHM_NAME]

    # Merge them on n_places to compare
    comparison_df = pd.merge(
        dp_df, or_df, on='n_places',
        suffixes=('_dp', '_or')
    )
    
    if comparison_df.empty:
        print("[!] No data available where Dynamic Programming succeeded. Skipping quality difference plot.")
        return

    # Calculate percentage difference: ((OR_Tools - DP) / DP) * 100
    comparison_df['distance_diff_percent'] = (
        (comparison_df['avg_total_distance_m_or'] - comparison_df['avg_total_distance_m_dp']) /
         comparison_df['avg_total_distance_m_dp']
    ) * 100

    # --- Plotting ---
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 7))

    colors = ['green' if x <= 0 else 'orange' for x in comparison_df['distance_diff_percent']]
    
    sns.barplot(
        x='n_places', y='distance_diff_percent', data=comparison_df,
        palette=colors, ax=ax
    )

    ax.axhline(0, color='grey', linewidth=0.8, linestyle='--')
    ax.set_title('OR-Tools vs. Optimal (DP) Solution Quality', fontsize=16, fontweight='bold')
    ax.set_xlabel('Number of Places (n)', fontsize=12)
    ax.set_ylabel('Distance Difference (%)', fontsize=12)
    # ax.text(0.01, 0.05, 'Negative values mean OR-Tools found a better or equal path',
    #         transform=ax.transAxes, fontsize=10, style='italic')

    plt.tight_layout()
    output_path = os.path.join(OUTPUT_DIR, '3_or_tools_optimality_gap.png')
    plt.savefig(output_path)
    print(f"[+] Optimality gap plot saved to '{output_path}'")
    plt.close()


def main():
    """Main function to load data and generate all plots."""
    if not os.path.exists(INPUT_CSV):
        print(f"[!] Error: Summary file not found at '{INPUT_CSV}'")
        print("Please run 'benchmark_tsp_solvers.py' and 'summarize_results.py' first.")
        return
        
    print(f"[*] Loading summary data from '{INPUT_CSV}'...")
    df = pd.read_csv(INPUT_CSV)
    
    # Generate Plots
    plot_execution_time(df)
    plot_total_distance(df)
    plot_quality_difference(df)
    
    print("\n[+] All plots have been generated successfully.")

if __name__ == "__main__":
    # Ensure you have the required libraries
    try:
        import pandas
        import matplotlib
        import seaborn
    except ImportError:
        print("[!] Missing required libraries. Please run:")
        print("pip install pandas matplotlib seaborn")
    else:
        main() 