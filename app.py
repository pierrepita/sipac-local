"""Interface web local e modo linha de comando do SIPAC Local."""
from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sipac import SipacError, export_process, normalize_number

HERE = Path(__file__).resolve().parent


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)
        self.folder = None
        self.data = {"status": "pronto", "mensagem": "Pronto para consultar.", "atual": 0, "total": 0,
                     "destino_padrao": str(Path.home() / "Documentos" / "SIPAC"), "eventos": []}

    def snapshot(self):
        with self.lock:
            return dict(self.data)

    def progress(self, message, done, total):
        with self.lock:
            self.data.update(mensagem=message, atual=done, total=total)
            self.data["eventos"] = (self.data["eventos"] + [message])[-60:]
        print(message, flush=True)

    def run(self, number, destination):
        try:
            folder, record = export_process(number, destination, self.progress)
            with self.lock:
                self.folder = folder
                self.data.update(status="concluido", pasta=str(folder), salvos=record["total_salvo"],
                                 arquivos=record["total_arquivos"], pendencias=record["pendencias"],
                                 indice="/acervo/indice.html", mensagem="Consulta concluída. Os arquivos estão no seu computador.")
        except Exception as exc:
            print(f"Falha: {exc}", file=sys.stderr, flush=True)
            with self.lock:
                self.data.update(status="erro", mensagem=str(exc))


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Evita imprimir URLs de documentos e dados de processo no log HTTP.
            pass

        def allowed_host(self):
            host = self.headers.get("Host", "").lower()
            return host in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def reply(self, body, mime="application/json; charset=utf-8", status=200, attachment=False):
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if attachment:
                self.send_header("Content-Disposition", "attachment")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if not self.allowed_host():
                return self.reply({"erro": "Host não permitido."}, status=403)
            path = urlsplit(self.path).path
            if path == "/":
                content = (HERE / "web" / "index.html").read_text(encoding="utf-8").replace("__LOCAL_TOKEN__", state.token)
                return self.reply(content, "text/html; charset=utf-8")
            if path in ("/app.js", "/style.css"):
                file = HERE / "web" / path[1:]
                return self.reply(file.read_bytes(), "text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8")
            if path == "/api/estado":
                if not hmac.compare_digest(self.headers.get("X-Local-Token", ""), state.token):
                    return self.reply({"erro": "Token local inválido."}, status=403)
                return self.reply(state.snapshot())
            if path.startswith("/acervo/"):
                with state.lock:
                    folder = state.folder
                if folder is None:
                    return self.reply({"erro": "Nenhum acervo concluído nesta sessão."}, status=404)
                file = (folder / unquote(path.removeprefix("/acervo/"))).resolve()
                if not file.is_relative_to(folder.resolve()) or not file.is_file():
                    return self.reply({"erro": "Arquivo não encontrado."}, status=404)
                mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                return self.reply(file.read_bytes(), mime, attachment=file.suffix.lower() not in (".html", ".pdf", ".png", ".jpg", ".jpeg", ".txt"))
            return self.reply({"erro": "Página não encontrada."}, status=404)

        def do_POST(self):
            if not self.allowed_host() or not hmac.compare_digest(self.headers.get("X-Local-Token", ""), state.token):
                return self.reply({"erro": "Requisição local não autorizada."}, status=403)
            expected_origins = {f"http://localhost:{self.server.server_port}", f"http://127.0.0.1:{self.server.server_port}"}
            if self.headers.get("Origin") not in expected_origins | {None}:
                return self.reply({"erro": "Origem não permitida."}, status=403)
            path = urlsplit(self.path).path
            if path == "/api/pasta":
                try:
                    code = "import tkinter as t; from tkinter import filedialog; r=t.Tk(); r.withdraw(); r.attributes('-topmost', True); print(filedialog.askdirectory(title='Escolha onde salvar os processos')); r.destroy()"
                    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
                    if result.returncode:
                        raise RuntimeError("Seletor indisponível. Digite o caminho da pasta.")
                    return self.reply({"pasta": result.stdout.strip()})
                except Exception:
                    return self.reply({"erro": "Seletor de pastas indisponível. Digite o caminho da pasta de destino."}, status=400)
            if path != "/api/consultar":
                return self.reply({"erro": "Ação não encontrada."}, status=404)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise SipacError("Requisição inválida.")
                data = json.loads(self.rfile.read(size))
                number = normalize_number(str(data.get("processo", "")))
                destination = str(data.get("destino", "")).strip()
                if not destination:
                    raise SipacError("Escolha a pasta de destino.")
                target = Path(destination).expanduser()
                if not target.is_absolute():
                    raise SipacError("Informe o caminho completo da pasta de destino.")
            except (SipacError, ValueError, TypeError, AttributeError) as exc:
                return self.reply({"erro": str(exc)}, status=400)
            with state.lock:
                if state.data["status"] == "executando":
                    return self.reply({"erro": "Já existe uma consulta em andamento."}, status=409)
                state.folder = None
                state.data = {"status": "executando", "mensagem": "Iniciando consulta…", "atual": 0, "total": 0,
                              "processo": number, "destino_padrao": destination, "eventos": []}
            threading.Thread(target=state.run, args=(number, destination), daemon=True).start()
            return self.reply({"ok": True}, status=202)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="SIPAC Local — cópia organizada de processos públicos da UFBA")
    parser.add_argument("--processo", help="Executa pelo terminal, sem abrir a interface")
    parser.add_argument("--destino", default=str(Path.home() / "Documentos" / "SIPAC"))
    parser.add_argument("--porta", type=int, default=8765)
    parser.add_argument("--sem-navegador", action="store_true")
    args = parser.parse_args()
    if args.processo:
        try:
            folder, record = export_process(args.processo, args.destino, lambda message, *_: print(message, flush=True))
            print(f"\nÍndice: {folder / 'indice.html'}")
            print(f"Documentos salvos: {record['total_salvo']}/{record['total_listado']}; pendências: {record['pendencias']}")
            return 2 if record["pendencias"] else 0
        except (SipacError, OSError) as exc:
            print(f"Erro: {exc}", file=sys.stderr)
            return 1
    state = State()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.porta), make_handler(state))
    except OSError:
        print(f"A porta {args.porta} está ocupada. Tente: python app.py --porta 8766", file=sys.stderr)
        return 1
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"SIPAC Local aberto em {address}\nMantenha este terminal aberto. Para encerrar: Ctrl+C.", flush=True)
    if not args.sem_navegador:
        threading.Timer(0.5, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
