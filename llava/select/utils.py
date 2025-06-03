import pandas as pd
import numpy as np
import os, json
import glob

def human_readable_number(n):
    if n >= 1000:
        return f"{n // 1000}k"
    return str(n)

def parse_score(x, t):
    try:
        return t(x)
    except:
        print(f"Wrong score ```{x}```")
        return np.NaN

def parse_sty(row):
    stys = []
    for sty in row['style'].split(','):
        sty = f"{sty.strip()}+{row['image_source']}"
        if sty not in stys:
            stys.append(sty)
    return list(stys)

def save_json(data, output_path):
    if isinstance(data, pd.DataFrame):
        data_json = data.to_dict(orient='records')
    else:
        data_json = data
    print(f"Saving {len(data_json)} items to {output_path} ...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data_json, f, indent=2, ensure_ascii=False)


def collect_jsonl_files(folder_path, ext='jsonl'):
    result = {}
    for filepath in glob.glob(os.path.join(folder_path, f'*.{ext}')):
        filename = os.path.basename(filepath)
        base, _ = os.path.splitext(filename)
        result[base] = filepath
    return result
