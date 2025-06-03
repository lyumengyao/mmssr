import json
import pandas as pd
import argparse
import os
from utils import *

def get_score_sty(caps2resultpath, df_qas):

    answer_column = "pred_response"

    # parse scores
    cap_ratings = []
    for cap, cap_res in caps2resultpath.items():
        if cap != 'style':
            cap_rating = pd.DataFrame([json.loads(line) for line in open(cap_res)]) if cap_res.endswith('.jsonl') else pd.read_json(cap_res) 
            cap_rating = cap_rating.set_index('idx', verify_integrity=True)
    
            cap_rating[answer_column] = cap_rating[answer_column].apply(lambda x: parse_score(x, int))
            cap_ratings.append(cap_rating[[answer_column]].rename(columns={answer_column: cap}))
    result_df = pd.concat(cap_ratings, axis=1, join='outer')

    # parse styles
    style_fpath = caps2resultpath['style']
    style = pd.DataFrame([json.loads(line) for line in open(style_fpath)]) if style_fpath.endswith('.jsonl') else pd.read_json(style_fpath) 
    style = style.set_index('idx', verify_integrity=True).rename(columns={answer_column: 'style'})
    style = style.join(df_qas['image_source'], validate="one_to_one")
    parsed_style = style.apply(parse_sty, axis=1)
    parsed_style = pd.DataFrame(parsed_style.tolist(), index=style.index)
    parsed_style.columns = [f'sty_{i+1}' for i in range(parsed_style.shape[1])]

    # ss
    ratings = result_df.join(parsed_style, validate="one_to_one")

    print(f"Loaded {len(ratings)} mmssr responses ...")
    return ratings

def select(df_sorted, num_select):
    # Melt the DataFrame
    melted_df = df_sorted[[col for col in df_sorted.columns if col.startswith("sty_")]].melt(ignore_index=False, var_name='style_idx', value_name='style').dropna(subset=['style']).reset_index()

    # Group by the values while maintaining order
    grouped = melted_df.groupby('style', group_keys=True)['idx'].apply(list)
    n_bin = len(grouped)
    assert n_bin > 0

    sorted_grouped = grouped.sort_values(key=lambda x: x.apply(len), ascending=True)

    num_select_bin = max(num_select // n_bin, 1)
    selected_indices = set()

    num_samples_debt = 0
    for value, indices_list in sorted_grouped.items():
        if len(selected_indices) >= num_select:
            break
        filtered_indices = [idx for idx in indices_list if idx not in selected_indices]
        current_num_samples = min(num_select_bin + num_samples_debt, len(filtered_indices))
        num_samples_debt = max(num_select_bin + num_samples_debt - len(filtered_indices), 0)
        selected_for_group = filtered_indices[:current_num_samples]
        selected_indices.update(selected_for_group)
    
    return selected_indices
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--question-file', type=str, required=True)
    parser.add_argument('--ss-folder', type=str, required=True)
    parser.add_argument('--ratio', type=float, required=True)
    parser.add_argument('--save-folder', type=str, default="./mmssr_selection")
    parser.add_argument('--selected-caps', type=str, required=True)
    parser.add_argument('--thr', type=int, default=0)

    args = parser.parse_args()

    thr = args.thr
    assert 0 <= thr <=5, "thr should be in [0,5)"
    suffix = '' if thr == 0 else f"-thr{thr}"

    qas = json.load(open(os.path.expanduser(args.question_file)))
    df_qas = pd.DataFrame(qas).set_index('idx')
    TOTAL_LEN = len(qas)

    assert args.ratio < 1
    selected_len = int(TOTAL_LEN * args.ratio)
    print(f"selecting {selected_len} samples for {args.selected_caps} ...")

    # parse cap scores
    score_sty_v = os.path.basename(args.ss_folder)
    caps2resultpath = collect_jsonl_files(args.ss_folder)
    precompute_file = f"{args.save_folder}/{score_sty_v}_parsed.csv"
    if os.path.exists(precompute_file):
        print(f"load precomputed ratings from {precompute_file}...")
        parsed_ratings = pd.read_csv(precompute_file)
        parsed_ratings.set_index('idx', inplace=True, verify_integrity=True)
    else:
        print(f"precompute file not found, parsing ratings...")
        parsed_ratings = get_score_sty(caps2resultpath, df_qas)
        parsed_ratings.to_csv(precompute_file)
    valid_cols = parsed_ratings.columns
    print(f"parsed columns: {valid_cols}")

    comb = args.selected_caps
    save_folder = os.path.join(args.save_folder, score_sty_v, comb)
    
    selected_caps = comb.split('_')
    if not all([cap in valid_cols for cap in selected_caps]):
        print(f"No valid scores for {set(selected_caps)-set(valid_cols)}")
    else:
        valid_candidates = parsed_ratings.copy()
        selected_idx = set()
        while len(selected_idx) < selected_len:
            every_cap_budget = max(int(selected_len - len(selected_idx)) // len(selected_caps), 1)
            drop_caps = []
            for cap_name in selected_caps:
                sorted_ratings = valid_candidates.sort_values(by=cap_name, ascending=False)
                every_cap_budget = min(every_cap_budget, selected_len-len(selected_idx))
                new_index_cap = select(sorted_ratings[sorted_ratings[cap_name] > thr], every_cap_budget)
                if len(new_index_cap) == 0:
                    drop_caps.append(cap_name)
                else:
                    valid_candidates = valid_candidates.drop(new_index_cap)
                    selected_idx = selected_idx.union(new_index_cap)
                if len(selected_idx) >= selected_len:
                    break
            selected_caps = list(set(selected_caps) - set(drop_caps))

        selected_data = [item for item in qas if item['idx'] in selected_idx]

        save_json(selected_data, os.path.join(save_folder, f"llavaov-si-img-{score_sty_v}{suffix}-mmssr{args.ratio*100:.0f}.json"))
            