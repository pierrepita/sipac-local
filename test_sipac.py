"""Verificações offline: integridade, restrições, codificação e links do índice."""
import hashlib
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from lxml import html

from sipac import (BASE, Client, Response, SipacError, checked_url, download_document,
                   fields, normalize_number, parse_documents, render_report, require_content, safe_fragment)


def response(body, mime="text/html; charset=utf-8"):
    headers = Message()
    headers["Content-Type"] = mime
    return Response(BASE + "/public/documento", body.encode("utf-8") if isinstance(body, str) else body, headers)


def document():
    return {"ordem": 1, "tipo": "OFICIO", "data": "11/05/2026", "origem": "Unidade", "natureza": "OSTENSIVO",
            "id": "123", "descricao": "OFICIO", "acoes": [{"url": BASE + "/public/original", "variante": "original"},
            {"url": BASE + "/public/assinaturas", "variante": "com_assinaturas"}], "arquivos": [], "erros": [], "avisos": []}


class DownloaderTests(unittest.TestCase):
    def test_complete_nup(self):
        self.assertEqual(normalize_number("23066026112202679"), "23066.026112/2026-79")
        for invalid in ("../teste", "23066.026112/2026", "026112", "", "<script>"):
            with self.assertRaises(SipacError):
                normalize_number(invalid)

    def test_scope_and_redirects(self):
        self.assertEqual(checked_url("/public/documento"), BASE + "/public/documento")
        for external in ("https://example.com", "http://sipac.ufba.br/a", "//evil.test/a", "https://sipac.ufba.br@evil.test"):
            with self.assertRaises(SipacError):
                checked_url(external)

    def test_encoding_and_metadata(self):
        page = response('<table><tr><th>Assunto:</th><td>Alteração curricular</td><th>Ano:</th><td>2026</td></tr></table>')
        self.assertEqual(fields(page.root()), {"Assunto": "Alteração curricular", "Ano": "2026"})

    def test_restricted_document_is_never_reported_as_saved(self):
        doc = document()
        doc.update(natureza="RESTRITO", acoes=[])
        with tempfile.TemporaryDirectory() as directory:
            result = download_document(doc, Path(directory))
        self.assertEqual(result["status"], "restrito")
        self.assertFalse(result["arquivos"])

    def test_http200_login_is_not_a_document(self):
        login = response('<html><form><input type="password"></form></html>')
        with self.assertRaises(SipacError):
            require_content(login)
        doc = document()
        with tempfile.TemporaryDirectory() as directory, patch.object(Client, "request", return_value=login):
            result = download_document(doc, Path(directory))
            self.assertEqual(result["status"], "erro")
            self.assertFalse(list(Path(directory).iterdir()))

    def test_partial_download_and_pdf_integrity(self):
        original = b"%PDF-1.7\noriginal bytes\x00\xff"
        doc = document()
        with tempfile.TemporaryDirectory() as directory, patch.object(Client, "request", side_effect=[response(original, "application/download"), SipacError("HTTP 503")]):
            result = download_document(doc, Path(directory))
            saved = Path(directory) / Path(result["arquivos"][0]["caminho"]).name
            self.assertEqual(saved.read_bytes(), original)
            self.assertEqual(result["arquivos"][0]["sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(result["status"], "parcial")
            self.assertTrue(result["erros"])

    def test_active_content_removed_from_local_copy(self):
        page = response('<html><body onload="evil()"><script>evil()</script><p>Pré-requisitos de Enfermagem</p><iframe src="https://evil.test"></iframe><a href="javascript:evil()">Link</a><img src="https://evil.test/a"><form><input name="senha"></form></body></html>')
        fragment = safe_fragment(page.root())
        self.assertIn("Pré-requisitos", fragment)
        for unsafe in ("<script", "onload", "iframe", "javascript:", "<input", "<img", "<form"):
            self.assertNotIn(unsafe, fragment)

    def test_retry_fetches_only_missing_version(self):
        original = b"%PDF-1.7\noriginal bytes"
        signed = b"%PDF-1.7\nsigned bytes"
        doc = document()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Client, "request", side_effect=[response(original, "application/download"), SipacError("HTTP 503")]):
                download_document(doc, Path(directory))
            self.assertEqual(doc["status"], "parcial")
            with patch.object(Client, "request", return_value=response(signed, "application/download")) as request:
                download_document(doc, Path(directory))
                self.assertEqual(request.call_count, 1)
                self.assertEqual(request.call_args.args[0], BASE + "/public/assinaturas")
            self.assertEqual(doc["status"], "baixado")
            self.assertEqual(len(doc["arquivos"]), 2)
            self.assertFalse(doc["erros"])

    def test_all_document_actions_are_retained(self):
        page = response('''<table><caption>Documentos do Processo</caption><tbody><tr><td>1</td><td>OFICIO</td><td>11/05/2026</td><td>Unidade</td><td>OSTENSIVO</td><td>
        <a onclick="window.open('/public/verArquivoDocumento?idArquivo=1')"><img alt="Visualizar Documento Original"></a>
        <a onclick="window.open('/public/verArquivoDocumento?idArquivo=1&amp;idDocumento=12')"><img alt="Visualizar Documento"></a>
        <a onclick="documentoPublicoDetalhado(12)"><img alt="Dados"></a></td></tr></tbody></table>''')
        docs = parse_documents(page)
        self.assertEqual(len(docs), 1)
        self.assertEqual(len(docs[0]["acoes"]), 2)
        self.assertEqual(docs[0]["id"], "12")

    def test_index_has_relative_valid_links_and_escaped_descriptions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "documentos").mkdir()
            file = root / "documentos" / "001_original.pdf"
            file.write_bytes(b"%PDF-1.7")
            doc = document()
            doc.update(status="baixado", descricao="Ofício <img onerror=evil()>", arquivos=[{"caminho": "documentos/001_original.pdf", "formato": "pdf", "variante": "original"}])
            record = {"processo": "23066.026112/2026-79", "consultado_em": "2026-11-15", "fonte": BASE,
                      "cabecalho": {"Processo": "23066.026112/2026-79"}, "interessados": {"colunas": [], "linhas": []},
                      "movimentacoes": {"colunas": [], "linhas": []}, "avisos": [], "documentos": [doc]}
            render_report(record, root)
            page = html.fromstring((root / "indice.html").read_bytes())
            self.assertFalse(page.xpath("//img"))
            links = page.xpath("//a[starts-with(@href,'documentos/')]/@href")
            self.assertEqual(links, ["documentos/001_original.pdf"])
            self.assertTrue(all((root / link).is_file() for link in links))
            self.assertEqual(json.loads((root / "processo.json").read_text())["processo"], record["processo"])


if __name__ == "__main__":
    unittest.main()
