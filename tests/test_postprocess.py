from copilot.domain.models import OcrBlock
from copilot.ocr.postprocess import (
    build_result,
    hamming_distance,
    merge_line_fragments,
    perceptual_hash,
)


def test_merge_line_fragments_joins_same_row():
    blocks = [
        OcrBlock(text="Por que voce", bbox=(10, 100, 120, 118)),
        OcrBlock(text="quer esta vaga?", bbox=(125, 102, 300, 119)),
        OcrBlock(text="Outra linha", bbox=(10, 160, 120, 178)),
    ]
    merged = merge_line_fragments(blocks)
    assert len(merged) == 2
    assert merged[0].text == "Por que voce quer esta vaga?"


def test_build_result_filters_low_confidence():
    blocks = [
        OcrBlock(text="ruido", bbox=(0, 0, 10, 10), confidence=0.2),
        OcrBlock(text="Pergunta valida?", bbox=(0, 40, 100, 55), confidence=0.9),
    ]
    result = build_result(blocks, min_confidence=0.4)
    assert result.full_text == "Pergunta valida?"


def test_perceptual_hash_detects_similarity():
    import io

    from PIL import Image

    def png_of(color):
        buffer = io.BytesIO()
        Image.new("RGB", (100, 100), color).save(buffer, format="PNG")
        return buffer.getvalue()

    white = perceptual_hash(png_of((255, 255, 255)))
    white2 = perceptual_hash(png_of((250, 250, 250)))
    assert hamming_distance(white, white2) <= 2

    half = Image.new("RGB", (100, 100), (255, 255, 255))
    for x in range(50):
        for y in range(100):
            half.putpixel((x, y), (0, 0, 0))
    buffer = io.BytesIO()
    half.save(buffer, format="PNG")
    assert hamming_distance(white, perceptual_hash(buffer.getvalue())) > 10
