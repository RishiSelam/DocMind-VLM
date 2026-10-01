import io
import os

from PIL import Image

from app import db
from app.services import ocr, pdf


def test_streaming_upload_has_no_size_cap(tmp_path):
    payload = os.urandom(1024 * 1024)
    src = io.BytesIO(payload * 30)  # 30 MiB
    path, size, digest = pdf.save_upload_stream(src, tmp_path, "big.pdf", "t1")
    assert size == 30 * 1024 * 1024 and path.stat().st_size == size and len(digest) == 64


def test_safe_name_strips_paths():
    assert pdf.safe_name("../../etc/passwd") == "passwd"
    assert pdf.safe_name("we ird*name?.pdf") == "we ird_name_.pdf"


def test_pdf_and_image_pages(report_pdf, invoice_png):
    assert pdf.count_pages(report_pdf) == 6
    assert pdf.count_pages(invoice_png) == 1
    img = pdf.render_page(report_pdf, 2, 100)
    assert isinstance(img, Image.Image) and img.mode == "RGB"
    assert "Pune" in pdf.text_layer(report_pdf, 2)
    assert pdf.text_layer(invoice_png, 0) == ""
    assert pdf.page_features(report_pdf, 0)["text_layer_chars"] > 0
    assert pdf.page_features(invoice_png, 0)["is_image_file"] == 1


def test_render_out_of_range(report_pdf):
    import pytest

    with pytest.raises(IndexError):
        pdf.render_page(report_pdf, 99)


def test_boxes_to_text_lines_and_columns():
    b = [dict(text="Quarter", x0=0, y0=0, x1=60, y1=12), dict(text="Revenue", x0=300, y0=1, x1=360, y1=13),
         dict(text="Q1", x0=0, y0=30, x1=20, y1=42), dict(text="41.7", x0=300, y0=31, x1=330, y1=43)]
    assert ocr.boxes_to_text(b) == "Quarter | Revenue\nQ1 | 41.7"
    assert ocr.boxes_to_text([]) == ""
    close = [dict(text="Hello", x0=0, y0=0, x1=50, y1=12), dict(text="world", x0=55, y0=0, x1=100, y1=12)]
    assert ocr.boxes_to_text(close) == "Hello world"


def test_rapidocr_reads_rendered_invoice(invoice_png):
    eng = ocr.get_engine("rapidocr")
    res = eng.extract(str(invoice_png), [0])[0]
    assert "INV-2041" in res.text.replace(" ", "")
    assert "1,284.50" in res.text or "1284.50" in res.text
    assert res.mean_conf and res.mean_conf > 0.8 and res.boxes


def test_ocr_cache_avoids_rerun(invoice_png):
    db.init_db()
    doc = {"id": "doc_cachetest", "path": str(invoice_png), "n_pages": 1}
    first = ocr.ocr_pages(doc)
    calls = {"n": 0}
    eng = ocr.get_engine()
    orig = eng.extract
    eng.extract = lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), orig(*a, **k))[1]
    try:
        second = ocr.ocr_pages(doc)
    finally:
        eng.extract = orig
    assert calls["n"] == 0 and second[0]["text"] == first[0]["text"]


def test_unknown_engine_message():
    import pytest

    with pytest.raises(ValueError, match="Unknown OCR_ENGINE"):
        ocr.get_engine("nope")


def test_textlayer_engine(report_pdf):
    res = ocr.get_engine("textlayer").extract(str(report_pdf), [4])[4]
    assert "342" in res.text
