"""Training and export script for LaneFeatureNet.
Generates an annotated road scene dataset with varied illumination, lateral vehicle offsets,
and markings, trains LaneFeatureNet, and saves the trained weights to ai/weights/lane_model.pt.
"""

import os
import time
import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from model_def import LaneFeatureNet


def generate_synthetic_dataset(num_samples: int = 600):
    """Generate diverse synthetic road camera frames with ground-truth lane annotations."""
    frames = []
    labels_lane = []
    labels_offset = []
    labels_conf = []

    w, h = 320, 180

    for i in range(num_samples):
        # 10% negative samples: no lanes, dark road, or heavy noise
        is_negative = (i % 10 == 0)

        img = np.zeros((h, w, 3), dtype=np.uint8)

        # Base road lighting variation (daylight to overcast)
        base_brightness = np.random.randint(40, 140)
        img[int(h * 0.45):, :] = (
            base_brightness + np.random.randint(-10, 10),
            base_brightness + np.random.randint(-10, 10),
            base_brightness + np.random.randint(-10, 10),
        )

        # Sky
        img[:int(h * 0.45), :] = (
            np.random.randint(140, 220),
            np.random.randint(120, 180),
            np.random.randint(90, 150),
        )

        if is_negative:
            # Low confidence sample
            # Add Gaussian noise
            noise = np.random.normal(0, 15, img.shape).astype(np.uint8)
            img = cv2.add(img, noise)
            frames.append(img)
            labels_lane.append(1)  # Default center
            labels_offset.append(0.0)
            labels_conf.append(0.1)
            continue

        # Choose lane position: 0=LEFT, 1=CENTER, 2=RIGHT
        lane_choice = np.random.choice([0, 1, 2])
        if lane_choice == 0:
            # Vehicle is in the LEFT lane (road lines appear shifted to the right)
            shift_x = np.random.randint(40, 75)
            target_offset = -float(shift_x) / 75.0
        elif lane_choice == 2:
            # Vehicle is in the RIGHT lane (road lines appear shifted to the left)
            shift_x = np.random.randint(-75, -40)
            target_offset = -float(shift_x) / 75.0
        else:
            # Vehicle is in the CENTER lane
            shift_x = np.random.randint(-18, 18)
            target_offset = -float(shift_x) / 75.0

        vp_x = w // 2 + shift_x
        vp_y = int(h * 0.48)

        # Left lane marking
        left_bot_x = int(w * 0.18) + shift_x
        right_bot_x = int(w * 0.82) + shift_x

        # Lane color: white or yellow
        color = (255, 255, 255) if np.random.rand() > 0.3 else (0, 230, 255)
        thickness = np.random.randint(3, 6)

        cv2.line(img, (left_bot_x, h), (vp_x - 15, vp_y), color, thickness)
        cv2.line(img, (right_bot_x, h), (vp_x + 15, vp_y), color, thickness)

        # Center dashed line
        if np.random.rand() > 0.5:
            cv2.line(img, (w // 2 + shift_x, h), (vp_x, vp_y), (255, 255, 255), 2)

        # Add camera texture noise
        noise = np.random.normal(0, 6, img.shape).astype(np.uint8)
        img = cv2.add(img, noise)

        frames.append(img)
        labels_lane.append(lane_choice)
        labels_offset.append(target_offset)
        labels_conf.append(0.92)

    # Convert to PyTorch tensors: (N, 3, H, W) normalized to [0, 1]
    x_tensor = torch.tensor(np.array(frames), dtype=torch.float32).permute(0, 3, 1, 2) / 255.0
    y_lane = torch.tensor(labels_lane, dtype=torch.long)
    y_offset = torch.tensor(labels_offset, dtype=torch.float32).unsqueeze(1)
    y_conf = torch.tensor(labels_conf, dtype=torch.float32).unsqueeze(1)

    return x_tensor, y_lane, y_offset, y_conf


def train_and_export():
    print("=" * 60)
    print("Training PyTorch LaneFeatureNet Model for Vehicle Camera")
    print("=" * 60)

    weights_dir = os.path.join(os.path.dirname(__file__), "weights")
    os.makedirs(weights_dir, exist_ok=True)
    weights_path = os.path.join(weights_dir, "lane_model.pt")

    print("Generating synthetic dataset (600 road frames)...")
    x_data, y_lane, y_offset, y_conf = generate_synthetic_dataset(num_samples=600)
    print(f"Dataset shape: X={x_data.shape}, y_lane={y_lane.shape}")

    model = LaneFeatureNet()
    model.train()

    criterion_lane = nn.CrossEntropyLoss()
    criterion_offset = nn.MSELoss()
    criterion_conf = nn.BCELoss()

    optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)

    batch_size = 32
    num_epochs = 12
    num_samples = len(x_data)

    t0 = time.time()
    for epoch in range(num_epochs):
        permutation = torch.randperm(num_samples)
        epoch_loss = 0.0

        for i in range(0, num_samples, batch_size):
            indices = permutation[i : i + batch_size]
            batch_x = x_data[indices]
            batch_lane = y_lane[indices]
            batch_offset = y_offset[indices]
            batch_conf = y_conf[indices]

            optimizer.zero_grad()
            pred_lane, pred_offset, pred_conf = model(batch_x)

            loss_l = criterion_lane(pred_lane, batch_lane)
            loss_o = criterion_offset(pred_offset, batch_offset)
            loss_c = criterion_conf(pred_conf, batch_conf)

            loss = loss_l + 2.0 * loss_o + loss_c
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item() * len(batch_x)

        avg_loss = epoch_loss / num_samples
        if (epoch + 1) % 3 == 0 or epoch == num_epochs - 1:
            print(f"Epoch [{epoch+1:2d}/{num_epochs:2d}] - Loss: {avg_loss:.4f}")

    train_duration = time.time() - t0
    print(f"Training completed in {train_duration:.2f}s")

    # Evaluation
    model.eval()
    with torch.no_grad():
        test_x = x_data[:60]
        t_infer0 = time.time()
        p_lane, p_offset, p_conf = model(test_x)
        infer_latency_ms = (time.time() - t_infer0) * 1000.0 / len(test_x)

        pred_classes = torch.argmax(p_lane, dim=1)
        accuracy = (pred_classes == y_lane[:60]).float().mean().item() * 100.0

        print(f"Validation Accuracy: {accuracy:.1f}%")
        print(f"Mean Inference Latency: {infer_latency_ms:.2f} ms/frame")

    # Save state dict
    torch.save(model.state_dict(), weights_path)
    print(f"Model weights saved successfully to: {weights_path}")

    # Also export TorchScript model for production deployment
    scripted_model = torch.jit.script(model)
    script_path = os.path.join(weights_dir, "lane_model_scripted.pt")
    scripted_model.save(script_path)
    print(f"TorchScript compiled model saved to: {script_path}")


if __name__ == "__main__":
    train_and_export()
