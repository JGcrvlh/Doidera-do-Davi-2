from __future__ import annotations

import io

from copilot.domain.models import OcrBlock, OcrResult


def perceptual_hash(png: bytes, size: int = 8) -> str:
    """Average-hash 8x8: suficiente para detectar 'a tela quase nao mudou'."""
    from PIL import Image

    image = Image.open(io.BytesIO(png)).convert("L").resize((size, size))
    pixels = list(image.tobytes())
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= average else "0" for p in pixels)
    return f"{int(bits, 2):0{size * size // 4}x}"


def hamming_distance(hash_a: str, hash_b: str) -> int:
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def merge_line_fragments(blocks: list[OcrBlock], y_tolerance: float = 8.0) -> list[OcrBlock]:
    """OCR costuma quebrar uma linha visual em varios fragmentos. Junta blocos
    na mesma faixa vertical, em ordem de leitura."""
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0]))
    merged: list[OcrBlock] = []
    current = ordered[0]
    for block in ordered[1:]:
        same_line = abs(block.bbox[1] - current.bbox[1]) <= y_tolerance
        if same_line:
            current = OcrBlock(
                text=f"{current.text} {block.text}".strip(),
                bbox=(
                    min(current.bbox[0], block.bbox[0]),
                    min(current.bbox[1], block.bbox[1]),
                    max(current.bbox[2], block.bbox[2]),
                    max(current.bbox[3], block.bbox[3]),
                ),
                confidence=min(current.confidence, block.confidence),
            )
        else:
            merged.append(current)
            current = block
    merged.append(current)
    return merged


def build_result(
    blocks: list[OcrBlock],
    *,
    min_confidence: float,
    image_hash: str | None = None,
    window_title: str | None = None,
) -> OcrResult:
    kept = [b for b in blocks if b.confidence >= min_confidence and b.text.strip()]
    merged = merge_line_fragments(kept)
    return OcrResult(
        blocks=merged,
        full_text="\n".join(b.text for b in merged),
        image_hash=image_hash,
        window_title=window_title,
    )
