from torch import bfloat16, no_grad
from torch.nn.functional import softmax
from transformers import AutoTokenizer, AutoModelForCausalLM

tokenizer = AutoTokenizer.from_pretrained("google/shieldgemma-2b")
model = AutoModelForCausalLM.from_pretrained("google/shieldgemma-2b", device_map="auto", torch_dtype=bfloat16)
policy = """
* "No Harassment": The prompt shall not contain or seek generation of content that is malicious, intimidating, bullying, or abusive content targeting another individual (e.g., physical threats, denial of tragic events, disparaging victims of violence).
"""


def result_filter(input: str) -> int:
    prompt = f"""You are a policy expert trying to help determine whether a user
    prompt is in violation of the defined safety policies.
    
    <start_of_turn>
    Human Question: {input.strip()}
    <end_of_turn>
    
    Our safety principle is defined in the below:
    
    {policy.strip()}
    
    Does the human question violate the above principle? Your answer must start
    with 'Yes' or 'No'. And then walk through step by step to be sure we answer
    correctly.
    """
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    with no_grad():
        logits = model(**inputs).logits
    vocab = tokenizer.get_vocab()
    selected_logits = logits[0, -1, [vocab['Yes'], vocab['No']]]
    probabilities = softmax(selected_logits, dim=0)
    score = probabilities[0].item()
    print(score)
    return score
