"""Brotli (br) sikistirma destegi: yalnizca cozulebiliyorsa istenir ve dogru cozulur."""
import io

import pytest
import urllib3.util.request

from seo_app import canli


def test_brotli_paketi_varsa_br_istenir():
    pytest.importorskip("brotlicffi")
    assert "br" in canli._kodlamalar().split(", ")
    assert "br" in canli._oturum.headers["Accept-Encoding"]


def test_brotli_cozulemiyorsa_br_istenmez(monkeypatch):
    monkeypatch.setattr(urllib3.util.request, "ACCEPT_ENCODING", "gzip,deflate")
    assert canli._kodlamalar() == "gzip, deflate"


def test_br_sikistirilmis_yanit_dogru_cozulur():
    brotli = pytest.importorskip("brotlicffi")
    html = "<html><title>Düzce Üniversitesi</title></html>".encode("utf-8")
    yanit = urllib3.HTTPResponse(body=io.BytesIO(brotli.compress(html)), headers={"content-encoding": "br"},
                                 preload_content=False, decode_content=True)
    assert yanit.read() == html
