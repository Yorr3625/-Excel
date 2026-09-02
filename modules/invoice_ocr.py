"""Распознавание текста на фотографиях накладных через Yandex Vision OCR."""

from __future__ import annotations

import base64
import json
import re
import warnings
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image, UnidentifiedImageError


OCR_ENDPOINT = "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText"
MAX_PHOTOS = 10
MAX_PHOTO_BYTES = 10 * 1024 * 1024
OCR_TIMEOUT_SECONDS = 45
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}
_UNIT_PATTERN = re.compile(
    r"\b(кг|шт|шту?к\.?|л|литр(?:а|ов)?|уп\.?|упак(?:овка|\.)?|"
    r"кор(?:об(?:ка)?|\.)?|пач(?:ка|\.)?|бут(?:ылка|\.)?)\b",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(r"(?<![\w.,])\d{1,3}(?:[ .]\d{3})*(?:[,.]\d+)?|(?<![\w.,])\d+(?:[,.]\d+)?")
_UNIT_LABELS = {
    "кг": "кг",
    "шт": "шт",
    "штука": "шт",
    "штук": "шт",
    "л": "л",
    "литр": "л",
    "литра": "л",
    "литров": "л",
    "уп": "уп",
    "упаковка": "уп",
    "кор": "кор",
    "короб": "кор",
    "коробка": "кор",
    "пач": "пач",
    "пачка": "пач",
    "бут": "бут",
    "бутылка": "бут",
}


class InvoiceOcrError(RuntimeError):
    """Ошибка, которую можно безопасно показать пользователю."""


@dataclass(frozen=True)
class PreparedPhoto:
    original: bytes
    extension: str
    ocr_content: bytes
    ocr_mime_type: str


def validate_and_prepare_photo(filename: str, content: bytes) -> PreparedPhoto:
    """Проверяет фото и подготавливает его для OCR без записи на диск."""

    suffix = _suffix(filename)
    if suffix not in _ALLOWED_SUFFIXES:
        raise InvoiceOcrError("Поддерживаются только фотографии JPG, PNG и WEBP")
    if not content:
        raise InvoiceOcrError("Один из файлов пустой")
    if len(content) > MAX_PHOTO_BYTES:
        raise InvoiceOcrError("Размер одного фото не должен превышать 10 МБ")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
                image_format = image.format
                if image_format not in _FORMATS:
                    raise InvoiceOcrError("Файл не является фотографией JPG, PNG или WEBP")
                extension, mime_type = _FORMATS[image_format]
                if image_format != "WEBP":
                    return PreparedPhoto(content, extension, content, mime_type)
                return PreparedPhoto(
                    content,
                    extension,
                    _webp_to_jpeg(image),
                    "image/jpeg",
                )
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise InvoiceOcrError("Не удалось прочитать фотографию") from error


def recognize_images(photos: list[PreparedPhoto], api_key: str, folder_id: str) -> str:
    """Распознаёт фотографии по очереди и возвращает общий текст."""

    if not api_key.strip() or not folder_id.strip():
        raise InvoiceOcrError("Сначала укажите ключ Yandex Vision и ID каталога в настройках")
    if not photos:
        raise InvoiceOcrError("Добавьте хотя бы одну фотографию накладной")
    if len(photos) > MAX_PHOTOS:
        raise InvoiceOcrError("Можно распознать не более 10 фотографий за раз")

    pages = [
        recognize_image(photo.ocr_content, photo.ocr_mime_type, api_key, folder_id)
        for photo in photos
    ]
    text = "\n\n".join(page for page in pages if page.strip()).strip()
    if not text:
        raise InvoiceOcrError("Yandex Vision не распознал текст на фотографиях")
    return text


def recognize_image(content: bytes, mime_type: str, api_key: str, folder_id: str) -> str:
    """Отправляет одну фотографию в Yandex Vision OCR."""

    payload = json.dumps(
        {
            "mimeType": mime_type,
            "languageCodes": ["ru", "en"],
            "model": "page",
            "content": base64.b64encode(content).decode("ascii"),
        }
    ).encode("utf-8")
    request = Request(
        OCR_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Api-Key {api_key.strip()}",
            "Content-Type": "application/json",
            "x-folder-id": folder_id.strip(),
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=OCR_TIMEOUT_SECONDS) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        messages = {
            401: "Yandex Vision отклонил ключ API",
            403: "Нет доступа к Yandex Vision или указанному каталогу",
            429: "Yandex Vision временно ограничил число запросов. Повторите позже",
        }
        raise InvoiceOcrError(messages.get(error.code, f"Yandex Vision вернул ошибку {error.code}")) from error
    except (URLError, TimeoutError, OSError) as error:
        raise InvoiceOcrError("Не удалось обратиться к Yandex Vision. Проверьте интернет и повторите") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvoiceOcrError("Yandex Vision вернул некорректный ответ") from error

    return _extract_text(response_data)


def parse_invoice_lines(text: str) -> list[dict[str, str]]:
    """Консервативно строит товарные строки из OCR-текста."""

    rows = []
    for source_line in text.splitlines():
        line = " ".join(source_line.replace("—", "-").split())
        unit_match = _UNIT_PATTERN.search(line)
        if unit_match is None:
            continue

        name = line[: unit_match.start()].strip(" -:;,.\t")
        if not name:
            continue

        numbers = [_parse_number(match.group()) for match in _NUMBER_PATTERN.finditer(line[unit_match.end() :])]
        numbers = [number for number in numbers if number is not None]
        if len(numbers) < 2 or numbers[0] <= 0 or numbers[1] < 0:
            continue

        quantity, unit_price = numbers[:2]
        line_total = numbers[2] if len(numbers) >= 3 and numbers[2] >= 0 else quantity * unit_price
        rows.append(
            {
                "name": name,
                "unit": _normalize_unit(unit_match.group()),
                "quantity": _format_decimal(quantity),
                "unit_price": _format_decimal(unit_price),
                "line_total": _format_decimal(line_total),
            }
        )

    return rows


def _extract_text(response_data: object) -> str:
    if not isinstance(response_data, dict):
        raise InvoiceOcrError("Yandex Vision вернул некорректный ответ")

    results = response_data.get("results")
    if not isinstance(results, list):
        result = response_data.get("result")
        results = [result] if isinstance(result, dict) else []

    lines = []
    for result in results:
        annotation = result.get("textAnnotation") if isinstance(result, dict) else None
        blocks = annotation.get("blocks") if isinstance(annotation, dict) else None
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            for line in block.get("lines", []) if isinstance(block, dict) else []:
                words = line.get("words", []) if isinstance(line, dict) else []
                text = " ".join(
                    word.get("text", "").strip()
                    for word in words
                    if isinstance(word, dict) and isinstance(word.get("text"), str)
                ).strip()
                if text:
                    lines.append(text)

    text = "\n".join(lines)
    if not text:
        raise InvoiceOcrError("Yandex Vision не распознал текст на фотографии")
    return text


def _webp_to_jpeg(image: Image.Image) -> bytes:
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGB", image.size, "white")
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _suffix(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _parse_number(value: str) -> Decimal | None:
    normalized = value.replace(" ", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _format_decimal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _normalize_unit(value: str) -> str:
    normalized = value.lower().rstrip(".")
    return _UNIT_LABELS.get(normalized, normalized)
