# Add Exception Reports Column to APHIS Data
#
# This script enriches aphis_data_final.csv with an "Exception Report" boolean
# column indicating whether each research facility has filed at least one annual
# report containing an exception (Column E) entry.
#
# --- HOW TO USE ---
#
# 1. Go to https://aphis.my.site.com/PublicSearchTool/s/annual-reports
# 2. Check the "Has Exception" checkbox and click Search.
# 3. Export all results to CSV (use the "Export to CSV" button, paginating as needed,
#    or use the aphis_data_complier.py script to merge multiple export pages).
# 4. Save the exported file as "aphis_exceptions.csv" in this directory.
# 5. Run:  python add_exception_reports.py
#
# Output: static_data/us/aphis_data_final.csv is updated in place with the new
#         "Exception Report" column (True/False).

import pandas as pd
import os

EXCEPTIONS_FILE = 'aphis_exceptions.csv'
APHIS_FINAL_FILE = os.path.join(
    os.path.dirname(__file__), '..', 'static_data', 'us', 'aphis_data_final.csv'
)

def main():
    # --- Load the exceptions export ---
    if not os.path.exists(EXCEPTIONS_FILE):
        print(f"ERROR: '{EXCEPTIONS_FILE}' not found.")
        print("Please download the APHIS annual reports filtered by 'Has Exception' and save as 'aphis_exceptions.csv'.")
        return

    print(f"Loading exception reports from '{EXCEPTIONS_FILE}'...")
    exceptions_df = pd.read_csv(EXCEPTIONS_FILE, dtype=str)

    if 'Certificate Number' not in exceptions_df.columns:
        print("ERROR: 'Certificate Number' column not found in exceptions file.")
        print(f"Available columns: {list(exceptions_df.columns)}")
        return

    exception_certs = set(exceptions_df['Certificate Number'].dropna().str.strip())
    print(f"Found {len(exception_certs)} unique certificates with exception reports.")

    # --- Load the main APHIS data ---
    aphis_path = os.path.normpath(APHIS_FINAL_FILE)
    if not os.path.exists(aphis_path):
        print(f"ERROR: '{aphis_path}' not found.")
        return

    print(f"Loading APHIS data from '{aphis_path}'...")
    aphis_df = pd.read_csv(aphis_path, dtype=str)

    if 'Certificate Number' not in aphis_df.columns:
        print("ERROR: 'Certificate Number' column not found in APHIS data.")
        return

    # --- Add the Exception Report column ---
    aphis_df['Exception Report'] = aphis_df['Certificate Number'].str.strip().isin(exception_certs)

    matched = aphis_df['Exception Report'].sum()
    print(f"Matched {matched} facilities with exception reports out of {len(aphis_df)} total.")

    # --- Save in place ---
    aphis_df.to_csv(aphis_path, index=False)
    print(f"\nSUCCESS! Updated '{aphis_path}' with 'Exception Report' column.")

if __name__ == '__main__':
    main()
