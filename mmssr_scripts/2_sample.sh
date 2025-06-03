#!/bin/bash

question_file="/path/to/data/qas.json"
OUTPUT_FOLDER="/path/to/result/folder"
SAVE_FOLDER="/path/to/mmssr_selection/folder"

ratio=$1

caps="spatial_attribute_logical_..."
python3 llava/select/mmssr.py \
    --question-file $question_file \
    --ss-folder $OUTPUT_FOLDER \
    --ratio $ratio \
    --save-folder $SAVE_FOLDER \
    --selected_caps $caps