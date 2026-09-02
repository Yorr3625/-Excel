import json
from io import BytesIO

import pytest
from PIL import Image

from modules import invoice_ocr


def _image_bytes(image_format: str) -> bytes:
    image = Image.new("RGB", (20, 20), "white")
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


def test_jpeg_is_validated_without_reencoding():
    content = _image_bytes("JPEG")

    photo = invoice_ocr.validate_and_prepare_photo("накладная.jpg", content)

    assert photo.original == content
    assert photo.ocr_content == content
    assert photo.extension == ".jpg"
    assert photo.ocr_mime_type == "image/jpeg"


def test_webp_is_converted_to_jpeg_only_for_ocr():
    photo = invoice_ocr.validate_and_prepare_photo("накладная.webp", _image_bytes("WEBP"))

    assert photo.extension == ".webp"
    assert photo.ocr_mime_type == "image/jpeg"
    assert photo.ocr_content[:2] == b"\xff\xd8"
    assert photo.original != photo.ocr_content


def test_rejects_unsupported_extension_before_uploading_to_ocr():
    with pytest.raises(invoice_ocr.InvoiceOcrError, match="JPG"):
        invoice_ocr.validate_and_prepare_photo("накладная.pdf", b"not an image")


def test_rejects_damaged_image():
    with pytest.raises(invoice_ocr.InvoiceOcrError, match="прочитать"):
        invoice_ocr.validate_and_prepare_photo("накладная.png", b"not an image")


def test_recognize_sends_expected_yandex_request(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "result": {
                        "textAnnotation": {
                            "blocks": [
                                {"lines": [{"words": [{"text": "Банан"}, {"text": "кг"}]}]}
                            ]
                        }
                    }
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(invoice_ocr, "urlopen", fake_urlopen)

    text = invoice_ocr.recognize_image(b"image", "image/jpeg", "test-key", "b1g-folder")

    request = captured["request"]
    payload = json.loads(request.data.decode())
    assert request.full_url == invoice_ocr.OCR_ENDPOINT
    assert request.get_header("Authorization") == "Api-Key test-key"
    assert request.get_header("X-folder-id") == "b1g-folder"
    assert payload["mimeType"] == "image/jpeg"
    assert payload["languageCodes"] == ["ru", "en"]
    assert payload["model"] == "page"
    assert text == "Банан кг"


def test_parse_invoice_lines_calculates_total_when_it_is_missing():
    rows = invoice_ocr.parse_invoice_lines("Банан - кг 25 цена 140")

    assert rows == [
        {
            "name": "Банан",
            "unit": "кг",
            "quantity": "25",
            "unit_price": "140",
            "line_total": "3500",
        }
    ]


def test_parse_invoice_lines_keeps_explicit_sum():
    rows = invoice_ocr.parse_invoice_lines("Молоко шт 12 85,50 1 026,00")

    assert rows[0]["quantity"] == "12"
    assert rows[0]["unit_price"] == "85.5"
    assert rows[0]["line_total"] == "1026"
