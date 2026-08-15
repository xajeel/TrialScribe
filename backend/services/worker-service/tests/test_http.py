from urllib.parse import quote

from trialscribe_worker.utils.http import attachment_content_disposition


def test_unicode_filename_uses_rfc5987_parameter() -> None:
    filename = "研究📄.docx"
    header = attachment_content_disposition(filename)
    assert f"filename*=UTF-8''{quote(filename, safe='')}" in header
    assert "\r" not in header
    assert "\n" not in header


def test_quotes_and_control_characters_are_stripped() -> None:
    header = attachment_content_disposition('report "draft".docx')
    assert 'filename="report _draft_.docx"' in header
    injected = attachment_content_disposition("report\r\nX-Injected: yes.docx")
    assert "\r" not in injected
    assert "\n" not in injected
    assert "filename*=UTF-8''" in injected
