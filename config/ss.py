seps = [" ", "\n"]

style_instruct = ""

style_candidates = [
    "multi-choice", 
    "coordinate", 
    "yes/no", 
    "word/short-phrase", 
    "short description", 
    "detailed description", 
    "comparison", 
    "chain-of-thought (step-by-step)", 
    "specified style"
]
style_candidates = f"[{', '.join(style_candidates)}]"
style_query = "Interaction style candidates:" + seps[0] + style_candidates + seps[1] + "Styles: "

cap_instruct = ""
cap_query = "On a scale of 0 to 5, how do you rate the helpfulness of the VQA instance in training a Multimodal Large Language Model for {cap_keyword}?"