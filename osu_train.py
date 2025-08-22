from os import getcwd

from datasets import load_dataset
from torch import stack
from transformers import AutoImageProcessor, AutoModelForObjectDetection, TrainingArguments, Trainer


def transform(example):
    inputs = processor(images=example["image"], annotations=example["annotations"], return_tensors="pt")
    example["pixel_values"] = inputs["pixel_values"][0]
    example["labels"] = {k: v[0] for k, v in inputs["labels"].items()}
    return example


def collate(batch):
    return {
        "pixel_values": stack([b["pixel_values"] for b in batch]),
        "labels": [b["labels"] for b in batch]
    }


def start_train():
    dataset = load_dataset("coco", data_dir="data", split={"train": "train", "val": "validation"})
    datasets = {key: value.with_transform(transform) for key, value in dataset.items()}
    model = AutoModelForObjectDetection.from_pretrained("facebook/detr-resnet-50", num_labels=2,
                                                        ignore_mismatched_sizes=True)
    args = TrainingArguments(output_dir=f"{getcwd()}/osu_model", num_train_epochs=8, per_device_train_batch_size=2,
                             per_device_eval_batch_size=2, learning_rate=1e-4, save_strategy="epoch", fp16=True,
                             report_to="none")
    trainer = Trainer(model=model, args=args, train_dataset=datasets["train"], eval_dataset=datasets["val"],
                      data_collator=collate)
    trainer.train()
    trainer.save_model(f"{getcwd()}/model/finals")


if __name__ == "__main__":
    processor = AutoImageProcessor.from_pretrained("facebook/detr-resnet-50")
    start_train()
