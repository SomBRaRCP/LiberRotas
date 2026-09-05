"""Validação e normalização segura das imagens enviadas ao LiberRotas."""

from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError


_MIME_TO_FORMAT = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_FORMAT_TO_MIME = {value: key for key, value in _MIME_TO_FORMAT.items()}


class MediaProcessingError(RuntimeError):
    """Erro de imagem com código estável, sem expor bytes ou detalhes internos."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    data: bytes
    content_type: str
    width: int
    height: int
    checksum_sha256: str
    variants: tuple["ProcessedImageVariant", ...] = ()


@dataclass(frozen=True, slots=True)
class ProcessedImageVariant:
    variant: str
    data: bytes
    content_type: str
    width: int
    height: int
    checksum_sha256: str


def _format_from_magic(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def _has_transparency(image: Image.Image) -> bool:
    return image.mode in {"LA", "RGBA", "RGBa", "PA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def _clean_mode(image: Image.Image, image_format: str) -> Image.Image:
    has_transparency = _has_transparency(image)

    if image_format == "JPEG":
        if image.mode in {"L", "RGB", "CMYK"}:
            clean = image.copy()
        else:
            clean = image.convert("RGB")
    elif has_transparency:
        clean = image.convert("RGBA")
    elif image_format == "WEBP":
        clean = image.convert("RGB")
    elif image.mode in {"1", "L", "P", "RGB", "I", "I;16"}:
        clean = image.copy()
    else:
        clean = image.convert("RGB")

    # O encoder não deve herdar EXIF, GPS, XMP, ICC ou outros metadados.
    clean.info.clear()
    return clean


def _open_and_verify(data: bytes, expected_format: str, max_pixels: int) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as candidate:
                detected_format = (candidate.format or "").upper()
                if detected_format != expected_format:
                    raise MediaProcessingError("MEDIA_IMAGE_TYPE_MISMATCH")
                width, height = candidate.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise MediaProcessingError("MEDIA_IMAGE_PIXEL_LIMIT_EXCEEDED")
                candidate.verify()

            # ``verify`` invalida o decoder; uma segunda abertura seguida de
            # ``load`` garante que o conteúdo completo é de fato decodificável.
            with Image.open(io.BytesIO(data)) as decoded:
                detected_format = (decoded.format or "").upper()
                if detected_format != expected_format:
                    raise MediaProcessingError("MEDIA_IMAGE_TYPE_MISMATCH")
                width, height = decoded.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise MediaProcessingError("MEDIA_IMAGE_PIXEL_LIMIT_EXCEEDED")
                decoded.load()
                return decoded.copy()
    except MediaProcessingError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise MediaProcessingError("MEDIA_IMAGE_PIXEL_LIMIT_EXCEEDED") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise MediaProcessingError("MEDIA_IMAGE_INVALID") from exc
    except Exception as exc:
        raise MediaProcessingError("MEDIA_IMAGE_INVALID") from exc


def _encode(image: Image.Image, image_format: str) -> bytes:
    output = io.BytesIO()
    try:
        if image_format == "JPEG":
            image.save(
                output,
                format="JPEG",
                quality=90,
                optimize=True,
                progressive=True,
            )
        elif image_format == "PNG":
            image.save(output, format="PNG", optimize=True, compress_level=9)
        else:
            image.save(output, format="WEBP", quality=90, method=6)
    except Exception as exc:
        raise MediaProcessingError("MEDIA_IMAGE_PROCESSING_FAILED") from exc
    return output.getvalue()


def _image_variants(image: Image.Image) -> tuple[ProcessedImageVariant, ...]:
    """Gera apenas os dois tamanhos usados nas listas e telas do aplicativo."""

    generated: list[ProcessedImageVariant] = []
    for variant, max_dimension, quality in (
        ("thumbnail", 320, 78),
        ("display", 1024, 84),
    ):
        resized = image.copy()
        try:
            resized.thumbnail(
                (max_dimension, max_dimension),
                Image.Resampling.LANCZOS,
            )
            output = io.BytesIO()
            resized.save(
                output,
                format="WEBP",
                quality=quality,
                method=6,
            )
            data = output.getvalue()
            generated.append(
                ProcessedImageVariant(
                    variant=variant,
                    data=data,
                    content_type="image/webp",
                    width=resized.width,
                    height=resized.height,
                    checksum_sha256=hashlib.sha256(data).hexdigest(),
                )
            )
        except Exception as exc:
            raise MediaProcessingError("MEDIA_IMAGE_VARIANT_PROCESSING_FAILED") from exc
        finally:
            resized.close()
    return tuple(generated)


def process_image(
    data: bytes,
    declared_content_type: str,
    *,
    max_pixels: int = 40_000_000,
    max_dimension: int = 4096,
) -> ProcessedImage:
    """Valida, orienta, limita e regrava JPEG, PNG ou WebP sem metadados."""

    if max_pixels <= 0 or max_dimension <= 0:
        raise MediaProcessingError("MEDIA_IMAGE_CONFIG_INVALID")
    if not isinstance(data, bytes) or not data:
        raise MediaProcessingError("MEDIA_IMAGE_EMPTY")

    if not isinstance(declared_content_type, str):
        raise MediaProcessingError("MEDIA_IMAGE_TYPE_NOT_ALLOWED")
    content_type = declared_content_type.strip().lower()
    expected_format = _MIME_TO_FORMAT.get(content_type)
    if expected_format is None:
        raise MediaProcessingError("MEDIA_IMAGE_TYPE_NOT_ALLOWED")

    magic_format = _format_from_magic(data)
    if magic_format is None:
        raise MediaProcessingError("MEDIA_IMAGE_MAGIC_INVALID")
    if magic_format != expected_format:
        raise MediaProcessingError("MEDIA_IMAGE_TYPE_MISMATCH")

    decoded = _open_and_verify(data, expected_format, max_pixels)
    try:
        oriented = ImageOps.exif_transpose(decoded)
        clean = _clean_mode(oriented, expected_format)
        clean.thumbnail(
            (max_dimension, max_dimension),
            Image.Resampling.LANCZOS,
        )
        if clean.width <= 0 or clean.height <= 0:
            raise MediaProcessingError("MEDIA_IMAGE_INVALID")
        encoded = _encode(clean, expected_format)
        variants = _image_variants(clean)
        return ProcessedImage(
            data=encoded,
            content_type=_FORMAT_TO_MIME[expected_format],
            width=clean.width,
            height=clean.height,
            checksum_sha256=hashlib.sha256(encoded).hexdigest(),
            variants=variants,
        )
    except MediaProcessingError:
        raise
    except Exception as exc:
        raise MediaProcessingError("MEDIA_IMAGE_PROCESSING_FAILED") from exc
    finally:
        decoded.close()
