"""Verificações offline: integridade, restrições, codificação e links do índice."""
import hashlib
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from lxml import html
from cae import build_control, control_tsv, render_control

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
        self.assertEqual(normalize_number(" 006904/23-84 "), "23066.006904/2023-84")
        self.assertEqual(normalize_number("23066.006904/2023-84"), "23066.006904/2023-84")
        for invalid in ("../teste", "23066.026112/2026", "026112", "", "<script>"):
            with self.assertRaises(SipacError):
                normalize_number(invalid)

    def test_cae_control_and_receipt(self):
        record = {"processo": "23066.006904/2023-84", "cabecalho": {"Unidade de Origem": "DEPARTAMENTO DE CIRURGIA/FMB (12.01.21.22)", "Assunto Detalhado": "Proposta de Criação do Programa de Residência Médica em Cirurgia Cardiovascular", "Data de Autuação": "07/02/2023 11:20"}, "movimentacoes": {"colunas": ["Unidade Origem", "Unidade Destino", "Recebido Em"], "linhas": [["PROPG", "CONSELHO ACADÊMICO DE ENSINO /UFBA", "23/02/2026 11:33"], ["CAE", "CARE", "20/10/2026"], ["X", "CGAE", "15/11/2026"]]}}
        c = build_control(record)
        self.assertEqual(len(c["colunas"]), 17)
        self.assertEqual(c["valores"], ["006904/23-84", "PÓS", "FMB - Faculdade de Medicina", record["cabecalho"]["Assunto Detalhado"], "A definir", "Criação de curso", "30", "07/02/2023", "23/02/2026", "A definir", "A definir", "A definir", "A definir", "Em análise", "A definir", "A definir", "A definir"])
        self.assertEqual(len(control_tsv(c).split("\t")), 17)
        self.assertEqual(len(control_tsv(c, header=True).split("\r\n")), 2)
        self.assertIn("data-cae-copy", render_control(c))

    def test_cae_unknown_dates_and_tsv_safety(self):
        record = {"processo": "23066.006904/2023-84", "cabecalho": {"Data de Autuação": "31/02/2023"}, "movimentacoes": {"colunas": ["Destino", "Recebido Em"], "linhas": [["CAE", "31/02/2026"], ["CAE", "15/01/2025"], ["CAE", "23/02/2026"]]}}
        c = build_control(record)
        self.assertEqual(c["valores"][1], "A definir")
        self.assertEqual(c["valores"][7], "A definir")
        self.assertEqual(c["valores"][8], "23/02/2026")
        c["valores"][3] = "=FORMULA()\tsegunda\nlinha"
        self.assertIn("'=FORMULA() segunda linha", control_tsv(c))
        self.assertEqual(len(control_tsv(c).split("\t")), 17)
        self.assertNotIn("\n", control_tsv(c))

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
            control = (root / "controle-cae.tsv").read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(len(control), 2)
            self.assertEqual(len(control[1].split("\t")), 17)
            self.assertEqual(len(page.xpath("//input[@data-cae-value]")), 17)
            self.assertTrue((root / "controle-cae.js").is_file())

    def test_local_api_normalizes_short_number(self):
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        from app import State, make_handler
        state = State()
        with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state)) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with patch.object(state, "run"):
                    body = json.dumps({"processo": "006904/23-84", "destino": tempfile.gettempdir()}).encode()
                    req = Request(base + "/api/consultar", data=body, headers={"X-Local-Token": state.token, "Content-Type": "application/json"})
                    with urlopen(req) as result:
                        self.assertEqual(result.status, 202)
                    # Handler starts the worker before returning HTTP 202.
                    self.assertEqual(state.snapshot()["processo"], "23066.006904/2023-84")
                with urlopen(base + "/controle-cae.js") as script:
                    self.assertIn(b"installCaeControls", script.read())
            finally:
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    unittest.main()
