"""Lane-Aware Intelligent Emergency Vehicle Alert System
PyTorch Neural Network Architecture for Real-Time Edge Lane Detection.

Model: LaneFeatureNet
---------------------
A lightweight, high-efficiency convolutional neural network designed for edge
automotive deployment on vehicle-mounted cameras.

Input:
    Tensor of shape (B, 3, 180, 320), normalized in [0, 1].

Outputs:
    1. lane_logits: (B, 3) classification logits for [LEFT, CENTER, RIGHT].
    2. offset_pred: (B, 1) normalized lateral displacement from lane center [-1.0 .. 1.0].
    3. conf_pred:   (B, 1) sigmoid confidence score for lane visibility [0.0 .. 1.0].
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class LaneFeatureNet(nn.Module):
    """Convolutional neural network for lane classification and geometry estimation."""

    def __init__(self) -> None:
        super().__init__()
        # Feature extraction backbone
        self.conv1 = nn.Conv2d(3, 16, kernel_size=3, stride=1, padding=1)
        self.bn1 = nn.BatchNorm2d(16)

        self.conv2 = nn.Conv2d(16, 32, kernel_size=3, stride=1, padding=1)
        self.bn2 = nn.BatchNorm2d(32)

        self.conv3 = nn.Conv2d(32, 64, kernel_size=3, stride=1, padding=1)
        self.bn3 = nn.BatchNorm2d(64)

        self.conv4 = nn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1)
        self.bn4 = nn.BatchNorm2d(128)

        self.pool = nn.MaxPool2d(2, 2)
        self.adaptive_pool = nn.AdaptiveAvgPool2d((4, 4))

        # Lane assignment head (3 classes: 0=LEFT, 1=CENTER, 2=RIGHT)
        self.fc_shared = nn.Linear(128 * 4 * 4, 64)
        self.dropout = nn.Dropout(0.2)

        self.head_lane = nn.Linear(64, 3)
        self.head_offset = nn.Linear(64, 1)
        self.head_conf = nn.Linear(64, 1)

    def forward(self, x: torch.Tensor):
        # x: (B, 3, 180, 320)
        x = self.pool(F.relu(self.bn1(self.conv1(x))))  # -> (16, 90, 160)
        x = self.pool(F.relu(self.bn2(self.conv2(x))))  # -> (32, 45, 80)
        x = self.pool(F.relu(self.bn3(self.conv3(x))))  # -> (64, 22, 40)
        x = self.pool(F.relu(self.bn4(self.conv4(x))))  # -> (128, 11, 20)

        feat = self.adaptive_pool(x)  # -> (128, 4, 4)
        feat = torch.flatten(feat, 1)

        feat_dense = F.relu(self.fc_shared(feat))
        feat_dense = self.dropout(feat_dense)

        lane_logits = self.head_lane(feat_dense)
        offset_pred = torch.tanh(self.head_offset(feat_dense))  # [-1, 1]
        conf_pred = torch.sigmoid(self.head_conf(feat_dense))   # [0, 1]

        return lane_logits, offset_pred, conf_pred
