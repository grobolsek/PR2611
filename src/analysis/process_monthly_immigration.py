"""Automated monthly parser for GOV.SI issued immigration certificates.

Scans the directory for original filenames containing 'izdana' and a year,
extracts monthly values from the 'Izdana DP_mesečno' sheet, and compiles
a detailed long-format monthly CSV for correlation analysis.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Slovenian months mapped to the crime database numeric format (e.g., "01.2025")
SLO_MONTHS = {
    "JANUAR": "01", "FEBRUAR": "02", "MAREC": "03", "APRIL": "04",
    "MAJ": "05", "JUNIJ": "06", "JULIJ": "07", "AVGUST": "08",
    "SEPTEMBER": "09", "OKTOBER": "10", "NOVEMBER": "11", "DECEMBER": "12"
}

def extract_monthly_data(file_path: Path, year: int) -> pd.DataFrame:
    """Read the monthly sheet and extract structured data for each individual month."""
    try:
        excel_file = pd.ExcelFile(file_path)
        
        # Locate the specific worksheet containing monthly metrics
        target_sheet = next((s for s in excel_file.sheet_names if "MESEČNO" in s.upper() or "MESECNO" in s.upper()), None)
        
        if not target_sheet:
            logger.error(f"Could not find a monthly data sheet in file: {file_path.name}")
            return pd.DataFrame()
            
        # Load the spreadsheet data (header context starts at row index 5)
        df = pd.read_excel(file_path, sheet_name=target_sheet, skiprows=5)
        
        # Clean column identifiers for safe parsing
        df.columns = [str(c).strip() for c in df.columns]
        
        monthly_records = []
        
        for idx, row in df.iterrows():
            month_name = str(row.iloc[0]).strip().upper()
            
            # Break out or skip if the aggregation rows or empty spaces are hit
            if "SKUPAJ" in month_name or "TOTAL" in month_name or pd.isna(row.iloc[0]):
                continue
                
            if month_name in SLO_MONTHS:
                month_num = SLO_MONTHS[month_name]
                
                # Fetch group values from the primary total summation columns
                # Third-country nationals TOTAL (Column D) + EEA Nationals TOTAL (Column H)
                total_third_countries = row.iloc[3] if not pd.isna(row.iloc[3]) else 0
                total_eea = row.iloc[7] if not pd.isna(row.iloc[7]) else 0
                
                total_issued = int(total_third_countries) + int(total_eea)
                
                monthly_records.append({
                    "MesecStoritve": f"{month_num}.{year}",
                    "Izdana_Dovoljenja_Mesec": total_issued
                })
                
        return pd.DataFrame(monthly_records)

    except Exception as e:
        logger.error(f"Error parsing file elements for {file_path.name}: {e}")
        return pd.DataFrame()

def main() -> None:
    base_dir = Path(__file__).parents[2]
    imm_dir = base_dir / "data" / "immigration"
    
    # Retrieve all target Excel files inside the immigration directory
    all_files = list(imm_dir.glob("*.xlsx"))
    
    all_monthly_dfs = []
    
    for f in all_files:
        filename_lower = f.name.lower()
        
        # Rule 1: Filename must target permit issues containing 'izdana'
        if "izdana" not in filename_lower:
            continue
            
        # Rule 2: Attempt to dynamically isolate the context year (e.g., 2024, 2025)
        year_match = re.search(r"202\d", filename_lower)
        if not year_match:
            logger.warning(f"Detected permit file match, but missing a verifiable year format: {f.name}")
            continue
            
        year = int(year_match.group(0))
        logger.info(f"Processing target data file found for year {year}: {f.name}")
        
        df_month = extract_monthly_data(f, year)
        if not df_month.empty:
            all_monthly_dfs.append(df_month)
            
    if all_monthly_dfs:
        df_final = pd.concat(all_monthly_dfs, ignore_index=True)
        
        # Sort values chronologically to build a proper historical series
        df_final["_sort_date"] = pd.to_datetime(df_final["MesecStoritve"], format="%m.%Y")
        df_final = df_final.sort_values(by="_sort_date").drop(columns=["_sort_date"]).reset_index(drop=True)
        
        # Export paths execution
        out_file = imm_dir / "monthly_immigration_trends.csv"
        df_final.to_csv(out_file, index=False, encoding="utf-8")
        
        print(f"Monthly dataset saved to:\n{out_file}")
        print(df_final.head(12))  # Outputs first 12 monthly series for confirmation
    else:
        logger.error("No valid 'izdana' files containing identifiable years found inside the target directory.")

if __name__ == "__main__":
    main()