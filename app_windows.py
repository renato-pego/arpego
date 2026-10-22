"""
=============================================================================
Assistente Pessoal - ARPego (Base Forte Windows Desktop)
Operação Stand Alone Gráfica com SQL Server Local (ASSISTPE) e Sincronização
=============================================================================
"""

import sys
import os
import json
import time
import argparse
import subprocess
import webbrowser
import threading
import http.server
import socketserver
import urllib.request
import urllib.error
import sqlite3
import re
from datetime import datetime, timezone, timedelta, date

# Fuso Horário de Brasília (UTC-3) conforme diretriz global do projeto
TZ_BR = timezone(timedelta(hours=-3))

def get_now_br():
    """Retorna datetime no fuso de Brasília (UTC-3)."""
    return datetime.now(timezone.utc).astimezone(TZ_BR).replace(tzinfo=None)

def normalize_dt(val):
    """Converte valores de data/hora (string ou datetime) para objeto datetime seguro contra erro 22007 do SQL Server."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    s = str(val).strip()
    if not s or s.lower() in ('none', 'null', 'nan'):
        return None
    s = s.replace('T', ' ')
    if '.' in s:
        s = s.split('.')[0]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

# Diretórios e Configurações
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP_HTML_FILE = os.path.join(BASE_DIR, "painel_desktop.html")
SQLITE_FALLBACK_FILE = os.path.join(BASE_DIR, "assistpe_desktop.db")

DEFAULT_SQL_SERVER = os.environ.get("ARPEGO_SQL_SERVER", "localhost")
DEFAULT_SQL_DB = os.environ.get("ARPEGO_SQL_DB", "ASSISTPE")
DEFAULT_SQL_USER = os.environ.get("ARPEGO_SQL_USER", "ASSISTPE")
DEFAULT_SQL_PASS = os.environ.get("ARPEGO_SQL_PASS", "ASSISTPE")
CLOUD_URL = os.environ.get("ARPEGO_CLOUD_URL", "https://arpego-9p4x.onrender.com")

DESKTOP_PORT = 5050
LAST_HEARTBEAT = time.time()

CACHED_CONN_STR = None

# ==================== CONEXÃO SQL SERVER & FALLBACK STAND ALONE ====================
def get_db_connection():
    """
    Tenta conectar ao SQL Server local (ASSISTPE) usando múltiplas estratégias e drivers.
    Retorna o objeto de conexão do pyodbc se bem-sucedido, ou None caso indisponível.
    """
    global CACHED_CONN_STR
    try:
        import pyodbc
    except ImportError:
        log_event("[SQL] pyodbc não encontrado no Python. Tentando instalar pyodbc silenciosamente via pip...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyodbc", "--quiet"], check=False, timeout=30)
            import pyodbc
            log_event("[SQL] pyodbc instalado com sucesso!")
        except Exception as err:
            log_event(f"[SQL] Falha ao instalar pyodbc: {err}")
            return None

    # Se já temos uma string de conexão validada anteriormente, tenta ela primeiro
    if CACHED_CONN_STR:
        try:
            conn = pyodbc.connect(CACHED_CONN_STR, timeout=4)
            try:
                conn.cursor().execute("SET DATEFORMAT ymd;")
            except Exception:
                pass
            return conn
        except Exception:
            CACHED_CONN_STR = None

    installed_drivers = pyodbc.drivers()
    log_event(f"[SQL] Drivers ODBC detectados: {installed_drivers}")

    preferred_drivers = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 13 for SQL Server",
        "ODBC Driver 11 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server"
    ]
    
    test_drivers = [d for d in preferred_drivers if d in installed_drivers]
    for d in installed_drivers:
        if d not in test_drivers and "SQL Server" in d:
            test_drivers.append(d)

    if not test_drivers:
        log_event("[SQL] Nenhum driver ODBC de SQL Server encontrado no Windows!")
        return None

    servers = [DEFAULT_SQL_SERVER, "localhost", ".", "127.0.0.1", "(local)", r"localhost\SQLEXPRESS", r".\SQLEXPRESS"]
    unique_servers = list(dict.fromkeys(servers))

    for driver in test_drivers:
        for server in unique_servers:
            # 1. Tenta autenticação SQL padrão (ASSISTPE/ASSISTPE)
            base_conn = f"DRIVER={{{driver}}};SERVER={server};DATABASE={DEFAULT_SQL_DB};UID={DEFAULT_SQL_USER};PWD={DEFAULT_SQL_PASS};"
            if "18" in driver:
                conn_str = base_conn + "Encrypt=no;TrustServerCertificate=yes;"
            elif driver == "SQL Server":
                conn_str = base_conn
            else:
                conn_str = base_conn + "TrustServerCertificate=yes;"

            try:
                conn = pyodbc.connect(conn_str, timeout=4)
                try:
                    conn.cursor().execute("SET DATEFORMAT ymd;")
                except Exception:
                    pass
                log_event(f"[SQL] Conectado com sucesso ao SQL Server! (Driver: '{driver}' | Servidor: '{server}')")
                CACHED_CONN_STR = conn_str
                return conn
            except Exception as e:
                log_event(f"[SQL Tentativa] Falha com driver '{driver}' em '{server}': {e}")

            # 2. Se falhar, tenta Trusted_Connection (Autenticação Windows)
            win_base = f"DRIVER={{{driver}}};SERVER={server};DATABASE={DEFAULT_SQL_DB};Trusted_Connection=yes;"
            if "18" in driver:
                conn_str_win = win_base + "Encrypt=no;TrustServerCertificate=yes;"
            elif driver == "SQL Server":
                conn_str_win = win_base
            else:
                conn_str_win = win_base + "TrustServerCertificate=yes;"

            try:
                conn = pyodbc.connect(conn_str_win, timeout=3)
                try:
                    conn.cursor().execute("SET DATEFORMAT ymd;")
                except Exception:
                    pass
                log_event(f"[SQL] Conectado via Autenticação Windows! (Driver: '{driver}' | Servidor: '{server}')")
                CACHED_CONN_STR = conn_str_win
                return conn
            except Exception as e:
                pass

    log_event("[SQL] Todas as tentativas de conexão com o SQL Server local falharam.")
    return None

def init_sqlserver_tables(conn):
    """Garante a estrutura das tabelas no SQL Server."""
    cur = conn.cursor()
    
    cur.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_projetos')
    BEGIN
        CREATE TABLE tb_projetos (
            id INT IDENTITY(1,1) PRIMARY KEY,
            nome NVARCHAR(150) NOT NULL,
            sigla NVARCHAR(20),
            tipo NVARCHAR(50) DEFAULT 'Profissional'
        );
    END
    """)

    cur.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_tarefas')
    BEGIN
        CREATE TABLE tb_tarefas (
            id INT IDENTITY(1,1) PRIMARY KEY,
            codigo NVARCHAR(20) NOT NULL UNIQUE,
            id_projeto INT NULL,
            titulo NVARCHAR(255) NOT NULL,
            tipo NVARCHAR(50) DEFAULT 'Profissional',
            prioridade NVARCHAR(50) DEFAULT 'Média',
            status NVARCHAR(50) DEFAULT 'Não iniciada',
            observacoes NVARCHAR(MAX) NULL,
            data_conclusao NVARCHAR(50) NULL,
            recorrencia_dias INT DEFAULT 0,
            data_recorrencia NVARCHAR(50) NULL,
            sync_pendente BIT DEFAULT 0,
            ultima_atualizacao DATETIME DEFAULT GETDATE(),
            CONSTRAINT FK_tb_tarefas_projetos FOREIGN KEY (id_projeto) REFERENCES tb_projetos(id)
        );
    END
    ELSE
    BEGIN
        IF COL_LENGTH('tb_tarefas', 'ultima_atualizacao') IS NULL
            ALTER TABLE tb_tarefas ADD ultima_atualizacao DATETIME DEFAULT GETDATE();
        IF COL_LENGTH('tb_tarefas', 'sync_pendente') IS NULL
            ALTER TABLE tb_tarefas ADD sync_pendente BIT DEFAULT 0;
    END
    """)

    cur.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_status')
    BEGIN
        CREATE TABLE tb_status (
            id INT IDENTITY(1,1) PRIMARY KEY,
            nome NVARCHAR(50) NOT NULL UNIQUE,
            cor NVARCHAR(20) NOT NULL,
            borda NVARCHAR(20) NOT NULL,
            bg NVARCHAR(20) NOT NULL,
            ordem INT DEFAULT 0,
            ativo BIT DEFAULT 1
        );

        INSERT INTO tb_status (nome, cor, borda, bg, ordem) VALUES
        ('Não iniciada', '#cbd5e1', '#475569', '#1e293b', 1),
        ('Em andamento', '#38bdf8', '#0284c7', '#0369a130', 2),
        ('Aguardando retorno', '#facc15', '#eab308', '#854d0e30', 3),
        ('Pendente', '#facc15', '#eab308', '#854d0e30', 4),
        ('Em testes', '#4ade80', '#22c55e', '#065f4630', 5),
        ('Concluída', '#94a3b8', '#64748b', '#1e293b', 6);
    END
    """)

    cur.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_prioridades')
    BEGIN
        CREATE TABLE tb_prioridades (
            id INT IDENTITY(1,1) PRIMARY KEY,
            nome NVARCHAR(50) NOT NULL UNIQUE,
            cor NVARCHAR(20) NOT NULL,
            borda NVARCHAR(20) NOT NULL,
            bg NVARCHAR(20) NOT NULL,
            ordem INT DEFAULT 0,
            ativo BIT DEFAULT 1
        );

        INSERT INTO tb_prioridades (nome, cor, borda, bg, ordem) VALUES
        ('Alta', '#f87171', '#ef444450', '#ef444420', 1),
        ('Média', '#fbbf24', '#f59e0b50', '#f59e0b20', 2),
        ('Baixa', '#60a5fa', '#3b82f650', '#3b82f620', 3);
    END
    """)

    cur.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_historico')
    BEGIN
        CREATE TABLE tb_historico (
            id INT IDENTITY(1,1) PRIMARY KEY,
            codigo_tarefa NVARCHAR(20) NULL,
            descricao NVARCHAR(MAX) NOT NULL,
            data_hora DATETIME DEFAULT GETDATE()
        );
    END
    """)

    cur.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_sync_log')
    BEGIN
        CREATE TABLE tb_sync_log (
            id INT IDENTITY(1,1) PRIMARY KEY,
            data_hora DATETIME DEFAULT GETDATE(),
            direcao NVARCHAR(20) NOT NULL,
            itens_enviados INT DEFAULT 0,
            itens_recebidos INT DEFAULT 0,
            status NVARCHAR(50) NOT NULL,
            mensagem NVARCHAR(MAX) NULL
        );
    END
    """)

    conn.commit()

def init_sqlite_fallback():
    """Garante funcionamento 100% stand-alone mesmo sem SQL Server ativo."""
    conn = sqlite3.connect(SQLITE_FALLBACK_FILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_projetos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        sigla TEXT,
        tipo TEXT DEFAULT 'Profissional'
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_tarefas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL UNIQUE,
        id_projeto INTEGER,
        titulo TEXT NOT NULL,
        tipo TEXT DEFAULT 'Profissional',
        prioridade TEXT DEFAULT 'Média',
        status TEXT DEFAULT 'Não iniciada',
        observacoes TEXT,
        data_conclusao TEXT,
        recorrencia_dias INTEGER DEFAULT 0,
        data_recorrencia TEXT,
        sync_pendente INTEGER DEFAULT 0,
        ultima_atualizacao TEXT
    );
    """)
    cur.execute("PRAGMA table_info(tb_tarefas);")
    cols_fb = [r[1] for r in cur.fetchall()]
    if 'ultima_atualizacao' not in cols_fb:
        cur.execute("ALTER TABLE tb_tarefas ADD COLUMN ultima_atualizacao TEXT;")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE,
        cor TEXT NOT NULL,
        borda TEXT NOT NULL,
        bg TEXT NOT NULL,
        ordem INTEGER DEFAULT 0,
        ativo INTEGER DEFAULT 1
    );
    """)
    cur.execute("SELECT COUNT(*) FROM tb_status;")
    if cur.fetchone()[0] == 0:
        cur.executemany("INSERT INTO tb_status (nome, cor, borda, bg, ordem) VALUES (?, ?, ?, ?, ?);", [
            ('Não iniciada', '#cbd5e1', '#475569', '#1e293b', 1),
            ('Em andamento', '#38bdf8', '#0284c7', '#0369a130', 2),
            ('Aguardando retorno', '#facc15', '#eab308', '#854d0e30', 3),
            ('Pendente', '#facc15', '#eab308', '#854d0e30', 4),
            ('Em testes', '#4ade80', '#22c55e', '#065f4630', 5),
            ('Concluída', '#94a3b8', '#64748b', '#1e293b', 6)
        ])
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_prioridades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE,
        cor TEXT NOT NULL,
        borda TEXT NOT NULL,
        bg TEXT NOT NULL,
        ordem INTEGER DEFAULT 0,
        ativo INTEGER DEFAULT 1
    );
    """)
    cur.execute("SELECT COUNT(*) FROM tb_prioridades;")
    if cur.fetchone()[0] == 0:
        cur.executemany("INSERT INTO tb_prioridades (nome, cor, borda, bg, ordem) VALUES (?, ?, ?, ?, ?);", [
            ('Alta', '#f87171', '#ef444450', '#ef444420', 1),
            ('Média', '#fbbf24', '#f59e0b50', '#f59e0b20', 2),
            ('Baixa', '#60a5fa', '#3b82f650', '#3b82f620', 3)
        ])
    conn.commit()
    conn.close()

# ==================== MOTOR DE SINCRONIZAÇÃO COM A NUVEM ====================
def sync_with_cloud(verbose=False):
    """Executa a sincronização bidirecional entre a Base Forte Desktop e a Nuvem."""
    conn = get_db_connection()
    use_sql = True if conn else False
    if not conn:
        conn = sqlite3.connect(SQLITE_FALLBACK_FILE)

    try:
        if use_sql:
            init_sqlserver_tables(conn)
        else:
            init_sqlite_fallback()

        cur = conn.cursor()

        # Coleta todas as tarefas locais com carimbo de data/hora para reconciliação LWW
        if use_sql:
            cur.execute("""
            SELECT t.codigo, t.status, t.titulo, p.nome, t.tipo, t.prioridade, t.observacoes, t.recorrencia_dias,
                   t.data_conclusao, t.data_recorrencia,
                   CONVERT(VARCHAR(19), t.ultima_atualizacao, 120) AS ultima_atualizacao,
                   t.sync_pendente
            FROM tb_tarefas t
            LEFT JOIN tb_projetos p ON t.id_projeto = p.id;
            """)
        else:
            cur.execute("""
            SELECT t.codigo, t.status, t.titulo, p.nome, t.tipo, t.prioridade, t.observacoes, t.recorrencia_dias,
                   t.data_conclusao, t.data_recorrencia,
                   COALESCE(t.ultima_atualizacao, datetime('now')) AS ultima_atualizacao,
                   t.sync_pendente
            FROM tb_tarefas t
            LEFT JOIN tb_projetos p ON t.id_projeto = p.id;
            """)

        all_local_tarefas = []
        local_changes = []
        for r in cur.fetchall():
            item = {
                "codigo": r[0],
                "status": r[1],
                "titulo": r[2],
                "projeto": r[3] or "Geral",
                "tipo": r[4],
                "prioridade": r[5],
                "observacoes": r[6] or "",
                "recorrencia_dias": r[7] or 0,
                "data_conclusao": r[8],
                "data_recorrencia": r[9],
                "ultima_atualizacao": str(r[10]) if r[10] else ""
            }
            all_local_tarefas.append(item)
            if r[11] == 1:
                local_changes.append({"action": "editar", **item})

        # Coleta projetos locais para a Nuvem conhecer todos os projetos (ex: Carro)
        cur.execute("SELECT nome, tipo FROM tb_projetos;")
        local_projs = [{"nome": r[0], "tipo": r[1]} for r in cur.fetchall()]

        # Coleta domínios locais para sincronizar com a nuvem
        cur.execute("SELECT nome, cor, borda, bg, ordem FROM tb_status WHERE ativo = 1;")
        local_status = [{"nome": r[0], "cor": r[1], "borda": r[2], "bg": r[3], "ordem": r[4]} for r in cur.fetchall()]
        cur.execute("SELECT nome, cor, borda, bg, ordem FROM tb_prioridades WHERE ativo = 1;")
        local_prio = [{"nome": r[0], "cor": r[1], "borda": r[2], "bg": r[3], "ordem": r[4]} for r in cur.fetchall()]

        payload = {
            "client_id": "windows-desktop-baseforte",
            "tarefas": all_local_tarefas,
            "changes": local_changes,
            "projetos": local_projs,
            "dominios": {
                "status": local_status,
                "prioridades": local_prio
            }
        }

        # Despacha para Nuvem
        req_url = f"{CLOUD_URL.rstrip('/')}/api/sync"
        req_data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            req_url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ARPego-Windows-Desktop/2.0",
                "X-User-Id": "1"
            }
        )

        with urllib.request.urlopen(req, timeout=12) as resp:
            res_json = json.loads(resp.read().decode('utf-8'))

        if not res_json.get("success"):
            return False, res_json.get("error", "Erro ao sincronizar.")

        # Atualiza banco local com resposta da Nuvem
        tarefas_nuvem = res_json.get("tarefas", [])
        projetos_nuvem = res_json.get("projetos", [])

        for p in projetos_nuvem:
            p_nome = p.get("nome", "").strip()
            p_tipo = p.get("tipo", "Profissional").strip()
            if not p_nome: continue
            cur.execute("SELECT id FROM tb_projetos WHERE LOWER(nome) = LOWER(?);", (p_nome,))
            if not cur.fetchone():
                cur.execute("INSERT INTO tb_projetos (nome, sigla, tipo) VALUES (?, ?, ?);",
                            (p_nome, p_nome[:6].upper(), p_tipo))

        # Mapa de projetos
        cur.execute("SELECT id, LOWER(nome) FROM tb_projetos;")
        proj_map = {row[1]: row[0] for row in cur.fetchall()}

        now_str = get_now_br().strftime('%Y-%m-%d %H:%M:%S')

        for t in tarefas_nuvem:
            cod = t.get("codigo", "").strip()
            tit = t.get("titulo", "").strip()
            proj_nome = (t.get("projeto") or "Geral").strip().lower()
            tipo = t.get("tipo", "Profissional").strip()
            prio = t.get("prioridade", "Média").strip()
            st = t.get("status", "Não iniciada").strip()
            obs = t.get("observacoes", "")
            rec_d = int(t.get("recorrencia_dias", 0))
            d_conc = t.get("data_conclusao")
            d_rec = t.get("data_recorrencia")
            cloud_ts = (t.get("ultima_atualizacao") or "").strip()

            proj_id = proj_map.get(proj_nome, 1)

            if use_sql:
                cur.execute("SELECT id, CONVERT(VARCHAR(19), ultima_atualizacao, 120), sync_pendente FROM tb_tarefas WHERE codigo = ?;", (cod,))
            else:
                cur.execute("SELECT id, ultima_atualizacao, sync_pendente FROM tb_tarefas WHERE codigo = ?;", (cod,))

            # Tratamento robusto para colunas DATETIME do SQL Server / SQLite
            dt_ts = normalize_dt(cloud_ts) or get_now_br()
            dt_conc = normalize_dt(d_conc)
            dt_rec = normalize_dt(d_rec)

            if use_sql:
                val_ts = dt_ts
                val_conc = dt_conc
                val_rec = dt_rec
            else:
                val_ts = dt_ts.strftime('%Y-%m-%d %H:%M:%S')
                val_conc = dt_conc.strftime('%Y-%m-%d %H:%M:%S') if dt_conc else None
                val_rec = dt_rec.strftime('%Y-%m-%d %H:%M:%S') if dt_rec else None

            row = cur.fetchone()
            if row:
                loc_id = row[0]
                loc_ts = (str(row[1]) if row[1] else "").strip()
                loc_pend = row[2]

                # Se a Nuvem tem carimbo mais recente ou Desktop não tinha carimbo, atualiza local
                if cloud_ts > loc_ts or not loc_ts:
                    cur.execute("""
                    UPDATE tb_tarefas
                    SET titulo = ?, id_projeto = ?, tipo = ?, prioridade = ?, status = ?,
                        observacoes = ?, data_conclusao = ?, recorrencia_dias = ?, data_recorrencia = ?,
                        ultima_atualizacao = ?, sync_pendente = 0
                    WHERE codigo = ?;
                    """, (tit, proj_id, tipo, prio, st, obs, val_conc, rec_d, val_rec, val_ts, cod))
                elif loc_ts > cloud_ts:
                    # Desktop é mais recente: mantém e deixa sync_pendente = 1
                    pass
                else:
                    # Mesma data/hora: limpa pendência
                    if loc_pend == 1:
                        cur.execute("UPDATE tb_tarefas SET sync_pendente = 0 WHERE codigo = ?;", (cod,))
            else:
                # Tarefa não existe no Desktop: insere diretamente
                cur.execute("""
                INSERT INTO tb_tarefas (codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, data_conclusao, recorrencia_dias, data_recorrencia, ultima_atualizacao, sync_pendente)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
                """, (cod, proj_id, tit, tipo, prio, st, obs, val_conc, rec_d, val_rec, val_ts))

        for c in local_changes:
            c_cod = c.get("codigo")
            if c_cod:
                cur.execute("UPDATE tb_tarefas SET sync_pendente = 0 WHERE codigo = ? AND sync_pendente = 1;", (c_cod,))

        conn.commit()
        conn.close()
        return True, "Sincronização concluída com sucesso!"
    except Exception as e:
        if conn: conn.close()
        return False, str(e)

# ==================== ESTADO OPERACIONAL & DIAGNÓSTICO LOCAL ====================
LOG_FILE = os.path.join(BASE_DIR, "desktop_app.log")

def log_event(msg):
    """Registra eventos no log local para diagnóstico imediato."""
    try:
        ts = get_now_br().strftime('%Y-%m-%d %H:%M:%S')
        line = f"[{ts}] {msg}\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
        print(line.strip())
    except Exception:
        pass

APP_RUNTIME_STATE = {
    "sql_ativo": False,
    "cloud_online": False,
    "modo": "desconhecido",  # 'sincronizado' | 'base_forte_offline' | 'nuvem_online'
    "descricao": "",
    "ultima_sync": None
}

def check_sql_server():
    """Verifica se o SQL Server local (ASSISTPE) está ativo e acessível."""
    try:
        conn = get_db_connection()
        if conn:
            try:
                init_sqlserver_tables(conn)
                conn.close()
                log_event("SQL Server local (ASSISTPE): CONECTADO E PRONTO")
                return True
            except Exception as e:
                try: conn.close()
                except Exception: pass
                log_event(f"SQL Server conectado, mas falhou ao validar tabelas: {e}")
                return False
        else:
            log_event("SQL Server local (ASSISTPE): INDISPONÍVEL / PARADO")
            return False
    except Exception as e:
        log_event(f"Exceção ao verificar SQL Server: {e}")
        return False

def check_cloud_online():
    """
    Verifica se a Nuvem (Render / Internet) está respondendo.
    Utiliza timeout adequado (7s) e bypass de validação SSL local.
    """
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    test_targets = [
        f"{CLOUD_URL.rstrip('/')}/api/tarefas",
        f"{CLOUD_URL.rstrip('/')}/",
        "https://www.google.com"
    ]

    for target in test_targets:
        try:
            req = urllib.request.Request(
                target,
                headers={"User-Agent": "ARPego-DesktopCheck/1.0"}
            )
            with urllib.request.urlopen(req, timeout=7.0, context=ctx) as resp:
                log_event(f"Conexão com {target}: ONLINE (Status {resp.status})")
                return True
        except urllib.error.HTTPError as he:
            # Qualquer código HTTP (inclusive 404/500) prova que o servidor e a internet estão online
            log_event(f"Conexão com {target}: ONLINE (Servidor respondeu HTTP {he.code})")
            return True
        except Exception as e:
            log_event(f"Tentativa de conexão com {target} sem resposta: {e}")
            continue

    log_event("Nenhuma conexão de internet detectada (OFFLINE)")
    return False

def show_alert_and_exit(message, title="ARPego - Assistente Pessoal"):
    """Exibe alerta nativo do Windows e encerra sem abrir a interface gráfica."""
    log_event(f"Exibindo alerta nativo: {message}")
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x1000)
    except Exception:
        print(message)
    sys.exit(0)

def proxy_cloud_request(method, path, body_data=None):
    """Encaminha requisições transparentemente para o Hub Cloud com bypass SSL."""
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"{CLOUD_URL.rstrip('/')}{path}"
    req_data = json.dumps(body_data).encode('utf-8') if body_data is not None else None
    headers = {"User-Agent": "ARPego-DesktopProxy/1.0", "X-User-Id": "1"}
    if req_data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read().decode('utf-8'))

# ==================== SERVIDOR WEB DESKTOP LOCAL (PORTA 5050) ====================
class DesktopRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        """Silencia logs automáticos no stderr para evitar erros sob pythonw.exe."""
        pass

    def translate_path(self, path):
        clean_path = path.split('?', 1)[0].split('#', 1)[0]
        if clean_path in ('/', '/painel', '/index.html'):
            return DESKTOP_HTML_FILE
        return os.path.join(BASE_DIR, clean_path.lstrip('/'))

    def do_GET(self):
        global LAST_HEARTBEAT
        LAST_HEARTBEAT = time.time()
        clean_path = self.path.split('?', 1)[0].split('#', 1)[0]

        if clean_path == '/api/heartbeat':
            self._send_json({"alive": True, "time": LAST_HEARTBEAT})
            return

        if clean_path in ('/', '/painel', '/index.html'):
            if os.path.exists(DESKTOP_HTML_FILE):
                with open(DESKTOP_HTML_FILE, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.end_headers()
                self.wfile.write(content)
                return

        if clean_path == '/icon.svg':
            icon_file = os.path.join(BASE_DIR, "icon.svg")
            if os.path.exists(icon_file):
                with open(icon_file, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'image/svg+xml')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        if clean_path == '/api/status_conexao':
            # Se estava marcado como SQL inativo, reavalia para promoção automática
            if not APP_RUNTIME_STATE.get("sql_ativo"):
                if check_sql_server():
                    APP_RUNTIME_STATE["sql_ativo"] = True
                    if APP_RUNTIME_STATE.get("cloud_online"):
                        APP_RUNTIME_STATE["modo"] = "sincronizado"
                        APP_RUNTIME_STATE["descricao"] = "🟢 Online & Sincronizado (SQL Server + Nuvem)"
                    else:
                        APP_RUNTIME_STATE["modo"] = "base_forte_offline"
                        APP_RUNTIME_STATE["descricao"] = "⚡ Base Forte (SQL Server Ativo | Nuvem Offline)"

            self._send_json({
                "sql_ativo": APP_RUNTIME_STATE["sql_ativo"],
                "cloud_online": APP_RUNTIME_STATE["cloud_online"],
                "modo": APP_RUNTIME_STATE["modo"],
                "descricao": APP_RUNTIME_STATE["descricao"],
                "ultima_sync": APP_RUNTIME_STATE.get("ultima_sync")
            })
            return

        # Auto-recuperação: se estava em modo nuvem pura e o SQL voltou, promove a sincronizado
        if APP_RUNTIME_STATE.get("modo") == "nuvem_online":
            if check_sql_server():
                APP_RUNTIME_STATE["sql_ativo"] = True
                APP_RUNTIME_STATE["modo"] = "sincronizado"
                APP_RUNTIME_STATE["descricao"] = "🟢 Online & Sincronizado (SQL Server + Nuvem)"
            else:
                if clean_path in ('/api/tarefas', '/api/projetos', '/api/dominios'):
                    try:
                        res = proxy_cloud_request("GET", clean_path)
                        self._send_json(res)
                    except Exception as e:
                        self._send_json({"error": str(e)}, 500)
                    return

        # Monitoramento de E-mails e SLA (Outlook Desktop)
        if clean_path == '/api/emails':
            try:
                import email_monitor
                res = email_monitor.obter_dados_emails_painel()
                self._send_json(res)
            except Exception as e:
                self._send_json({"emails": [], "error": str(e), "metricas": {"total": 0, "critico": 0, "alerta": 0, "atencao": 0, "vinculados": 0}})
            return

        if clean_path == '/api/emails/sugestoes':
            try:
                import email_monitor
                res = email_monitor.obter_sugestoes_pendentes()
                self._send_json(res)
            except Exception as e:
                self._send_json([], 500)
            return

        # Governança de Apontamentos de Horas (IADBMNG / PSOffice)
        if clean_path == '/api/apontamentos':
            try:
                import apontamentos_manager
                res = apontamentos_manager.obter_status_apontamentos()
                self._send_json(res)
            except Exception as e:
                self._send_json({"status": "erro", "error": str(e)}, 500)
            return

        # Modos Locais (Base Forte e Sincronizado): Lê do banco local
        if clean_path == '/api/tarefas':
            conn = get_db_connection()
            use_sql = True if conn else False
            if not conn:
                conn = sqlite3.connect(SQLITE_FALLBACK_FILE)

            cur = conn.cursor()
            if use_sql:
                cur.execute("""
                SELECT t.id, t.codigo, p.id AS projeto_id, p.nome AS projeto, t.titulo, t.tipo, t.prioridade, 
                       t.status, t.observacoes, t.recorrencia_dias, t.data_conclusao, t.data_recorrencia,
                       CONVERT(VARCHAR(19), t.ultima_atualizacao, 120) AS ultima_atualizacao
                FROM tb_tarefas t
                LEFT JOIN tb_projetos p ON t.id_projeto = p.id
                ORDER BY 
                    CASE t.status 
                        WHEN 'Em andamento' THEN 1 
                        WHEN 'Pendente' THEN 2
                        WHEN 'Aguardando retorno' THEN 3
                        WHEN 'Não iniciada' THEN 4
                        WHEN 'Liberado p/ testes' THEN 5 
                        WHEN 'Aguardando testes' THEN 6 
                        WHEN 'Em testes' THEN 6
                        WHEN 'Planejada' THEN 7 
                        ELSE 8 
                    END,
                    t.codigo;
                """)
            else:
                cur.execute("""
                SELECT t.id, t.codigo, p.id AS projeto_id, p.nome AS projeto, t.titulo, t.tipo, t.prioridade, 
                       t.status, t.observacoes, t.recorrencia_dias, t.data_conclusao, t.data_recorrencia,
                       t.ultima_atualizacao
                FROM tb_tarefas t
                LEFT JOIN tb_projetos p ON t.id_projeto = p.id
                ORDER BY 
                    CASE t.status 
                        WHEN 'Em andamento' THEN 1 
                        WHEN 'Pendente' THEN 2
                        WHEN 'Aguardando retorno' THEN 3
                        WHEN 'Não iniciada' THEN 4
                        WHEN 'Liberado p/ testes' THEN 5 
                        WHEN 'Aguardando testes' THEN 6 
                        WHEN 'Em testes' THEN 6
                        WHEN 'Planejada' THEN 7 
                        ELSE 8 
                    END,
                    t.codigo;
                """)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            conn.close()
            self._send_json(rows)

        elif clean_path == '/api/projetos':
            conn = get_db_connection()
            if not conn: conn = sqlite3.connect(SQLITE_FALLBACK_FILE)
            cur = conn.cursor()
            cur.execute("SELECT id, nome, tipo FROM tb_projetos ORDER BY nome;")
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            conn.close()
            self._send_json(rows)

        elif clean_path == '/api/dominios':
            conn = get_db_connection()
            if not conn: conn = sqlite3.connect(SQLITE_FALLBACK_FILE)
            cur = conn.cursor()
            cur.execute("SELECT id, nome, cor, borda, bg, ordem FROM tb_status WHERE ativo = 1 ORDER BY ordem, id;")
            cols_st = [d[0] for d in cur.description]
            st_list = [dict(zip(cols_st, r)) for r in cur.fetchall()]

            cur.execute("SELECT id, nome, cor, borda, bg, ordem FROM tb_prioridades WHERE ativo = 1 ORDER BY ordem, id;")
            cols_pr = [d[0] for d in cur.description]
            pr_list = [dict(zip(cols_pr, r)) for r in cur.fetchall()]
            conn.close()
            self._send_json({"status": st_list, "prioridades": pr_list})

        else:
            super().do_GET()

    def do_POST(self):
        global LAST_HEARTBEAT
        LAST_HEARTBEAT = time.time()
        clean_path = self.path.split('?', 1)[0].split('#', 1)[0]
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        if clean_path == '/api/shutdown':
            self._send_json({"ok": True})
            def _kill():
                time.sleep(0.2)
                os._exit(0)
            threading.Thread(target=_kill, daemon=True).start()
            return

        # MODO NUVEM: se SQL estiver ativo, promove imediatamente; se não, encaminha para Hub Nuvem
        if APP_RUNTIME_STATE.get("modo") == "nuvem_online":
            if check_sql_server():
                APP_RUNTIME_STATE["sql_ativo"] = True
                APP_RUNTIME_STATE["modo"] = "sincronizado"
                APP_RUNTIME_STATE["descricao"] = "🟢 Online & Sincronizado (SQL Server + Nuvem)"
            else:
                if clean_path in ('/api/tarefa/nova', '/api/tarefa/status', '/api/tarefa/editar', '/api/tarefa/excluir'):
                    try:
                        res = proxy_cloud_request("POST", clean_path, data)
                        self._send_json(res)
                    except Exception as e:
                        self._send_json({"error": str(e)}, 500)
                    return
                elif clean_path == '/api/sync':
                    self._send_json({"success": True, "mensagem": "Operando diretamente na Nuvem. Dados já sincronizados em tempo real."})
                    return
                elif clean_path in ('/api/dominios/status/salvar', '/api/dominios/prioridade/salvar'):
                    self._send_json({"success": False, "error": "Manutenção de domínios requer SQL Server ativo."}, 400)
                    return

        conn = get_db_connection()
        use_sql = True if conn else False
        if not conn:
            conn = sqlite3.connect(SQLITE_FALLBACK_FILE)

        cur = conn.cursor()

        if clean_path == '/api/tarefa/nova':
            proj_in = str(data.get('projeto', 'Geral')).strip()
            tipo = data.get('tipo', 'Profissional').strip()
            titulo = data.get('titulo', '').strip()
            prio = data.get('prioridade', 'Alta').strip()
            obs = data.get('observacoes', '').strip()
            rec = int(data.get('recorrencia_dias', 0))

            if not titulo:
                conn.close()
                self._send_json({"error": "Título obrigatório"}, 400)
                return

            # Busca ou cria projeto
            cur.execute("SELECT id FROM tb_projetos WHERE LOWER(nome) = LOWER(?);", (proj_in,))
            row = cur.fetchone()
            if row:
                proj_id = row[0]
            else:
                cur.execute("INSERT INTO tb_projetos (nome, sigla, tipo) VALUES (?, ?, ?);", (proj_in, proj_in[:6].upper(), tipo))
                if use_sql:
                    proj_id = cur.execute("SELECT @@IDENTITY;").fetchone()[0]
                else:
                    proj_id = cur.lastrowid

            # Gera código único
            if tipo == 'Pessoal':
                cur.execute("SELECT codigo FROM tb_tarefas WHERE codigo LIKE '#P%' ORDER BY id DESC;")
                last = cur.fetchone()
                num = int(re.sub(r'\D', '', last[0]) or 0) if last else 0
                cod = f"#P{num + 1:02d}"
            else:
                cur.execute("SELECT codigo FROM tb_tarefas WHERE codigo NOT LIKE '#P%' ORDER BY id DESC;")
                last = cur.fetchone()
                num = int(re.sub(r'\D', '', last[0]) or 0) if last else 0
                cod = f"#{num + 1:03d}"

            now_dt = get_now_br() if use_sql else get_now_br().strftime('%Y-%m-%d %H:%M:%S')
            cur.execute("""
            INSERT INTO tb_tarefas (codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, recorrencia_dias, sync_pendente, ultima_atualizacao)
            VALUES (?, ?, ?, ?, ?, 'Não iniciada', ?, ?, 1, ?);
            """, (cod, proj_id, titulo, tipo, prio, obs, rec, now_dt))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "codigo": cod})

        elif clean_path == '/api/tarefa/status':
            cod = data.get('codigo', '').strip()
            novo_st = data.get('status', 'Não iniciada').strip()
            now_dt = get_now_br() if use_sql else get_now_br().strftime('%Y-%m-%d %H:%M:%S')
            d_conc = (get_now_br() if use_sql else get_now_br().strftime('%Y-%m-%dT%H:%M:%S')) if novo_st == 'Concluída' else None
            cur.execute("""
            UPDATE tb_tarefas 
            SET status = ?, data_conclusao = ?, sync_pendente = 1, ultima_atualizacao = ? 
            WHERE codigo = ?;
            """, (novo_st, d_conc, now_dt, cod))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "codigo": cod, "status": novo_st})

        elif clean_path == '/api/tarefa/editar':
            cod = data.get('codigo', '').strip()
            tit = data.get('titulo', '').strip()
            proj_in = str(data.get('projeto', 'Geral')).strip()
            tipo = data.get('tipo', 'Profissional').strip()
            prio = data.get('prioridade', 'Alta').strip()
            st = data.get('status', 'Não iniciada').strip()
            rec = int(data.get('recorrencia_dias', 0))
            obs = data.get('observacoes', '').strip()

            cur.execute("SELECT id FROM tb_projetos WHERE LOWER(nome) = LOWER(?);", (proj_in,))
            row = cur.fetchone()
            proj_id = row[0] if row else 1

            now_dt = get_now_br() if use_sql else get_now_br().strftime('%Y-%m-%d %H:%M:%S')
            cur.execute("""
            UPDATE tb_tarefas 
            SET titulo = ?, id_projeto = ?, tipo = ?, prioridade = ?, status = ?, recorrencia_dias = ?, observacoes = ?, sync_pendente = 1, ultima_atualizacao = ?
            WHERE codigo = ?;
            """, (tit, proj_id, tipo, prio, st, rec, obs, now_dt, cod))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "codigo": cod})

        elif clean_path == '/api/tarefa/excluir':
            cod = data.get('codigo', '').strip()
            cur.execute("DELETE FROM tb_tarefas WHERE codigo = ?;", (cod,))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "codigo": cod})

        elif clean_path == '/api/dominios/status/salvar':
            nome = data.get('nome', '').strip()
            cor = data.get('cor', '#38bdf8').strip()
            borda = data.get('borda', '#0284c7').strip()
            bg = data.get('bg', '#0369a130').strip()
            cur.execute("SELECT id FROM tb_status WHERE LOWER(nome) = LOWER(?);", (nome,))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE tb_status SET cor = ?, borda = ?, bg = ? WHERE id = ?;", (cor, borda, bg, row[0]))
            else:
                cur.execute("INSERT INTO tb_status (nome, cor, borda, bg, ordem) VALUES (?, ?, ?, ?, 99);", (nome, cor, borda, bg))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "nome": nome})

        elif clean_path == '/api/dominios/prioridade/salvar':
            nome = data.get('nome', '').strip()
            cor = data.get('cor', '#f87171').strip()
            borda = cor + "50"
            bg = cor + "20"
            cur.execute("SELECT id FROM tb_prioridades WHERE LOWER(nome) = LOWER(?);", (nome,))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE tb_prioridades SET cor = ?, borda = ?, bg = ? WHERE id = ?;", (cor, borda, bg, row[0]))
            else:
                cur.execute("INSERT INTO tb_prioridades (nome, cor, borda, bg, ordem) VALUES (?, ?, ?, ?, 99);", (nome, cor, borda, bg))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "nome": nome})

        elif clean_path == '/api/sync':
            conn.close()
            success, msg = sync_with_cloud(verbose=False)
            if success:
                APP_RUNTIME_STATE["ultima_sync"] = get_now_br().strftime('%H:%M:%S')
            self._send_json({"success": success, "mensagem": msg})

        elif clean_path == '/api/emails/scan':
            conn.close()
            try:
                import email_monitor
                horas = int(data.get('horas', 360)) if isinstance(data, dict) else 360
                rel = email_monitor.processar_emails(horas_atras=horas)
                self._send_json({"success": True, "relatorio": rel})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)

        elif clean_path == '/api/emails/responder':
            conn.close()
            entry_id = data.get('entry_id') if isinstance(data, dict) else None
            if not entry_id:
                self._send_json({"error": "entry_id obrigatorio"}, 400)
                return
            try:
                import email_monitor
                email_monitor.marcar_email_respondido(entry_id)
                self._send_json({"success": True, "entry_id": entry_id})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)

        elif clean_path == '/api/emails/sugestoes/descartar':
            conn.close()
            sug_id = data.get('id') if isinstance(data, dict) else None
            try:
                import email_monitor
                email_monitor.descartar_sugestao(sug_id)
                self._send_json({"success": True, "id": sug_id})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)

        else:
            conn.close()
            self._send_json({"error": "Rota não encontrada"}, 404)

    def _send_json(self, data, status=200):
        response = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(response)

# ==================== LANÇADOR DE JANELA STANDALONE ====================
# ==================== LANÇADOR DE JANELA STANDALONE ====================
def check_existing_instance(port):
    """Verifica se já existe uma instância do ARPego rodando e respondendo nesta porta."""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/status_conexao",
            headers={"User-Agent": "ARPegoLauncher"}
        )
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass
    return False

def find_available_port(preferred=5050):
    """Encontra porta livre para o servidor local, evitando erro WinError 10048."""
    import socket
    for p in [preferred, 5051, 5052, 5053, 5054]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    return preferred

def launch_standalone_window(url):
    """Abre janela nativa de aplicativo standalone (App Mode) no Windows sem bloquear a execução."""
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")
    ]
    for p in edge_paths:
        if os.path.exists(p):
            try:
                log_event(f"Iniciando Edge App Mode: {p} --app={url}")
                subprocess.Popen([p, f"--app={url}"])
                return True
            except Exception as e:
                log_event(f"Falha ao abrir Edge: {e}")

    chrome_paths = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]
    for p in chrome_paths:
        if os.path.exists(p):
            try:
                log_event(f"Iniciando Chrome App Mode: {p} --app={url}")
                subprocess.Popen([p, f"--app={url}"])
                return True
            except Exception as e:
                log_event(f"Falha ao abrir Chrome: {e}")

    log_event(f"Abrindo navegador padrão do sistema: {url}")
    webbrowser.open(url)
    return True

def start_desktop_gui():
    """Inicia a Base Forte Windows Desktop Gráfica conforme a Matriz Operacional."""
    log_event("=" * 60)
    log_event("🤖 ASSISTENTE PESSOAL - ARPEGO (BASE FORTE DESKTOP)")
    log_event("Iniciando verificação de conectividade e banco de dados...")

    sql_ativo = check_sql_server()
    cloud_online = check_cloud_online()

    APP_RUNTIME_STATE["sql_ativo"] = sql_ativo
    APP_RUNTIME_STATE["cloud_online"] = cloud_online

    # REGRA 1: Se SQL não estiver ativo e não estiver online -> Informar e NÃO abrir
    if not sql_ativo and not cloud_online:
        log_event("[DECISÃO] SQL inativo e Nuvem offline: exibindo alerta nativo e encerrando.")
        show_alert_and_exit(
            "Assistente Pessoal - ARPego\n\n"
            "Não foi possível iniciar o aplicativo:\n\n"
            "• O banco de dados local (SQL Server ASSISTPE) está inativo.\n"
            "• Sem conexão com a internet (Nuvem offline).\n\n"
            "Para abrir o aplicativo, inicialize o serviço do SQL Server ou conecte-se à internet.",
            "ARPego - Sem Conexão"
        )
        return

    # REGRA 4: Se SQL ativo E online -> Sincronizar agora e abrir
    if sql_ativo and cloud_online:
        APP_RUNTIME_STATE["modo"] = "sincronizado"
        APP_RUNTIME_STATE["descricao"] = "🟢 Online & Sincronizado (SQL Server + Nuvem)"
        log_event("[DECISÃO] SQL ativo e Nuvem online: executando sincronização inicial...")
        success, msg = sync_with_cloud(verbose=False)
        if success:
            APP_RUNTIME_STATE["ultima_sync"] = get_now_br().strftime('%H:%M:%S')
            log_event(f"[SYNC] Sincronização inicial realizada às {APP_RUNTIME_STATE['ultima_sync']}.")
        else:
            log_event(f"[SYNC] Aviso na sincronização: {msg}")

    # REGRA 3: Se SQL ativo E offline -> Abrir com dados da Base Forte
    elif sql_ativo and not cloud_online:
        APP_RUNTIME_STATE["modo"] = "base_forte_offline"
        APP_RUNTIME_STATE["descricao"] = "⚡ Base Forte (SQL Server Ativo | Nuvem Offline)"
        log_event("[DECISÃO] SQL ativo e Nuvem offline: abrindo com dados do SQL Server local.")

    # REGRA 2: Se SQL inativo mas online -> Abrir com dados da Nuvem
    elif not sql_ativo and cloud_online:
        APP_RUNTIME_STATE["modo"] = "nuvem_online"
        APP_RUNTIME_STATE["descricao"] = "☁️ Modo Nuvem (SQL Server Inativo | Nuvem Online)"
        log_event("[DECISÃO] SQL inativo mas Nuvem online: operando com dados diretos da Nuvem.")

    # Encerra qualquer instância anterior pendente para aplicar as correções e configurações novas
    for p in [DESKTOP_PORT, 5051, 5052]:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{p}/api/shutdown", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=0.3)
        except Exception:
            pass
    time.sleep(0.3)

    # 1. Encontra porta HTTP disponível
    active_port = find_available_port(DESKTOP_PORT)
    log_event(f"Porta HTTP selecionada: {active_port}")

    # 2. Sobe o servidor HTTP local
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("127.0.0.1", active_port), DesktopRequestHandler)
    log_event(f"Servidor HTTP local ativo em http://127.0.0.1:{active_port}")

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)

    # 2.1. Inicia monitoramento de e-mails do Outlook em background (a cada 10 min)
    def background_email_scanner():
        time.sleep(8)
        while True:
            try:
                import email_monitor
                log_event("[EMAIL-SCAN] Executando varredura periódica de e-mails no Outlook (15 dias)...")
                email_monitor.processar_emails(horas_atras=360, limite_por_pasta=1000)
            except Exception as err_scan:
                log_event(f"[EMAIL-SCAN] Aviso no monitor em background: {err_scan}")
            time.sleep(600)

    t_email = threading.Thread(target=background_email_scanner, daemon=True)
    t_email.start()

    # 3. Lança a Janela Gráfica Stand Alone
    url = f"http://127.0.0.1:{active_port}"
    log_event(f"Disparando interface gráfica: {url} ({APP_RUNTIME_STATE['descricao']})")
    launch_standalone_window(url)

    # 4. Monitor de Ciclo de Vida por Heartbeat (Keep-Alive)
    # Dá 45 segundos de carência inicial para renderização da página.
    # Após isso, encerra se ficar 25 segundos sem receber heartbeat da janela.
    log_event("Monitor de ciclo de vida (Heartbeat) iniciado.")
    startup_grace = time.time() + 45
    try:
        while True:
            time.sleep(2)
            now = time.time()
            if now < startup_grace:
                continue
            if (now - LAST_HEARTBEAT) > 25:
                log_event(f"Janela fechada pelo usuário (inatividade de heartbeat há {int(now - LAST_HEARTBEAT)}s).")
                break
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        log_event("Processo desktop finalizado.")

if __name__ == '__main__':
    try:
        user_desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        shortcut_file = os.path.join(user_desktop, "ARPego.lnk")
        dup_shortcut = os.path.join(user_desktop, "Assistente Pessoal - ARPego.lnk")
        if os.path.exists(dup_shortcut):
            try: os.remove(dup_shortcut)
            except Exception: pass
        if not os.path.exists(shortcut_file):
            from generate_icon import setup_desktop_shortcut
            setup_desktop_shortcut()
    except Exception as e:
        log_event(f"Aviso ao configurar atalho: {e}")

    parser = argparse.ArgumentParser(description="ARPego Base Forte Windows Desktop")
    parser.add_argument("--sync", action="store_true", help="Executa uma sincronização única e encerra")
    args = parser.parse_args()

    if args.sync:
        success, msg = sync_with_cloud(verbose=True)
        print(f"[{'SUCESSO' if success else 'ERRO'}] {msg}")
    else:
        try:
            start_desktop_gui()
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            log_event(f"ERRO FATAL NA EXECUÇÃO:\n{tb}")
            show_alert_and_exit(f"Erro ao iniciar o aplicativo ARPego:\n\n{e}\n\nConsulte desktop_app.log.", "ARPego - Erro")

