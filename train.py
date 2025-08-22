from os import getcwd
from re import sub

from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments


def tokenize(examples):
    tokenized = []
    for title, selftext in zip(examples["title"], examples["selftext"]):
        title = title if title else ""
        selftext = selftext if selftext else ""
        text = "<BOS> " + title + " <ANSWER> " + selftext + " <EOS>"
        text = sub(r"\[.*?\]", "", text).strip()
        text = sub(r"\s+", " ", text).strip()
        text = text.replace("\n", "").replace("\r", "")
        tokenized.append(text)
    tokens = tokenizer(tokenized, truncation=True, padding="max_length", max_length=1000, return_tensors=None)
    tokens["labels"] = tokens["input_ids"].copy()
    return tokens


def start_train():
    dataset = load_dataset("SocialGrep/one-million-reddit-jokes")
    datasets = dataset["train"].train_test_split(test_size=0.1, seed=42)
    train = datasets["train"]
    val = datasets["test"]
    model = AutoModelForCausalLM.from_pretrained("gpt2")
    model.resize_token_embeddings(len(tokenizer))
    train = train.map(tokenize, batched=True, remove_columns=train.column_names)
    train.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])
    val = val.map(tokenize, batched=True, remove_columns=val.column_names)
    val.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])
    args = TrainingArguments(output_dir=f"{getcwd()}/model/checkpoints", num_train_epochs=8,
                             per_device_train_batch_size=4, per_device_eval_batch_size=8, warmup_steps=500,
                             weight_decay=0.01, logging_dir=f"{getcwd()}/model/logs", logging_steps=10,
                             save_steps=1000, eval_steps=1000, save_total_limit=2, fp16=True,
                             gradient_accumulation_steps=2, save_strategy="steps", learning_rate=5e-5,
                             load_best_model_at_end=False)
    trainer = Trainer(model=model, args=args, train_dataset=train, eval_dataset=val, tokenizer=tokenizer)
    trainer.train()
    trainer.save_model(f"{getcwd()}/model/finals")
    tokenizer.save_pretrained(f"{getcwd()}/model/finals")


if __name__ == "__main__":
    tokenizer = AutoTokenizer.from_pretrained("gpt2")
    special = {
        "bos_token": "<BOS>",
        "eos_token": "<EOS>",
        "pad_token": "<PAD>",
        "additional_special_tokens": ["<SEARCH>", "<ANSWER>"]
    }
    tokenizer.add_special_tokens(special)
    start_train()
