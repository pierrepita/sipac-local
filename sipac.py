"""Consulta e cópia local do portal público do SIPAC/UFBA.

Não utiliza credenciais e não contorna restrições de acesso.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import socket
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from email.message import Message
from html import escape
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from lxml import etree, html

BASE = "https://sipac.ufba.br"
PORTAL = BASE + "/public/jsp/portal.jsf"
HOST = "sipac.ufba.br"
MAX_BYTES = 250 * 1024 * 1024


class SipacError(Exception):
    pass


def text(node):
    return " ".join(node.text_content().split())


def fold(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c))


def normalize_number(value):
    value = value.strip()
    # Aceita NUP formatado ou seus 17 dígitos, sem completar dígitos omitidos.
    if re.fullmatch(r"\d{17}", value):
        value = f"{value[:5]}.{value[5:11]}/{value[11:15]}-{value[15:]}"
    if not re.fullmatch(r"\d{5}\.\d{6}/\d{4}-\d{2}", value):
        raise SipacError("Informe o número completo, por exemplo 23066.026112/2026-79.")
    return value


def slug(value, limit=75):
    result = re.sub(r"[^a-zA-Z0-9_-]+", "_", fold(value)).strip("_")[:limit]
    return result or "documento"


def checked_url(value, base=BASE):
    resolved = urljoin(base, value)
    parsed = urlsplit(resolved)
    if (parsed.scheme != "https" or parsed.hostname != HOST or parsed.port not in (None, 443)
            or parsed.username or parsed.password):
        raise SipacError("O portal retornou um endereço externo inesperado. Download interrompido.")
    return resolved


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl, req.full_url)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class Response:
    url: str
    body: bytes
    headers: Message

    def root(self):
        encoding = self.headers.get_content_charset()
        return html.fromstring(self.body, parser=html.HTMLParser(encoding=encoding))


class Client:
    """Uma sessão JSF por cliente. Não compartilhe esta instância entre threads."""
    def __init__(self, timeout=45):
        self.timeout = timeout
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()), SafeRedirect())

    def request(self, url, data=None):
        url = checked_url(url)
        for attempt in range(3):
            try:
                request = Request(url, data=urlencode(data).encode("utf-8") if data is not None else None,
                                  headers={"User-Agent": "SIPACLocal/1.0 (consulta publica; copia local)"})
                with self.opener.open(request, timeout=self.timeout) as response:
                    checked_url(response.url)
                    if int(response.headers.get("Content-Length", "0")) > MAX_BYTES:
                        raise SipacError("Arquivo excede o limite de 250 MB por resposta.")
                    body = bytearray()
                    while chunk := response.read(64 * 1024):
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise SipacError("Arquivo excede o limite de 250 MB por resposta.")
                    return Response(response.url, bytes(body), response.headers)
            except HTTPError as exc:
                if exc.code in (429, 502, 503, 504) and attempt < 2:
                    time.sleep(1 + attempt * 2)
                    continue
                raise SipacError(f"SIPAC respondeu HTTP {exc.code}.") from exc
            except (URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
                if data is None and attempt < 2:
                    time.sleep(1 + attempt * 2)
                    continue
                raise SipacError("Falha de conexão com o SIPAC. Verifique a internet e tente novamente.") from exc

    def search(self, number):
        number = normalize_number(number)
        response = self.request(PORTAL)
        root = response.root()
        forms = root.xpath("//form[@id='processoForm']")
        if not forms:
            raise SipacError("O formulário público mudou ou está indisponível. Nenhum processo foi baixado.")
        form = forms[0]
        data = form_fields(form)
        parts = re.fullmatch(r"(\d{5})\.(\d{6})/(\d{4})-(\d{2})", number).groups()
        data.update(zip(("RADICAL_PROTOCOLO", "NUM_PROTOCOLO", "ANO_PROTOCOLO", "DV_PROTOCOLO"), parts))
        for button in form.xpath(".//input[@type='submit']"):
            if "Consultar Processo" in button.get("value", ""):
                data[button.get("name")] = button.get("value")
                break
        response = self.request(urljoin(response.url, form.get("action")), data)
        root = response.root()
        matches = []
        for row in root.xpath("//tr[td]"):
            if number in text(row):
                for a in row.xpath(".//a[contains(@href,'processo_detalhado.jsf')]"):
                    matches.append(checked_url(a.get("href"), response.url))
        if not matches:
            visible = fold(text(root))
            if "captcha" in visible or "recaptcha" in visible:
                raise SipacError("A consulta exige CAPTCHA. Esta versão não resolve CAPTCHA automaticamente.")
            raise SipacError("Processo não localizado na consulta pública. Confira o número e a disponibilidade no portal.")
        if len(set(matches)) != 1:
            raise SipacError("A consulta retornou resultados ambíguos. Nenhum processo foi escolhido.")
        return self.request(matches[0])

    def follow(self, action, response):
        url = action_url(action, response.url)
        if url:
            return self.request(url)
        js = action.get("onclick", "")
        form_id = re.search(r"getElementById\(['\"]([^'\"]+)['\"]\)", js)
        pairs = re.findall(r"'([^']+)'\s*:\s*'([^']*)'", js)
        if form_id and pairs:
            root = response.root()
            forms = root.xpath("//form[@id=$name]", name=form_id[1])
            if forms:
                form = forms[0]
                data = form_fields(form, submit=False)
                data.update(pairs)
                return self.request(urljoin(response.url, form.get("action")), data)
        raise SipacError("Paginação ou ação JSF não reconhecida. A cópia não foi concluída.")


def form_fields(form, submit=False):
    data = {}
    for element in form.xpath(".//input[@name]"):
        kind = element.get("type", "text").lower()
        if element.get("disabled") is not None or kind in ("button", "image", "file", "reset"):
            continue
        if kind == "submit" and not submit:
            continue
        if kind in ("checkbox", "radio") and element.get("checked") is None:
            continue
        data[element.get("name")] = element.get("value", "")
    return data


def action_url(element, base):
    onclick = element.get("onclick", "")
    found = re.search(r"window\.open\(\s*['\"]([^'\"]+)['\"]", onclick)
    if found:
        return checked_url(found[1], base)
    href = element.get("href", "")
    if href and not href.startswith(("#", "javascript:")):
        return checked_url(href, base)
    return None


def table_named(root, caption):
    return root.xpath("//table[caption[contains(normalize-space(.), $caption)]]", caption=caption)


def fields(root):
    result = {}
    for row in root.xpath("//tr"):
        cells = row.xpath("./th|./td")
        for label, value in zip(cells, cells[1:]):
            key = text(label).rstrip(": ")
            if label.tag == "th" and value.tag == "td" and key and not value.xpath(".//table"):
                result[key] = text(value)
    return result


def tabular(root, caption):
    tables = table_named(root, caption)
    if not tables:
        return {"colunas": [], "linhas": []}
    table = tables[0]
    return {"colunas": [text(x) for x in table.xpath("./thead/tr/th")],
            "linhas": [[text(x) for x in row.xpath("./td")] for row in table.xpath("./tbody/tr|./tr") if row.xpath("./td")]}


def parse_documents(response):
    root = response.root()
    tables = table_named(root, "Documentos do Processo")
    if len(tables) != 1:
        raise SipacError("A tabela de documentos do processo não foi reconhecida. Nenhuma cópia integral foi declarada.")
    docs = []
    for row in tables[0].xpath("./tbody/tr|./tr"):
        cells = row.xpath("./td")
        if len(cells) < 5:
            if cells and "nenhum" not in fold(text(row)):
                raise SipacError("Uma linha de documento não foi reconhecida.")
            continue
        order = text(cells[0])
        if not order.isdigit():
            raise SipacError("Numeração inesperada na lista de documentos.")
        doc = {"ordem": int(order), "tipo": text(cells[1]), "data": text(cells[2]),
               "origem": text(cells[3]), "natureza": text(cells[4]), "id": "",
               "descricao": text(cells[1]), "acoes": [], "arquivos": [], "erros": [], "avisos": []}
        seen = set()
        for anchor in row.xpath(".//a"):
            onclick = anchor.get("onclick", "")
            info = re.search(r"documentoPublicoDetalhado\((\d+)\)", onclick)
            if info:
                doc["id"] = info[1]
                doc["url_dados"] = BASE + "/public/jsp/processos/info_documento.jsf?idDoc=" + info[1]
                continue
            url = action_url(anchor, response.url)
            if not url or url in seen:
                continue
            if not ("verArquivoDocumento" in url or "documento_visualizacao.jsf" in url):
                doc["avisos"].append("Ação de documento desconhecida: requer conferência no SIPAC.")
                continue
            labels = anchor.xpath(".//img/@alt")
            label = labels[0] if labels else (text(anchor) or "Documento")
            variant = "original" if "Original" in label else "com_assinaturas"
            doc["acoes"].append({"url": url, "variante": variant})
            seen.add(url)
            query = parse_qs(urlsplit(url).query)
            doc["id"] = doc["id"] or (query.get("idDocumento") or query.get("idDoc") or [""])[0]
        if "url_dados" not in doc and doc["id"]:
            doc["url_dados"] = BASE + "/public/jsp/processos/info_documento.jsf?idDoc=" + doc["id"]
        docs.append(doc)
    return docs


def next_page(response):
    root = response.root()
    # A tela atual mostra todos os documentos. Versões com paginador são percorridas
    # quando há um controle explícito de próxima página; formatos desconhecidos falham.
    pagers = root.xpath("//*[contains(@class,'paginador') or contains(@class,'paginacao') or contains(@class,'paginator')]")
    for pager in pagers:
        for a in pager.xpath(".//a"):
            label = fold(" ".join([text(a), a.get("title", ""), " ".join(a.xpath('.//img/@alt'))]))
            if any(token in label for token in ("proxima", "seguinte", "next")) or label.strip() in (">", ">>", "›", "»"):
                return a
        if pager.xpath(".//a"):
            # Só há links para páginas anteriores no final? O número atual deve ser
            # identificável e maior ou igual a todos os destinos numéricos.
            current = pager.xpath(".//*[contains(@class,'atual') or contains(@class,'selected') or self::strong or self::b]")
            numbers = [int(text(a)) for a in pager.xpath(".//a") if text(a).isdigit()]
            if not current or not text(current[0]).isdigit() or (numbers and max(numbers) > int(text(current[0]))):
                raise SipacError("Paginação não reconhecida. Não foi possível verificar todos os documentos.")
    return None


def require_content(response):
    root = response.root()
    for el in root.xpath("//script|//style"):
        el.drop_tree()
    visible = fold(text(root))
    if root.xpath("//input[@type='password']"):
        raise SipacError("O SIPAC pediu autenticação para este item.")
    denied = ("acesso negado", "acesso nao autorizado", "nao possui permissao", "nao tem permissao",
              "documento nao encontrado", "documento nao esta disponivel", "sessao expirada",
              "erro inesperado", "erro interno", "nao foi possivel visualizar")
    if any(term in visible for term in denied):
        raise SipacError("O SIPAC não disponibilizou o conteúdo deste item na consulta pública.")
    return root


REPORT_CSS = """
:root{color-scheme:light}*{box-sizing:border-box}body{font:15px/1.55 Arial,sans-serif;color:#172b3a;background:#f3f5f7;margin:0}
main{max-width:1200px;margin:36px auto;padding:34px;background:#fff;border-radius:18px}h1{font-size:29px;margin:7px 0 14px;overflow-wrap:anywhere}
h2{font-size:20px;margin-top:32px}.eyebrow{font-size:12px;letter-spacing:1.6px;color:#227966;text-transform:uppercase;font-weight:bold}
.note{padding:16px;background:#eef5f4;border-radius:10px}.muted{color:#5e6d78;font-size:13px}table{border-collapse:collapse;width:100%;margin:16px 0;font-size:13px}
th,td{text-align:left;border-bottom:1px solid #dce4e8;padding:11px 9px;vertical-align:top;overflow-wrap:anywhere}thead th{background:#eaf0f5;color:#203c53}
.fields th{width:25%}a{color:#126a8a;text-decoration:underline;text-underline-offset:2px}.links a{display:block;margin-bottom:6px}.badge{font-weight:bold;color:#22674e}
.warning{color:#9b4f0b}.scroll{overflow:auto}footer{margin-top:28px;color:#667782;font-size:12px}
@media print{body{background:white}main{margin:0;padding:0}thead{display:table-header-group}tr{break-inside:avoid}a{color:inherit}h2{break-after:avoid}}
"""


def html_page(title, body):
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><style>{REPORT_CSS}</style></head><body><main>{body}</main></body></html>'


def safe_fragment(root):
    # Cria uma cópia passiva, sem formulários, scripts, imagens remotas ou eventos.
    root = html.fromstring(html.tostring(root))
    for el in root.xpath("//script|//style|//link|//meta|//iframe|//object|//embed|//img|//input|//button|//textarea|//select|//svg|//video|//audio"):
        el.drop_tree()
    allowed = {"html", "body", "div", "p", "span", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "strong", "b", "i", "em", "u", "s", "br", "hr", "center", "ol", "ul", "li", "h1", "h2", "h3", "h4", "a", "caption", "small", "sup", "sub", "font"}
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            if el.getparent() is not None:
                el.getparent().remove(el)
            continue
        if el.tag == "head":
            el.drop_tree()
            continue
        for attr in list(el.attrib):
            if attr not in ("href", "colspan", "rowspan", "align"):
                del el.attrib[attr]
        if el.get("href"):
            try:
                el.set("href", checked_url(el.get("href")))
            except SipacError:
                del el.attrib["href"]
        if el.tag not in allowed and el.getparent() is not None:
            el.drop_tag()
    bodies = root.xpath("//body")
    body = bodies[0] if bodies else root
    return (escape(body.text or "") + "".join(html.tostring(c, encoding="unicode") for c in body))


def field_table(values):
    return '<table class="fields">' + "".join(f"<tr><th>{escape(k)}</th><td>{escape(v or 'Não informado')}</td></tr>" for k, v in values.items()) + "</table>"


def atomic_write(path, data):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    temporary.replace(path)


def file_extension(response):
    body = response.body
    if not body:
        raise SipacError("O SIPAC retornou um arquivo vazio.")
    if body[:1024].lstrip().startswith(b"%PDF-"):
        return ".pdf", "application/pdf"
    if response.headers.get_content_type() in ("text/html", "application/xhtml+xml") or body[:100].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return ".html", "text/html"
    name = response.headers.get_filename() or ""
    # Alguns servidores SIPAC retornam filename com aspas sem fechamento.
    suffix = Path(name.strip('\"')).suffix.lower()
    known = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".odt", ".ods", ".png", ".jpg", ".jpeg", ".zip", ".rtf", ".ppt", ".pptx", ".xml"}
    if body.startswith(b"PK") and suffix in {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".zip"}:
        return suffix, "application/octet-stream"
    if body.startswith(b"\x89PNG"):
        return ".png", "image/png"
    if body.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if suffix in known and suffix != ".pdf":
        return suffix, "application/octet-stream"
    raise SipacError("Formato de arquivo não reconhecido; resposta não foi marcada como download válido.")


def download_document(doc, folder, timeout=45):
    client = Client(timeout)
    prefix = f"{doc['ordem']:03d}_{slug(doc['tipo'])}"
    doc["erros"] = []
    doc["avisos"] = [w for w in doc["avisos"] if not w.startswith("Dados complementares:")]
    # Uma segunda tentativa conserva arquivos válidos e busca apenas o que faltou.
    valid_files = []
    for saved in doc["arquivos"]:
        file = folder / Path(saved["caminho"]).name
        if file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() == saved["sha256"]:
            valid_files.append(saved)
    doc["arquivos"] = valid_files
    has_metadata = doc.get("arquivo_dados") and (folder / Path(doc["arquivo_dados"]).name).is_file()
    if doc.get("url_dados") and not has_metadata:
        try:
            response = client.request(doc["url_dados"])
            root = require_content(response)
            metadata = fields(root)
            if not metadata.get("Tipo do Documento"):
                raise SipacError("A página de dados do documento não foi reconhecida.")
            doc["dados"] = metadata
            description = metadata.get("Assunto Detalhado", "")
            doc["descricao"] = description or doc["tipo"]
            filename = prefix + "_dados.html"
            atomic_write(folder / filename, html_page("Dados do documento", '<div class="eyebrow">Dados do documento • SIPAC UFBA</div>' + field_table(metadata)))
            doc["arquivo_dados"] = "documentos/" + filename
            # Inclui anexos adicionais apresentados na página de dados, se houver.
            known_urls = {a["url"] for a in doc["acoes"]}
            for anchor in root.xpath("//a"):
                extra_url = action_url(anchor, response.url)
                if extra_url and extra_url not in known_urls and any(path in extra_url for path in ("verArquivoDocumento", "documento_visualizacao.jsf")):
                    doc["acoes"].append({"url": extra_url, "variante": "anexo_adicional"})
                    known_urls.add(extra_url)
        except Exception as exc:
            doc["avisos"].append("Dados complementares: " + str(exc))
    if not doc["acoes"]:
        doc["status"] = "restrito" if any(t in fold(doc["natureza"]) for t in ("restrit", "sigilos")) else "indisponivel"
        doc["erros"].append("Nenhum link de conteúdo acessível na consulta pública.")
        return doc
    for idx, action in enumerate(doc["acoes"], 1):
        if any(saved["fonte"] == action["url"] for saved in doc["arquivos"]):
            continue
        try:
            response = client.request(action["url"])
            extension, mime = file_extension(response)
            output = response.body
            if extension == ".html":
                root = require_content(response)
                visible = fold(text(root))
                if "assinado eletronicamente" not in visible or "processo associado" not in visible:
                    raise SipacError("A resposta não foi reconhecida como documento eletrônico do SIPAC.")
                output = html_page(doc["tipo"], '<p class="muted">Cópia local da consulta pública • SIPAC UFBA</p>' + safe_fragment(root)).encode("utf-8")
            filename = f"{prefix}_{action['variante']}_{idx}{extension}"
            atomic_write(folder / filename, output)
            doc["arquivos"].append({"caminho": "documentos/" + filename, "variante": action["variante"],
                                     "formato": extension.lstrip("."), "bytes": len(output),
                                     "sha256": hashlib.sha256(output).hexdigest(), "fonte": action["url"]})
        except Exception as exc:
            doc["erros"].append(f"{action['variante']}: {exc}")
        time.sleep(0.2)
    doc["status"] = "baixado" if len(doc["arquivos"]) == len(doc["acoes"]) and not doc["erros"] else ("parcial" if doc["arquivos"] else "erro")
    return doc


def render_report(record, folder):
    docs = record["documentos"]
    complete = sum(d["status"] == "baixado" for d in docs)
    warnings = record["avisos"] + [f"Documento {d['ordem']}: {w}" for d in docs for w in d["avisos"]]
    for d in docs:
        warnings += [f"Documento {d['ordem']}: {w}" for w in d["erros"]]
    body = '<div class="eyebrow">Acervo local • SIPAC UFBA</div>'
    body += f'<h1>Processo {escape(record["processo"])}</h1>'
    body += f'<p class="muted">Consulta em {escape(record["consultado_em"])} • <a href="{escape(record["fonte"], quote=True)}">Consultar no SIPAC</a></p>'
    body += f'<div class="note"><b>{complete} de {len(docs)} documentos listados com todas as versões acessíveis salvas.</b><br>Escopo: consulta pública. Documentos ocultos ou restritos não são recuperados por esta versão. Anexos originais e versões com assinaturas estão identificados separadamente.</div>'
    body += '<h2>Cabeçalho do processo</h2>' + field_table(record["cabecalho"])
    for title, data in (("Interessados", record["interessados"]),):
        if data["linhas"]:
            body += f"<h2>{title}</h2>" + render_grid(data)
    body += '<h2>Documentos e despachos</h2><p class="muted">As descrições reproduzem os dados cadastrados no SIPAC. Os links abaixo abrem arquivos desta pasta.</p>'
    body += '<div class="scroll"><table><thead><tr><th>Ordem</th><th>Documento e descrição</th><th>Data / origem</th><th>Arquivos locais</th><th>Resultado</th></tr></thead><tbody>'
    for d in docs:
        links = []
        for f in d["arquivos"]:
            label = {"original": "Original", "com_assinaturas": "Com assinaturas", "anexo_adicional": "Anexo adicional"}[f["variante"]]
            links.append(f'<a href="{quote(f["caminho"], safe="/")}">{label} · {f["formato"].upper()}</a>')
        if d.get("arquivo_dados"):
            links.append(f'<a href="{quote(d["arquivo_dados"], safe="/")}">Dados do documento</a>')
        description = escape(d["descricao"])
        if d["descricao"] != d["tipo"]:
            description = f'<b>{escape(d["tipo"])}</b><br>{description}'
        details = "<br>".join(escape(x) for x in d["erros"])
        result = "Salvo" if d["status"] == "baixado" else d["status"].capitalize()
        body += f'<tr><td>{d["ordem"]:03d}</td><td>{description}</td><td>{escape(d["data"])}<br><span class="muted">{escape(d["origem"])}</span></td><td class="links">{"".join(links) or "—"}</td><td><span class="{"badge" if d["status"] == "baixado" else "warning"}">{result}</span><br><span class="muted">{details}</span></td></tr>'
    body += '</tbody></table></div>'
    if record["movimentacoes"]["linhas"]:
        body += '<h2>Movimentações do processo</h2>' + render_grid(record["movimentacoes"])
    if warnings:
        body += '<h2>Pendências e observações</h2><ul>' + ''.join(f'<li>{escape(x)}</li>' for x in warnings) + '</ul>'
    body += '<footer>Mantenha este índice e a pasta documentos juntos para preservar os links. Os PDFs recebidos do SIPAC foram salvos sem alteração. Documentos eletrônicos apresentados em HTML têm uma cópia local passiva do conteúdo.</footer>'
    atomic_write(folder / "indice.html", html_page("Processo " + record["processo"], body))
    atomic_write(folder / "processo.json", json.dumps(record, ensure_ascii=False, indent=2))
    with (folder / "documentos.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out, delimiter=";")
        writer.writerow(["Ordem", "Tipo", "Descrição", "Data", "Origem", "Natureza", "Resultado", "Arquivos", "Pendências"])
        for d in docs:
            values = [d["ordem"], d["tipo"], d["descricao"], d["data"], d["origem"], d["natureza"], d["status"], " | ".join(x["caminho"] for x in d["arquivos"]), " | ".join(d["erros"] + d["avisos"])]
            # Evita interpretar descrições do portal como fórmulas em planilhas.
            writer.writerow([("'" + v) if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for v in values])


def render_grid(data):
    header = "".join(f"<th>{escape(v)}</th>" for v in data["colunas"])
    rows = "".join("<tr>" + "".join(f"<td>{escape(v)}</td>" for v in row) + "</tr>" for row in data["linhas"])
    return f'<div class="scroll"><table><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table></div>'


def export_process(number, destination, progress=None, workers=3, timeout=45):
    number = normalize_number(number)
    notify = progress or (lambda message, done, total: None)
    notify("Consultando o número no SIPAC…", 0, 0)
    client = Client(timeout)
    response = client.search(number)
    root = require_content(response)
    header = fields(root)
    if header.get("Processo") != number:
        raise SipacError("O número no cabeçalho não corresponde ao solicitado. Operação interrompida.")
    docs = []
    fingerprints = set()
    for _ in range(200):
        page_docs = parse_documents(response)
        fingerprint = tuple((d["ordem"], d["id"]) for d in page_docs)
        if fingerprint in fingerprints:
            raise SipacError("O paginador repetiu uma página; não foi possível verificar a lista completa.")
        fingerprints.add(fingerprint)
        docs.extend(page_docs)
        action = next_page(response)
        if action is None:
            break
        response = client.follow(action, response)
    else:
        raise SipacError("Limite de paginação atingido. A lista precisa de conferência.")
    if not docs:
        raise SipacError("O processo não apresenta documentos nesta consulta pública.")
    if len({d["ordem"] for d in docs}) != len(docs):
        raise SipacError("Numeração duplicada na paginação. A lista precisa de conferência.")
    now = datetime.now(ZoneInfo("America/Bahia"))
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M%S_%f")
    folder = destination / (slug(number) + "_" + stamp)
    folder.mkdir(exist_ok=False)
    (folder / "documentos").mkdir()
    record = {"versao": "1.0", "processo": number, "consultado_em": now.isoformat(timespec="seconds"),
              "fonte": response.url, "escopo": "consulta_publica", "cabecalho": header,
              "interessados": tabular(root, "Interessados Deste Processo"),
              "movimentacoes": tabular(root, "Movimentações do Processo"), "avisos": [], "documentos": [],
              "total_listado": len(docs), "inventario_listado": [{k: d[k] for k in ("ordem", "id", "tipo", "data", "natureza")} for d in docs]}
    # Uma pasta por consulta: reexecuções nunca sobrescrevem cópias anteriores.
    # Checkpoints permitem conservar os arquivos já obtidos em uma interrupção.
    atomic_write(folder / "processo.json", json.dumps(record, ensure_ascii=False, indent=2))
    notify(f"{len(docs)} documentos encontrados. Baixando…", 0, len(docs))
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 3))) as pool:
        futures = {pool.submit(download_document, d, folder / "documentos", timeout): d for d in docs}
        for future in as_completed(futures):
            doc = future.result()
            with lock:
                record["documentos"].append(doc)
                record["documentos"].sort(key=lambda x: x["ordem"])
                atomic_write(folder / "processo.json", json.dumps(record, ensure_ascii=False, indent=2))
            notify(f"Documento {doc['ordem']:03d}: {doc['tipo']} — {doc['status']}", len(record["documentos"]), len(docs))
    retry = [d for d in record["documentos"] if d["acoes"] and (d["erros"] or any(w.startswith("Dados complementares:") for w in d["avisos"]))]
    if retry:
        notify(f"Conferindo {len(retry)} documento(s) com pendências e tentando novamente os itens ausentes…", len(docs), len(docs))
        for doc in retry:
            download_document(doc, folder / "documentos", timeout)
            atomic_write(folder / "processo.json", json.dumps(record, ensure_ascii=False, indent=2))
    record["total_listado"] = len(docs)
    record["total_salvo"] = sum(d["status"] == "baixado" for d in record["documentos"])
    record["total_arquivos"] = sum(len(d["arquivos"]) for d in record["documentos"])
    record["pendencias"] = sum(bool(d["erros"] or d["avisos"]) for d in record["documentos"])
    record["concluido_em"] = datetime.now(ZoneInfo("America/Bahia")).isoformat(timespec="seconds")
    render_report(record, folder)
    notify("Índice e arquivos salvos.", len(docs), len(docs))
    return folder, record
