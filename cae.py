"""Preenchimento inicial, revisável, da planilha de controle do CAE."""
import re
import unicodedata
from datetime import datetime
from html import escape

CONTROL_FIELDS = ["Processo", "Nível", "Unidade de Origem", "Título", "Relator", "Tipo",
                  "Sugestão de prazo", "Data Abertura", "Data Recebimento", "Data Distribuição",
                  "Data Parecer", "Dias até Parecer", "Data Apreciação", "Situação", "Parecer", "Final", "OBS"]


def clean(value):
    return " ".join(str(value or "").split())


def fold(value):
    return "".join(c for c in unicodedata.normalize("NFD", clean(value).lower()) if not unicodedata.combining(c))


def date_only(value):
    match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", clean(value))
    if match:
        try:
            return datetime.strptime(match[1], "%d/%m/%Y").strftime("%d/%m/%Y")
        except ValueError:
            pass
    return ""


def short_number(value):
    match = re.fullmatch(r"23066\.(\d{6})/20(\d{2})-(\d{2})", value)
    return f"{match[1]}/{match[2]}-{match[3]}" if match else value


def build_control(record):
    values = dict.fromkeys(CONTROL_FIELDS, "A definir")
    sources = {}
    header = {fold(k): clean(v) for k, v in record.get("cabecalho", {}).items()}

    def get(*keys):
        return next(((header[fold(k)], k) for k in keys if header.get(fold(k))), ("", ""))

    values["Processo"] = short_number(record["processo"])
    sources["Processo"] = "Número consultado; forma reduzida da UFBA."
    title, source = get("Assunto Detalhado", "Título", "Assunto do Processo", "Assunto")
    if title:
        values["Título"] = title
        sources["Título"] = "Cabeçalho: " + source
    unit, source = get("Unidade de Origem", "Unidade Origem")
    if unit:
        name = re.sub(r"\s*\([\d.]+\)\s*$", "", unit)
        values["Unidade de Origem"] = "FMB - Faculdade de Medicina" if fold(name) in ("faculdade de medicina", "faculdade de medicina da bahia", "fmb") or re.search(r"/fmb\b", fold(name)) else unit
        sources["Unidade de Origem"] = "Unidade de origem agrupada como FMB a partir de: " + unit if values["Unidade de Origem"] != unit else "Cabeçalho: " + source
    text = fold(" ".join([title, get("Assunto do Processo", "Assunto")[0]]))
    if re.search(r"\bpos\b|mestrado|doutorado|especializa|residencia", text):
        values["Nível"] = "PÓS"
    elif "graduacao" in text:
        values["Nível"] = "GRAD"
    if "criacao" in text and re.search(r"curso|programa|residencia", text):
        values["Tipo"] = "Criação de curso"
    elif re.search(r"alteracao curricular|reformulacao curricular|reforma curricular", text):
        values["Tipo"] = "Alteração curricular"
    for field in ("Nível", "Tipo"):
        if values[field] != "A definir":
            sources[field] = "Sugestão por palavras do assunto; conferir antes de colar."
    for key in ("Data de Abertura", "Data Abertura", "Data de Autuação", "Data de Cadastro"):
        date = date_only(header.get(fold(key), ""))
        if date:
            values["Data Abertura"] = date
            sources["Data Abertura"] = "Cabeçalho: " + key
            break
    movements = record.get("movimentacoes", {})
    columns = [fold(c) for c in movements.get("colunas", [])]
    destination = next((i for i, c in enumerate(columns) if c in ("unidade destino", "unidade de destino", "destino")), None)
    received = next((i for i, c in enumerate(columns) if c in ("recebido em", "data de recebimento", "data recebimento")), None)
    dates = []
    if destination is not None and received is not None:
        for row in movements.get("linhas", []):
            if max(destination, received) >= len(row):
                continue
            target = fold(row[destination])
            if re.search(r"\bcae\b", target) or "conselho academico de ensino" in target:
                date = date_only(row[received])
                if date:
                    dates.append(date)
    if dates:
        values["Data Recebimento"] = max(dates, key=lambda v: datetime.strptime(v, "%d/%m/%Y"))
        sources["Data Recebimento"] = "Recebimento mais recente em tramitação com destino ao CAE."
    values["Sugestão de prazo"] = "30"
    sources["Sugestão de prazo"] = "Valor inicial informado pelo usuário, em dias; ajustar ao caso."
    values["Situação"] = "Em análise"
    sources["Situação"] = "Valor inicial do controle; não é o status do SIPAC."
    return {"colunas": CONTROL_FIELDS.copy(), "valores": [values[k] for k in CONTROL_FIELDS], "fontes": sources}


def tsv_cell(value):
    value = clean(value)
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value


def control_tsv(control, header=False):
    line = "\t".join(tsv_cell(v) for v in control["valores"])
    return "\t".join(control["colunas"]) + "\r\n" + line if header else line


def render_control(control):
    rows = "".join('<tr><th><label data-cae-label for="cae-'+str(i)+'">'+escape(label)+'</label></th><td><input id="cae-'+str(i)+'" data-cae-value value="'+escape(str(value), quote=True)+'" aria-label="'+escape(label, quote=True)+'"></td></tr>' for i, (label, value) in enumerate(zip(control["colunas"], control["valores"])))
    sources = "".join('<li><b>'+escape(k)+':</b> '+escape(v)+'</li>' for k, v in control["fontes"].items())
    return '<section data-cae class="cae-control"><style>.cae-control{margin:24px 0;padding:18px;border:1px solid #cbdcd5;border-radius:10px;background:#f5faf7}.cae-control h2{margin:0 0 8px;font-size:19px}.cae-control p{font-size:13px}.cae-control table{width:100%;border-collapse:collapse}.cae-control th{width:36%;text-align:left}.cae-control th,.cae-control td{padding:7px;border-bottom:1px solid #dce4e6}.cae-control input{box-sizing:border-box;width:100%;min-width:140px;padding:8px;border:1px solid #b6cac3;border-radius:5px;font:13px Arial,sans-serif;background:white;color:#203649}.cae-scroll{max-height:320px;overflow:auto}.cae-actions{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.cae-control button{cursor:pointer;border:0;border-radius:6px;padding:10px 12px;background:#147b68;color:white;font:700 13px Arial,sans-serif}.cae-control textarea{box-sizing:border-box;width:100%;min-height:80px}.cae-control details{margin:12px 0;font:13px/1.5 Arial,sans-serif}.cae-control [hidden]{display:none!important}</style><h2>Planilha de controle CAE</h2><p>17 colunas na ordem da sua planilha. Revise os dados sugeridos. Campos sem evidência e campos de acompanhamento começam como “A definir”. O prazo inicial é de 30 dias.</p><details><summary>Revisar os 17 campos</summary><div class="cae-scroll"><table>'+rows+'</table></div></details><div class="cae-actions"><button type="button" data-cae-copy>Copiar linha para planilha</button><button type="button" data-cae-headers>Copiar cabeçalhos</button></div><p data-cae-status role="status">Cole na primeira coluna de uma linha vazia da planilha.</p><textarea data-cae-fallback aria-label="Texto para copiar para a planilha" readonly hidden></textarea><details><summary>Como os campos foram preenchidos</summary><ul>'+sources+'</ul><p>A revisão altera a linha copiada nesta página. O arquivo controle-cae.tsv guarda o preenchimento inicial. Não são calculadas datas futuras nem dias até parecer.</p></details></section>'
