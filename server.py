import http.server
import socketserver
import json
import socket
import os
import re

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MD_FILE = os.path.join(BASE_DIR, "ASSISTENTE_PESSOAL.md")
HTML_FILE = os.path.join(BASE_DIR, "painel.html")
SQL_FILE = os.path.join(BASE_DIR, "sync_db.sql")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class AssistantHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean_path = path.split('?', 1)[0].split('#', 1)[0]
        if clean_path in ('/', '/painel', '/index.html'):
            return HTML_FILE
        return os.path.join(BASE_DIR, clean_path.lstrip('/'))

    def do_POST(self):
        if self.path == '/api/tarefa/status':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                codigo = data.get('codigo', '').strip()
                novo_status = data.get('status', '').strip()

                if not codigo or not novo_status:
                    self._send_json({"error": "Parâmetros inválidos"}, 400)
                    return

                self._update_task_in_files(codigo, novo_status)
                self._send_json({"success": True, "codigo": codigo, "status": novo_status})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "Rota não encontrada"}, 404)

    def _update_task_in_files(self, codigo, status):
        sql_statement = f"\nUPDATE dbo.TB_TAREFAS SET STATUS = '{status}' WHERE CODIGO = '{codigo}';\n"
        sql_statement += f"INSERT INTO dbo.TB_HISTORICO (CODIGO_TAREFA, DESCRICAO) VALUES ('{codigo}', 'Atualizado via celular para: {status}');\n"
        try:
            with open(SQL_FILE, 'a', encoding='utf-8') as f:
                f.write(sql_statement)
        except Exception:
            pass

        if os.path.exists(MD_FILE):
            try:
                with open(MD_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()

                pattern = rf"(\| \*\*{re.escape(codigo)}\*\* \| [^\|]+ \| [^\|]+ \| [^\|]+ \| )([^\|]+)( \|)"
                content = re.sub(pattern, rf"\g<1>{status}\g<3>", content)

                with open(MD_FILE, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception:
                pass

    def _send_json(self, data, status=200):
        response = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(response)

if __name__ == "__main__":
    local_ip = get_local_ip()
    hostname = socket.gethostname()
    host_clean = hostname.lower()
    print("=" * 65)
    print("       🤖 SERVIDOR DO ASSISTENTE PESSOAL INICIADO")
    print("=" * 65)
    print("\nPara acessar pelo seu celular (FIXO - não muda com o IP do Wi-Fi):")
    print(f"\n👉 OPÇÃO 1 (Recomendada): http://{host_clean}.local:{PORT}")
    print(f"👉 OPÇÃO 2 (Nome de rede): http://{host_clean}:{PORT}")
    print(f"👉 OPÇÃO 3 (IP atual):     http://{local_ip}:{PORT}")
    print(f"👉 NO NOTEBOOK:            http://localhost:{PORT}\n")
    print("=" * 65)
    print("Dica: Salve 'http://" + host_clean + ".local:" + str(PORT) + "' nos favoritos do celular!")
    print("Pressione Ctrl+C para encerrar o servidor.")
    print("=" * 65)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), AssistantHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor encerrado.")
