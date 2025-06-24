# Trip Optimization Benchmark

This directory contains scripts to benchmark and visualize the performance of the Traveling Salesperson Problem (TSP) solvers used in the trip optimization feature.

## Objective

The goal is to compare the **Dynamic Programming (DP)** approach with **Google's OR-Tools** based on two key metrics:
1.  **Execution Time:** How long each algorithm takes to find a solution.
2.  **Solution Quality:** The total distance of the optimized route.

## Scripts

### 1. `benchmark_tsp_solvers.py`

This is the main script for running the benchmark. It will:
- Generate random trip data (sets of coordinates) for various numbers of places (e.g., from 5 to 60).
- Run both DP and OR-Tools on each dataset.
- **Important:** The DP algorithm is run with a **3-second timeout** to prevent it from hanging on large inputs, as its complexity is exponential.
- Record the execution time and resulting route distance for each run.
- Save the aggregated results into a file named `benchmark_results.csv`.

**Usage:**
```bash
python trip_optimization_analysis/benchmark_tsp_solvers.py
```
*Note: This script may take several minutes to run, especially for larger numbers of places.*

### 2. `summarize_results.py`

After generating the raw data with the benchmark script, you can run this script to create a summary file. It will:
- Read the raw `benchmark_results.csv`.
- Calculate the average execution time and total distance for each algorithm and for each number of places tested.
- Count the number of timeouts for each case.
- Save the results to `benchmark_summary.csv`.

**Usage:**
```bash
python trip_optimization_analysis/summarize_results.py
```

### 3. `visualize_benchmark_results.py`

After the benchmark has been run and you have either the raw or summarized CSV, this script can be used to visualize the results. It will generate plots comparing the two algorithms.

**Setup:**
You may need to install the following libraries if you haven't already:
```bash
pip install pandas matplotlib seaborn
```

**Usage:**
```bash
python trip_optimization_analysis/visualize_benchmark_results.py
```
This will read the CSV file and save the comparison charts as PNG images in this directory. 