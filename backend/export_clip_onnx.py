"""
Export CLIP ViT-L-14 visual encoder to ONNX format for runtime inference.

Usage:
    python -m backend.export_clip_onnx
    python -m backend.export_clip_onnx --fine-tuned   # export with fine-tuned weights

After export, the runtime (hash_matcher.py) uses ONNX instead of PyTorch.
PyTorch/open_clip are only needed for training and this export step.
"""

import argparse
import os
import sys

# Fix Windows cp1252 encoding issue with torch.onnx logs
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import torch
import open_clip

try:
    from backend.app.paths import DATA_DIR, ensure_dirs
    ensure_dirs()
except ImportError:
    from app.paths import DATA_DIR, ensure_dirs
    ensure_dirs()

ONNX_PATH = DATA_DIR / "clip_visual.onnx"
CHECKPOINT_PATH = DATA_DIR / "clip_yugioh.pth"


def export(use_fine_tuned: bool = False):
    device = "cpu"  # export on CPU for compatibility
    print("Loading CLIP ViT-L-14...")
    model, _, _ = open_clip.create_model_and_transforms(
        "ViT-L-14", pretrained="laion2b_s32b_b82k", device=device
    )

    if use_fine_tuned and CHECKPOINT_PATH.exists():
        ckpt = torch.load(str(CHECKPOINT_PATH), map_location=device, weights_only=False)
        model.visual.load_state_dict(ckpt["visual_state_dict"])
        print(f"Fine-tuned weights loaded (epoch {ckpt.get('epoch', '?')})")

    model.eval()

    # Dummy input: batch=1, 3 channels, 224x224
    dummy = torch.randn(1, 3, 224, 224, device=device)

    # Use legacy TorchScript exporter (dynamo has issues with this model)
    print("Exporting to ONNX...")
    torch.onnx.export(
        model.visual,
        dummy,
        str(ONNX_PATH),
        input_names=["image"],
        output_names=["embedding"],
        dynamic_axes={"image": {0: "batch"}, "embedding": {0: "batch"}},
        opset_version=14,
        dynamo=False,
    )

    # Verify
    import onnxruntime as ort
    import numpy as np

    session = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])

    # Use same input for both to compare accurately
    test_input = np.random.randn(1, 3, 224, 224).astype(np.float32)
    onnx_out = session.run(None, {"image": test_input})[0]

    with torch.no_grad():
        torch_out = model.visual(torch.from_numpy(test_input)).numpy()

    diff = np.abs(onnx_out - torch_out).max()
    print(f"ONNX exported to: {ONNX_PATH}")
    print(f"Size: {ONNX_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"Output shape: {onnx_out.shape}")
    print(f"Max difference vs PyTorch: {diff:.2e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fine-tuned", action="store_true", help="Use fine-tuned weights")
    args = parser.parse_args()
    export(use_fine_tuned=args.fine_tuned)
