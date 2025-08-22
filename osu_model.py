from PIL import Image
from pyautogui import moveTo, click
from torch import no_grad
from transformers import AutoImageProcessor, AutoModelForObjectDetection

img = Image.open("screenshot.png").convert("RGB")
processor = AutoImageProcessor.from_pretrained("facebook/detr-resnet-50")
model = AutoModelForObjectDetection.from_pretrained("facebook/detr-resnet-50", num_labels=2,
                                                    ignore_mismatched_sizes=True)
inputs = processor(images=img, return_tensors="pt").to(model.device)

with no_grad():
    outputs = model(**inputs)

results = processor.post_process_object_detection(outputs, threshold=0.8, target_sizes=[img.size[::-1]])[0]

for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
    x1, y1, x2, y2 = box.tolist()
    center = ((x1 + x2) / 2, (y1 + y2) / 2)
    print(f"检测到按钮 {label} 置信度 {score:.2f} 坐标 {center}")

    # 自动点击第一个置信度最高的按钮
    moveTo(center)
    click()
    break
