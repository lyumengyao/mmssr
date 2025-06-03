import argparse
import torch
import os
import json
from tqdm import tqdm
import copy

from llava.constants import IMAGE_TOKEN_INDEX, DEFAULT_IMAGE_TOKEN, DEFAULT_IM_START_TOKEN, DEFAULT_IM_END_TOKEN
from llava.conversation import conv_templates, SeparatorStyle
from llava.model.builder import load_pretrained_model
from llava.utils import disable_torch_init
from llava.mm_utils import tokenizer_image_token, get_model_name_from_path, KeywordsStoppingCriteria

from llava.constants import IGNORE_INDEX, DEFAULT_IMAGE_TOKEN, DEFAULT_IM_START_TOKEN, DEFAULT_IM_END_TOKEN, IMAGE_TOKEN_INDEX
from typing import Dict, Optional, Sequence, List
import transformers
import re

from PIL import Image

from config.ss import style_instruct, style_query, cap_instruct, cap_query, seps

def format_convs(convs):
    
    preprocessed_item = []
    for idx in range(len(convs)):
        conv = convs[idx]['value']
        if idx % 2 != 0:
            continue
        preprocessed_item.append(
            (
                conv if (conv.startswith('<image>\nHint:') or conv.startswith('Hint:')) 
                    else f"Question: {conv.strip('Question: ')}") + \
                seps[0] + \
                f"Answer: "
            )
        if idx != len(convs) - 1:
            preprocessed_item[-1] += f"{convs[idx+1]['value']}"
    return seps[1].join(preprocessed_item)


def preprocess_qwen(sources, tokenizer: transformers.PreTrainedTokenizer, has_image: bool = False, system_message: str = "You are a helpful assistant.") -> Dict:
    roles = {"human": "<|im_start|>user", "gpt": "<|im_start|>assistant"}

    im_start, im_end = tokenizer.additional_special_tokens_ids
    nl_tokens = tokenizer("\n").input_ids
    _system = tokenizer("system").input_ids + nl_tokens

    # Apply prompt templates
    input_ids, targets = [], []

    source = sources
    if roles[source[0]["from"]] != roles["human"]:
        source = source[1:]

    input_id, target = [], []
    system = [im_start] + _system + tokenizer(system_message).input_ids + [im_end] + nl_tokens
    input_id += system
    target += [im_start] + [IGNORE_INDEX] * (len(system) - 3) + [im_end] + nl_tokens
    assert len(input_id) == len(target)
    for j, sentence in enumerate(source):
        role = roles[sentence["from"]]
        if has_image and sentence["value"] is not None and "<image>" in sentence["value"]:
            num_image = len(re.findall(DEFAULT_IMAGE_TOKEN, sentence["value"]))
            texts = sentence["value"].split('<image>')
            _input_id = tokenizer(role).input_ids + nl_tokens 
            for i,text in enumerate(texts):
                _input_id += tokenizer(text).input_ids 
                if i<len(texts)-1:
                    _input_id += [IMAGE_TOKEN_INDEX] + nl_tokens
            _input_id += [im_end] + nl_tokens
            assert sum([i==IMAGE_TOKEN_INDEX for i in _input_id])==num_image
        else:
            if sentence["value"] is None:
                _input_id = tokenizer(role).input_ids + nl_tokens
            else:
                _input_id = tokenizer(role).input_ids + nl_tokens + tokenizer(sentence["value"]).input_ids + [im_end] + nl_tokens
        input_id += _input_id
        if role == "<|im_start|>user":
            _target = [im_start] + [IGNORE_INDEX] * (len(_input_id) - 3) + [im_end] + nl_tokens
        elif role == "<|im_start|>assistant":
            _target = [im_start] + [IGNORE_INDEX] * len(tokenizer(role).input_ids) + _input_id[len(tokenizer(role).input_ids) + 1 : -2] + [im_end] + nl_tokens
        else:
            raise NotImplementedError
        target += _target

    input_ids.append(input_id)
    targets.append(target)
    input_ids = torch.tensor(input_ids, dtype=torch.long)
    targets = torch.tensor(targets, dtype=torch.long)
    return input_ids

def get_last_processed_index(file_path):
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            if lines[-1].strip():
                return len(lines) - 1
            else:
                return len(lines) - 2
    except IndexError:
        return -1
    except FileNotFoundError:
        return -1

def eval_model(args):
    
    # Model
    disable_torch_init()
    model_path = os.path.expanduser(args.model_path)
    model_name = get_model_name_from_path(model_path)
    tokenizer, model, image_processor, context_len = load_pretrained_model(model_path, args.model_base, model_name)

    # Data
    with open(os.path.expanduser(args.question_file)) as f:
        questions = json.load(f)
    answers_file = os.path.expanduser(args.answers_file)
    os.makedirs(os.path.dirname(answers_file), exist_ok=True)
    ans_file = open(answers_file, "a")
    start_index = get_last_processed_index(answers_file) + 1
    print(f"{start_index}/{len(questions)} data have been processed for {args.question_file}")
    if start_index == len(questions):
        print(f'Data in {args.answers_file} is completed, exiting...')
        return
    else:
        questions = questions[start_index:]
    

    # prepare task
    if args.keyword == 'style':
        query = style_query
        instruct = style_instruct
    else:
        query = cap_query.replace('{cap_keyword}', args.keyword)
        instruct = cap_instruct

    system_message = "You are a helpful assistant."
    if args.instruct_sys:
        system_message = instruct
        instruct = ""

    if instruct:
        instruct += seps[1]
        
    for line in tqdm(questions, initial=start_index, total=len(questions)):

        image_file = line["image"]
        qs = instruct + format_convs(line["conversations"]) + seps[1] + query
        line["conversations"] = [{"value": qs, "from": line["conversations"][0]["from"]}]

        args.conv_mode = "qwen_1_5"

        conv = conv_templates[args.conv_mode].copy()
        conv.append_message(conv.roles[0], qs)
        conv.append_message(conv.roles[1], None)

        input_ids = preprocess_qwen(
            [line["conversations"][0], {'from': 'gpt','value': None}], 
            tokenizer,
            has_image=True,
            system_message=system_message).cuda()

        image = Image.open(os.path.join(args.image_folder, image_file))
        image_tensor = image_processor.preprocess(image, return_tensors='pt')['pixel_values']
        image_tensors = image_tensor.half().cuda().unsqueeze(0)

        stop_str = conv.sep if conv.sep_style != SeparatorStyle.TWO else conv.sep2

        with torch.inference_mode():
            output_ids = model.generate(
                input_ids,
                images=image_tensors,
                do_sample=True if args.temperature > 0 else False,
                temperature=args.temperature,
                top_p=args.top_p,
                num_beams=args.num_beams,
                # no_repeat_ngram_size=3,
                max_new_tokens=1024,
                use_cache=True)

        
        outputs = tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0]
        outputs = outputs.strip()
        if outputs.endswith(stop_str):
            outputs = outputs[:-len(stop_str)]
        outputs = outputs.strip()

        # ans_id = shortuuid.uuid()
        ans = {
                    "idx": line["idx"],
                    "pred_response": outputs,
                    # "model_id": model_name,
                    # "shortuuid": ans_id,
                    }
        ans_file.write(json.dumps(ans) + "\n")
        ans_file.flush()

    ans_file.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=str, default="facebook/opt-350m")
    parser.add_argument("--model-base", type=str, default=None)
    parser.add_argument("--keyword", type=str, required=True)
    parser.add_argument("--image-folder", type=str, default="")
    parser.add_argument("--extra-prompt", type=str, default="")
    parser.add_argument("--question-file", type=str, default="tables/question.json")
    parser.add_argument("--answers-file", type=str, default="answer.jsonl")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top_p", type=float, default=None)
    parser.add_argument("--num_beams", type=int, default=1)
    parser.add_argument("--test_size", type=int, default=10000000)
    parser.add_argument("--instruct-sys", action="store_true")
    args = parser.parse_args()

    eval_model(args)