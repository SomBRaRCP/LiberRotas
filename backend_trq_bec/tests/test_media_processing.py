from __future__ import annotations

import hashlib
import io

import pytest
from PIL import Image, features

from trq_bec.server.media_processing import (
    MediaProcessingError,
    process_image,
)


def image_bytes(
    image_format: str,
    *,
    size: tuple[int, int] = (40, 20),
    mode: str = "RGB",
    color=(10, 40, 90),
    **save_options,
) -> bytes:
    output = io.BytesIO()
    with Image.new(mode, size, color) as image:
        image.save(output, format=image_format, **save_options)
    return output.getvalue()


@pytest.mark.parametrize(
    ("image_format", "content_type"),
    [
        ("JPEG", "image/jpeg"),
        ("PNG", "image/png"),
        pytest.param(
            "WEBP",
            "image/webp",
            marks=pytest.mark.skipif(
                not features.check("webp"),
                reason="Pillow sem suporte a WebP",
            ),
        ),
    ],
)
def test_process_image_accepts_only_supported_decodable_images(
    image_format: str,
    content_type: str,
) -> None:
    result = process_image(image_bytes(image_format), content_type)

    assert result.content_type == content_type
    assert (result.width, result.height) == (40, 20)
    assert result.checksum_sha256 == hashlib.sha256(result.data).hexdigest()
    with Image.open(io.BytesIO(result.data)) as decoded:
        decoded.load()
        assert decoded.format == image_format
        assert decoded.size == (40, 20)


def test_process_image_rejects_mime_that_does_not_match_magic_bytes() -> None:
    with pytest.raises(MediaProcessingError) as captured:
        process_image(image_bytes("PNG"), "image/jpeg")

    assert captured.value.code == "MEDIA_IMAGE_TYPE_MISMATCH"


@pytest.mark.parametrize(
    ("data", "content_type", "expected_code"),
    [
        (b"", "image/png", "MEDIA_IMAGE_EMPTY"),
        (b"<svg></svg>", "image/svg+xml", "MEDIA_IMAGE_TYPE_NOT_ALLOWED"),
        (b"<html></html>", "image/png", "MEDIA_IMAGE_MAGIC_INVALID"),
        (b"\x89PNG\r\n\x1a\nnot-a-real-image", "image/png", "MEDIA_IMAGE_INVALID"),
    ],
)
def test_process_image_rejects_empty_unsupported_or_invalid_content(
    data: bytes,
    content_type: str,
    expected_code: str,
) -> None:
    with pytest.raises(MediaProcessingError) as captured:
        process_image(data, content_type)

    assert captured.value.code == expected_code
    assert str(captured.value) == expected_code


def test_process_image_applies_exif_orientation_and_removes_metadata() -> None:
    exif = Image.Exif()
    exif[274] = 6  # Rotação de 90 graus no sentido horário.
    exif[315] = "Autor que nao deve permanecer"
    source = image_bytes("JPEG", size=(40, 20), exif=exif)

    result = process_image(source, "image/jpeg")

    assert (result.width, result.height) == (20, 40)
    with Image.open(io.BytesIO(result.data)) as decoded:
        decoded.load()
        assert len(decoded.getexif()) == 0
        assert "icc_profile" not in decoded.info
        assert "xmp" not in decoded.info


def test_process_image_resizes_proportionally() -> None:
    result = process_image(
        image_bytes("PNG", size=(800, 400)),
        "image/png",
        max_dimension=200,
    )

    assert (result.width, result.height) == (200, 100)


def test_process_image_generates_only_thumbnail_and_display_webp_variants() -> None:
    result = process_image(
        image_bytes("JPEG", size=(1600, 800)),
        "image/jpeg",
    )

    assert [variant.variant for variant in result.variants] == ["thumbnail", "display"]
    assert [(variant.width, variant.height) for variant in result.variants] == [
        (320, 160),
        (1024, 512),
    ]
    for variant in result.variants:
        assert variant.content_type == "image/webp"
        assert variant.checksum_sha256 == hashlib.sha256(variant.data).hexdigest()
        with Image.open(io.BytesIO(variant.data)) as decoded:
            decoded.load()
            assert decoded.format == "WEBP"


def test_process_image_enforces_pixel_limit_before_processing() -> None:
    with pytest.raises(MediaProcessingError) as captured:
        process_image(
            image_bytes("PNG", size=(101, 100)),
            "image/png",
            max_pixels=10_000,
        )

    assert captured.value.code == "MEDIA_IMAGE_PIXEL_LIMIT_EXCEEDED"


def test_process_image_rejects_invalid_limits() -> None:
    with pytest.raises(MediaProcessingError) as captured:
        process_image(image_bytes("PNG"), "image/png", max_dimension=0)

    assert captured.value.code == "MEDIA_IMAGE_CONFIG_INVALID"


def test_process_image_preserves_png_transparency() -> None:
    source = image_bytes(
        "PNG",
        mode="RGBA",
        color=(20, 40, 60, 37),
    )

    result = process_image(source, "image/png")

    with Image.open(io.BytesIO(result.data)) as decoded:
        decoded.load()
        assert decoded.mode == "RGBA"
        assert decoded.getpixel((0, 0))[3] == 37


@pytest.mark.skipif(
    not features.check("webp"),
    reason="Pillow sem suporte a WebP",
)
def test_process_image_preserves_webp_transparency() -> None:
    source = image_bytes(
        "WEBP",
        mode="RGBA",
        color=(20, 40, 60, 37),
        lossless=True,
    )

    result = process_image(source, "image/webp")

    with Image.open(io.BytesIO(result.data)) as decoded:
        decoded.load()
        assert decoded.mode == "RGBA"
        assert decoded.getpixel((0, 0))[3] == 37
