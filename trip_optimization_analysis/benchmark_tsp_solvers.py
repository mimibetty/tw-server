import sys
import os
import time
import random
import pandas as pd
from multiprocessing import Process, Queue

# Add project root to the Python path to allow importing from 'app'
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now we can import the necessary functions from the trips API
try:
    from app.api.trips import (
        calculate_distance_matrix,
        solve_tsp_dp,
        solve_tsp_or_tools,
        calculate_total_distance
    )
except ImportError as e:
    print(f"Error importing functions from app.api.trips: {e}")
    print("Please ensure the script is run from the project's root directory or that the path is correct.")
    sys.exit(1)

# --- Configuration ---
# Test with a range of place counts. DP is expected to time out for n > 15.
N_PLACES_TO_TEST = [5, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 25, 30, 40, 50, 60]
NUM_TRIALS = 5  # Number of random trials for each place count to get stable results
DP_TIMEOUT_SECONDS = 10.0
OR_TOOLS_TIMEOUT_SECONDS = 15.0 # OR-Tools is faster, but we give it a generous timeout
OUTPUT_CSV = 'trip_optimization_analysis/benchmark_results.csv'

# Geographic bounds for generating random coordinates (approximating Da Nang)
LAT_RANGE = (15.9, 16.2)
LON_RANGE = (108.1, 108.4)


def generate_random_places(num_places):
    """Generates a list of random place dictionaries with lat/lon."""
    places = []
    for _ in range(num_places):
        places.append({
            'latitude': random.uniform(*LAT_RANGE),
            'longitude': random.uniform(*LON_RANGE)
        })
    return places


def dp_solver_process(distance_matrix, result_queue):
    """Function to be run in a separate process for the DP solver."""
    route = solve_tsp_dp(distance_matrix)
    result_queue.put(route)


def run_dp_with_timeout(distance_matrix, timeout):
    """
    Runs the DP solver in a separate process with a timeout.
    Returns the route or None if it times out.
    """
    result_queue = Queue()
    p = Process(target=dp_solver_process, args=(distance_matrix, result_queue))
    
    start_time = time.perf_counter()
    p.start()
    p.join(timeout)
    
    if p.is_alive():
        p.terminate()
        p.join()
        return None, timeout # Return None for route and the timeout duration

    end_time = time.perf_counter()
    route = result_queue.get()
    return route, end_time - start_time


def main():
    """Main benchmark execution function."""
    print("Starting TSP Solver Benchmark...")
    results = []

    for n_places in N_PLACES_TO_TEST:
        print(f"\n--- Testing with {n_places} places ---")
        for trial in range(1, NUM_TRIALS + 1):
            print(f"  Trial {trial}/{NUM_TRIALS}...")
            
            # 1. Generate data
            places = generate_random_places(n_places)
            distance_matrix = calculate_distance_matrix(places)

            # 2. Benchmark Dynamic Programming with Timeout
            if n_places >= 30:
                # For n >= 30, DP is computationally infeasible and guaranteed to time out.
                # We skip running it to save time and log it as a timeout directly.
                dp_route, dp_time = None, DP_TIMEOUT_SECONDS
            else:
                dp_route, dp_time = run_dp_with_timeout(distance_matrix, DP_TIMEOUT_SECONDS)

            dp_distance = float('inf')
            if dp_route:
                dp_distance = calculate_total_distance(dp_route, distance_matrix)
            
            results.append({
                'n_places': n_places,
                'trial': trial,
                'algorithm': 'Dynamic Programming',
                'execution_time_s': dp_time,
                'total_distance_m': dp_distance,
                'timed_out': dp_route is None
            })
            status = "Timed Out" if dp_route is None else f"Found path of {dp_distance}m"
            print(f"    - DP: {dp_time:.4f}s. Status: {status}")

            # 3. Benchmark Google OR-Tools
            or_start_time = time.perf_counter()
            or_route = solve_tsp_or_tools(distance_matrix, time_limit_seconds=int(OR_TOOLS_TIMEOUT_SECONDS))
            or_time = time.perf_counter() - or_start_time
            
            or_distance = float('inf')
            if or_route:
                or_distance = calculate_total_distance(or_route, distance_matrix)

            results.append({
                'n_places': n_places,
                'trial': trial,
                'algorithm': 'Google OR-Tools',
                'execution_time_s': or_time,
                'total_distance_m': or_distance,
                'timed_out': or_route is None
            })
            status = "Failed" if or_route is None else f"Found path of {or_distance}m"
            print(f"    - OR-Tools: {or_time:.4f}s. Status: {status}")

    # 4. Save results to CSV
    df = pd.DataFrame(results)
    try:
        df.to_csv(OUTPUT_CSV, index=False)
        print(f"\n[+] Benchmark complete. Results saved to '{OUTPUT_CSV}'")
    except Exception as e:
        print(f"\n[!] Error saving results to CSV: {e}")

if __name__ == "__main__":
    # Ensure the output directory exists
    output_dir = os.path.dirname(OUTPUT_CSV)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    main() 