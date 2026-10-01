"""Fine-tune YOLO11n on the Ultralytics Construction-PPE dataset.

    python training/train_ppe.py            # downloads dataset automatically
    cp runs/ppe/weights/best.pt models/ppe.pt
"""
from ultralytics import YOLO

if __name__ == "__main__":
    model = YOLO("yolo11n.pt")
    model.train(data="construction-ppe.yaml", imgsz=416, epochs=15, batch=16, project="runs", name="ppe", exist_ok=True)
    print(model.val(split="test"))
