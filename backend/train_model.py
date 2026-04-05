"""
Fine-tune MobileNetV2 on Yu-Gi-Oh artwork for card recognition.

Usage:
    python -m backend.train_model                # train and export ONNX
    python -m backend.train_model --epochs 10    # custom epoch count
    python -m backend.train_model --export-only  # export existing checkpoint to ONNX

Each card_id is a class. The model learns to distinguish artworks from each other,
making the feature layer (1280-dim) specific to Yu-Gi-Oh card recognition.
After training, the feature model is exported to ONNX and embeddings are rebuilt.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import models
from PIL import Image

# Import centralized paths
try:
    from backend.app.paths import FULL_IMAGES_DIR, IMAGES_DIR, CARDS_JSON, DATA_DIR, HASH_DB, ensure_dirs
    ensure_dirs()
except ImportError:
    from app.paths import FULL_IMAGES_DIR, IMAGES_DIR, CARDS_JSON, DATA_DIR, HASH_DB, ensure_dirs
    ensure_dirs()

# Must match build_index.py / hash_matcher.py
WARP_W = 590
WARP_H = 860
ARTWORK_REGION = {"x": 0.13, "y": 0.18, "w": 0.74, "h": 0.47}

CHECKPOINT_PATH = DATA_DIR / "mobilenetv2_yugioh.pth"
ONNX_FEATURES_PATH = DATA_DIR / "mobilenetv2_features.onnx"


def _extract_artwork_from_full(img_cv: np.ndarray) -> np.ndarray:
    warped = cv2.resize(img_cv, (WARP_W, WARP_H))
    h, w = warped.shape[:2]
    x1 = int(w * ARTWORK_REGION["x"])
    y1 = int(h * ARTWORK_REGION["y"])
    x2 = int(w * (ARTWORK_REGION["x"] + ARTWORK_REGION["w"]))
    y2 = int(h * (ARTWORK_REGION["y"] + ARTWORK_REGION["h"]))
    return warped[y1:y2, x1:x2]


class ArtworkDataset(Dataset):
    """Dataset with all artwork pre-loaded as tensors in RAM."""

    def __init__(self, cards: list[dict], card_id_to_idx: dict):
        self.tensors = []  # normalized float32 tensors
        self.labels = []

        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)

        print("  Pre-loading artwork into RAM as tensors...")
        loaded = 0
        for card in cards:
            card_id = card["id"]
            if card_id not in card_id_to_idx:
                continue
            img_path = FULL_IMAGES_DIR / f"{card_id}.jpg"
            if not img_path.exists():
                continue

            img_cv = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if img_cv is None:
                continue
            artwork_cv = _extract_artwork_from_full(img_cv)
            artwork_cv = cv2.resize(artwork_cv, (224, 224))
            artwork_rgb = cv2.cvtColor(artwork_cv, cv2.COLOR_BGR2RGB)

            # Convert to tensor and normalize
            t = torch.from_numpy(artwork_rgb).permute(2, 0, 1).float() / 255.0
            t = (t - mean) / std
            self.tensors.append(t)
            self.labels.append(card_id_to_idx[card_id])
            loaded += 1
            if loaded % 2000 == 0:
                print(f"    [{loaded}] loaded...")

        # Stack into single tensors for fast indexing
        self.tensors = torch.stack(self.tensors)
        self.labels = torch.tensor(self.labels, dtype=torch.long)
        print(f"  {loaded} artwork loaded ({self.tensors.shape})")

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return self.tensors[idx], self.labels[idx]


EMBEDDING_DIM = 256


def build_model(num_classes: int) -> nn.Module:
    """MobileNetV2 with embedding projection + classification head.

    Architecture: features(1280) -> projection(256, L2-norm) -> classifier(num_classes)
    The 256-dim embedding is what we use for matching at runtime.
    """
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)

    # Freeze only the first few layers, fine-tune the rest
    for param in model.features[:7].parameters():
        param.requires_grad = False

    # Replace classifier with embedding projection + classification
    model.classifier = nn.Sequential(
        nn.Dropout(0.2),
        nn.Linear(1280, EMBEDDING_DIM),
        nn.BatchNorm1d(EMBEDDING_DIM),
    )

    # Separate classification head on top of the embedding
    model.cls_head = nn.Linear(EMBEDDING_DIM, num_classes)

    # Override forward
    original_forward = model.forward

    def new_forward(x):
        x = model.features(x)
        x = nn.functional.adaptive_avg_pool2d(x, (1, 1))
        x = torch.flatten(x, 1)
        embedding = model.classifier(x)
        embedding = nn.functional.normalize(embedding, p=2, dim=1)  # L2 normalize
        logits = model.cls_head(embedding)
        return logits, embedding

    model.forward = new_forward
    return model


def train(epochs: int = 5, batch_size: int = 64, lr: float = 1e-3, resume: bool = False):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    if not CARDS_JSON.exists():
        print("No card data found. Run build_index first.")
        return

    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))

    # Build class mapping: card_id -> sequential index
    card_ids = []
    for card in cards:
        img_path = FULL_IMAGES_DIR / f"{card['id']}.jpg"
        if img_path.exists():
            card_ids.append(card["id"])

    card_id_to_idx = {cid: i for i, cid in enumerate(card_ids)}
    num_classes = len(card_ids)
    print(f"Classes (unique cards): {num_classes}")

    dataset = ArtworkDataset(cards, card_id_to_idx)
    print(f"Dataset size: {len(dataset)}")

    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        pin_memory=True,
    )

    model = build_model(num_classes).to(device)
    criterion = nn.CrossEntropyLoss()

    start_epoch = 0

    # Resume from checkpoint
    if resume and CHECKPOINT_PATH.exists():
        print(f"Resuming from checkpoint: {CHECKPOINT_PATH}")
        checkpoint = torch.load(str(CHECKPOINT_PATH), map_location=device, weights_only=False)
        if checkpoint.get("num_classes") == num_classes:
            model.load_state_dict(checkpoint["model_state_dict"])
            start_epoch = checkpoint.get("epoch", 0)
            print(f"  Resumed from epoch {start_epoch}")
        else:
            print(f"  WARNING: class count changed ({checkpoint.get('num_classes')} -> {num_classes}), training from scratch")

    # Only optimize unfrozen params
    optimizer = torch.optim.Adam(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=lr,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    # Training loop
    model.train()
    for epoch in range(start_epoch, start_epoch + epochs):
        t0 = time.time()
        running_loss = 0.0
        correct = 0
        total = 0

        for batch_idx, (images, labels) in enumerate(loader):
            images, labels = images.to(device), labels.to(device)

            # Augmentation on GPU: simulates foil, lighting, camera conditions
            with torch.no_grad():
                B = images.size(0)

                # 1) Brightness & contrast (lighting variation)
                brightness = 1.0 + (torch.rand(B, 1, 1, 1, device=device) - 0.5) * 1.0
                contrast = 1.0 + (torch.rand(B, 1, 1, 1, device=device) - 0.5) * 1.0
                images = (images - images.mean(dim=(2, 3), keepdim=True)) * contrast + images.mean(dim=(2, 3), keepdim=True)
                images = images * brightness

                # 2) Hue shift (foil cards change color drastically)
                # Rotate RGB channels partially: mix channels with random weights
                hue_mask = torch.rand(B, device=device) < 0.5  # 50% of batch
                if hue_mask.any():
                    shift = torch.randint(1, 3, (hue_mask.sum().item(),), device=device)
                    for i, s in zip(hue_mask.nonzero(as_tuple=True)[0], shift):
                        images[i] = images[i].roll(s.item(), dims=0)  # roll RGB channels

                # 3) Partial glare/reflection (foil highlight)
                glare_mask = torch.rand(B, device=device) < 0.3  # 30% of batch
                if glare_mask.any():
                    n_glare = glare_mask.sum().item()
                    # Random rectangular glare region
                    gy = torch.randint(0, 160, (n_glare,), device=device)
                    gx = torch.randint(0, 160, (n_glare,), device=device)
                    gh = torch.randint(30, 80, (n_glare,), device=device)
                    gw = torch.randint(30, 80, (n_glare,), device=device)
                    for idx, i in enumerate(glare_mask.nonzero(as_tuple=True)[0]):
                        y1, x1 = gy[idx].item(), gx[idx].item()
                        y2 = min(y1 + gh[idx].item(), 224)
                        x2 = min(x1 + gw[idx].item(), 224)
                        glare_strength = torch.rand(1, device=device).item() * 2.0 + 0.5
                        images[i, :, y1:y2, x1:x2] *= glare_strength

                # 4) Saturation jitter (foil changes color intensity)
                sat_factor = 1.0 + (torch.rand(B, 1, 1, 1, device=device) - 0.5) * 1.5
                gray = images.mean(dim=1, keepdim=True)
                images = gray + sat_factor * (images - gray)

                # 5) Gaussian noise (camera sensor noise)
                noise = torch.randn_like(images) * 0.08
                images = images + noise

                # 6) Random crop offset (simulates imperfect card positioning)
                crop_mask = torch.rand(B, device=device) < 0.4
                if crop_mask.any():
                    for i in crop_mask.nonzero(as_tuple=True)[0]:
                        dx = torch.randint(-30, 31, (1,)).item()
                        dy = torch.randint(-30, 31, (1,)).item()
                        images[i] = torch.roll(images[i], shifts=(dy, dx), dims=(1, 2))

                # 7) Random occlusion (shadows, fingers, objects covering part of artwork)
                occ_mask = torch.rand(B, device=device) < 0.25
                if occ_mask.any():
                    for i in occ_mask.nonzero(as_tuple=True)[0]:
                        # Random dark rectangle (shadow)
                        oy = torch.randint(0, 180, (1,)).item()
                        ox = torch.randint(0, 180, (1,)).item()
                        oh = torch.randint(20, 70, (1,)).item()
                        ow = torch.randint(20, 70, (1,)).item()
                        y2 = min(oy + oh, 224)
                        x2 = min(ox + ow, 224)
                        darkness = torch.rand(1, device=device).item() * 0.5
                        images[i, :, oy:y2, ox:x2] *= darkness

                # 8) Random zoom crop (simulates partial card visibility)
                zoom_mask = torch.rand(B, device=device) < 0.2
                if zoom_mask.any():
                    for i in zoom_mask.nonzero(as_tuple=True)[0]:
                        # Crop 60-90% of the image and resize back
                        scale = 0.6 + torch.rand(1, device=device).item() * 0.3
                        crop_size = int(224 * scale)
                        cy = torch.randint(0, 224 - crop_size + 1, (1,)).item()
                        cx = torch.randint(0, 224 - crop_size + 1, (1,)).item()
                        cropped = images[i, :, cy:cy+crop_size, cx:cx+crop_size].unsqueeze(0)
                        images[i] = torch.nn.functional.interpolate(cropped, size=(224, 224), mode='bilinear', align_corners=False).squeeze(0)

                images = images.clamp(-3, 3)

            optimizer.zero_grad()
            logits, embedding = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item()
            _, predicted = logits.max(1)
            total += labels.size(0)
            correct += predicted.eq(labels).sum().item()

            if (batch_idx + 1) % 50 == 0:
                print(f"  [{batch_idx + 1}/{len(loader)}] loss: {loss.item():.4f}")

        scheduler.step()
        elapsed = time.time() - t0
        acc = 100.0 * correct / total
        avg_loss = running_loss / len(loader)
        print(f"Epoch {epoch + 1}/{start_epoch + epochs} — loss: {avg_loss:.4f}, acc: {acc:.1f}%, time: {elapsed:.0f}s")

    # Save checkpoint
    final_epoch = start_epoch + epochs
    torch.save({
        "model_state_dict": model.state_dict(),
        "card_id_to_idx": card_id_to_idx,
        "num_classes": num_classes,
        "epoch": final_epoch,
    }, str(CHECKPOINT_PATH))
    print(f"\nCheckpoint saved: {CHECKPOINT_PATH} (epoch {final_epoch})")

    # Export to ONNX
    export_onnx(model, device)

    # Rebuild embeddings
    rebuild_embeddings(model, device, cards, card_id_to_idx)


def export_onnx(model=None, device=None):
    """Export the feature extraction part (before classifier) to ONNX."""
    if model is None:
        if not CHECKPOINT_PATH.exists():
            print("No checkpoint found. Train first.")
            return
        checkpoint = torch.load(str(CHECKPOINT_PATH), map_location="cpu", weights_only=False)
        model = build_model(checkpoint["num_classes"])
        model.load_state_dict(checkpoint["model_state_dict"])
        device = torch.device("cpu")

    model.eval()
    model.to(device)

    # Create embedding model (features + projection + L2 norm)
    class EmbeddingExtractor(nn.Module):
        def __init__(self, mobilenet):
            super().__init__()
            self.features = mobilenet.features
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.projection = mobilenet.classifier  # Linear(1280, 256) + BN

        def forward(self, x):
            x = self.features(x)
            x = self.pool(x)
            x = torch.flatten(x, 1)
            x = self.projection(x)
            x = nn.functional.normalize(x, p=2, dim=1)
            return x  # (batch, 256)

    feature_model = EmbeddingExtractor(model).to(device)
    feature_model.eval()

    dummy = torch.randn(1, 3, 224, 224).to(device)
    torch.onnx.export(
        feature_model,
        dummy,
        str(ONNX_FEATURES_PATH),
        input_names=["input"],
        output_names=["features"],
        dynamic_axes={"input": {0: "batch_size"}, "features": {0: "batch_size"}},
        opset_version=18,
        dynamo=False,
    )
    print(f"ONNX feature model exported: {ONNX_FEATURES_PATH}")
    print(f"  Size: {ONNX_FEATURES_PATH.stat().st_size / 1024 / 1024:.1f} MB")


def rebuild_embeddings(model, device, cards, card_id_to_idx):
    """Rebuild embedding index using the fine-tuned model."""
    import sqlite3
    import onnxruntime as ort

    print("\nRebuilding embeddings with fine-tuned model...")

    session = ort.InferenceSession(str(ONNX_FEATURES_PATH), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    conn = sqlite3.connect(str(HASH_DB))
    conn.execute("DROP TABLE IF EXISTS card_embeddings")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS card_embeddings (
            card_id     INTEGER PRIMARY KEY,
            embedding   BLOB NOT NULL
        )
    """)

    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    done = 0
    for card in cards:
        card_id = card["id"]
        img_path = FULL_IMAGES_DIR / f"{card_id}.jpg"
        if not img_path.exists():
            continue

        try:
            img_cv = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if img_cv is None:
                continue
            artwork_cv = _extract_artwork_from_full(img_cv)
            img = cv2.resize(artwork_cv, (224, 224))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            img = (img - mean) / std
            img = np.transpose(img, (2, 0, 1))
            input_tensor = np.expand_dims(img, axis=0)

            output = session.run(None, {input_name: input_tensor})[0]
            vec = output.flatten().astype(np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm

            conn.execute(
                "INSERT OR REPLACE INTO card_embeddings (card_id, embedding) VALUES (?, ?)",
                (card_id, vec.tobytes()),
            )
            done += 1
            if done % 1000 == 0:
                conn.commit()
                print(f"  [{done}] embedded...")
        except Exception as e:
            continue

    conn.commit()
    conn.close()
    print(f"Done! {done} embeddings rebuilt.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-tune MobileNetV2 on Yu-Gi-Oh artwork")
    parser.add_argument("--epochs", type=int, default=20, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=256, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    parser.add_argument("--resume", action="store_true", help="Resume training from last checkpoint")
    parser.add_argument("--export-only", action="store_true", help="Only export existing checkpoint to ONNX")
    args = parser.parse_args()

    try:
        if args.export_only:
            export_onnx()
        else:
            train(epochs=args.epochs, batch_size=args.batch_size, lr=args.lr, resume=args.resume)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
