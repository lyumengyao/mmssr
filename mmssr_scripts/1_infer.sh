#!/bin/bash

CHECKPOINT="/path/to/mmssr/model"
task_name="style"  # logical reasoning capability etc
question_file="/path/to/data/qas.json"
IMAGE_FOLDER="/path/to/data/images"
OUTPUT_FOLDER="/path/to/result/folder"

# you may split the candidate data into chunks to better utilize your GPUs
python3 -m llava.eval.model_ss \
        --model-path ${CHECKPOINT} \
        --keyword ${task_name} \
        --question-file ${question_file} \
        --image-folder ${IMAGE_FOLDER} \
        --answers-file ${OUTPUT_FOLDER}/${task_name}.jsonl \
        --temperature 0