import pandas as pd
import pathlib

NA_VALLS = ["", "NI OZNAKE", "199-NI PREDMETA", "OSTALO"]

def format(input_file: pathlib.Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(
                input_file.absolute(), 
                sep=';', 
                encoding='latin1', 
                on_bad_lines='warn',
                engine='c', # fatser
                na_values=NA_VALLS
            )
        
        df = df.replace("BREZ", 0) # denaran škoda
        df = df.fillna(-1)

        return df
    
    except Exception as e:
        print(f"Error processing {input_file.name}: {e}")
        return pd.DataFrame()


def format_all() -> None:
    base_path = pathlib.Path(__file__).parent.parent.parent

    input_dir  = base_path / "data" / "raw"
    output_dir = base_path / "data" / "formated"
    
    input_dir .mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        print(f"{input_dir} not a dir!")
        return

    for file in input_dir.glob("*.csv"):
        df = format(file)
        save_path = output_dir / file.name
        df.to_csv(save_path, sep=';', index=False, quoting=1, encoding='utf-8')

        print(f"Processed: {file.name} -> {save_path}")

if __name__ == "__main__":
    format_all()