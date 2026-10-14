import http.server
import socketserver
import json
import sqlite3
import os
import re
import threading
import time
from datetime import datetime, date, timedelta, timezone

import hashlib
import secrets

# Fuso horário oficial do Assistente: Brasília (UTC-3)
TZ_BR = timezone(timedelta(hours=-3))

def hash_password(password, salt=None):
    """Gera hash seguro SHA-256 com salt."""
    if not salt:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}:{h}"

def verify_password(password, stored_hash):
    """Verifica senha contra o hash armazenado."""
    try:
        if not stored_hash or ':' not in stored_hash:
            return False
        salt, h = stored_hash.split(':', 1)
        return hashlib.sha256((salt + password).encode('utf-8')).hexdigest() == h
    except Exception:
        return False

def get_now_br():
    """Retorna datetime naive no fuso horário de Brasília (UTC-3)."""
    return datetime.now(timezone.utc).astimezone(TZ_BR).replace(tzinfo=None)

def calculate_recurrence_target(rec_dias, from_dt=None):
    """
    Calcula a data/hora exata de reinício da tarefa baseada no corte diário das 04:00 (Brasília).
    Regra:
      - O dia operacional reinicia às 04:00.
      - Tarefa diária (rec_dias=1) finalizada após 04:00 (ex: às 21:00) reinicia no dia seguinte às 04:00.
      - Tarefa diária finalizada na madrugada antes das 04:00 (ex: às 01:30) reinicia às 04:00 do mesmo dia.
      - Tarefa de N dias reinicia N dias após o dia operacional às 04:00.
    """
    if not rec_dias or rec_dias <= 0:
        return None
    
    if from_dt is None:
        from_dt = get_now_br()
        
    if from_dt.hour < 4:
        op_date = from_dt.date() - timedelta(days=1)
    else:
        op_date = from_dt.date()
        
    target_date = op_date + timedelta(days=rec_dias)
    target_dt = datetime(target_date.year, target_date.month, target_date.day, 4, 0, 0)
    return target_dt.strftime('%Y-%m-%dT%H:%M:%S')

PORT = int(os.environ.get("PORT", 8080))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "assistpe.db")
MD_FILE = os.path.join(BASE_DIR, "ASSISTENTE_PESSOAL.md")
HTML_FILE = os.path.join(BASE_DIR, "painel.html")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # 0. Tabela de Usuários (Multi-Tenant)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT NOT NULL UNIQUE COLLATE NOCASE,
        nome TEXT NOT NULL,
        senha_hash TEXT NOT NULL,
        data_criacao TEXT
    );
    """)

    # Garante o usuário principal (Renato)
    cur.execute("SELECT id FROM tb_usuarios WHERE LOWER(login) = 'renato';")
    r_user = cur.fetchone()
    if not r_user:
        now_str = get_now_br().strftime('%Y-%m-%d %H:%M:%S')
        pwd_hash = hash_password("ASSITPES")
        cur.execute("INSERT INTO tb_usuarios (login, nome, senha_hash, data_criacao) VALUES (?, ?, ?, ?);",
                    ("Renato", "Renato Pego", pwd_hash, now_str))

    # 1. Tabelas de Tarefas e Projetos
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_projetos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_usuario INTEGER DEFAULT 1,
        nome TEXT NOT NULL,
        sigla TEXT,
        tipo TEXT DEFAULT 'Profissional'
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_tarefas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_usuario INTEGER DEFAULT 1,
        codigo TEXT NOT NULL,
        id_projeto INTEGER,
        titulo TEXT NOT NULL,
        tipo TEXT DEFAULT 'Profissional',
        prioridade TEXT DEFAULT 'Média',
        status TEXT DEFAULT 'Não iniciada',
        observacoes TEXT,
        data_conclusao TEXT,
        recorrencia_dias INTEGER DEFAULT 0,
        data_recorrencia TEXT,
        UNIQUE(id_usuario, codigo),
        FOREIGN KEY (id_projeto) REFERENCES tb_projetos(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_usuario INTEGER DEFAULT 1,
        codigo_tarefa TEXT,
        descricao TEXT,
        data_hora DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Tabela de Credenciais Criptografadas (Vault)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_credenciais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_usuario INTEGER DEFAULT 1,
        categoria TEXT NOT NULL,
        titulo TEXT NOT NULL,
        usuario TEXT,
        senha_cifrada TEXT NOT NULL,
        iv TEXT NOT NULL,
        salt TEXT NOT NULL,
        observacoes TEXT,
        data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3. Domínios de Status e Prioridades
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_usuario INTEGER DEFAULT 1,
        nome TEXT NOT NULL,
        cor TEXT NOT NULL,
        borda TEXT NOT NULL,
        bg TEXT NOT NULL,
        ordem INTEGER DEFAULT 0,
        ativo INTEGER DEFAULT 1,
        UNIQUE(id_usuario, nome)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tb_prioridades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_usuario INTEGER DEFAULT 1,
        nome TEXT NOT NULL,
        cor TEXT NOT NULL,
        borda TEXT NOT NULL,
        bg TEXT NOT NULL,
        ordem INTEGER DEFAULT 0,
        ativo INTEGER DEFAULT 1,
        UNIQUE(id_usuario, nome)
    );
    """)

    # Migrações seguras de id_usuario e índices compostos
    for table in ['tb_projetos', 'tb_tarefas', 'tb_historico', 'tb_credenciais', 'tb_status', 'tb_prioridades']:
        cur.execute(f"PRAGMA table_info({table});")
        cols = [r[1] for r in cur.fetchall()]
        if 'id_usuario' not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN id_usuario INTEGER DEFAULT 1;")
        cur.execute(f"UPDATE {table} SET id_usuario = 1 WHERE id_usuario IS NULL;")

    # Garante índice único composto em tb_tarefas para permitir #001 para cada usuário
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tb_tarefas';")
    tbl_row = cur.fetchone()
    if tbl_row and "UNIQUE(id_usuario, codigo)" not in tbl_row[0]:
        cur.execute("""
        CREATE TABLE tb_tarefas_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_usuario INTEGER DEFAULT 1,
            codigo TEXT NOT NULL,
            id_projeto INTEGER,
            titulo TEXT NOT NULL,
            tipo TEXT DEFAULT 'Profissional',
            prioridade TEXT DEFAULT 'Média',
            status TEXT DEFAULT 'Não iniciada',
            observacoes TEXT,
            data_conclusao TEXT,
            recorrencia_dias INTEGER DEFAULT 0,
            data_recorrencia TEXT,
            UNIQUE(id_usuario, codigo),
            FOREIGN KEY (id_projeto) REFERENCES tb_projetos(id)
        );
        """)
        cur.execute("""
        INSERT INTO tb_tarefas_v2 (id, id_usuario, codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, data_conclusao, recorrencia_dias, data_recorrencia)
        SELECT id, COALESCE(id_usuario, 1), codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, data_conclusao, COALESCE(recorrencia_dias, 0), data_recorrencia
        FROM tb_tarefas;
        """)
        cur.execute("DROP TABLE tb_tarefas;")
        cur.execute("ALTER TABLE tb_tarefas_v2 RENAME TO tb_tarefas;")

    # Garante índice único composto em tb_status
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tb_status';")
    st_row = cur.fetchone()
    if st_row and "UNIQUE(id_usuario, nome)" not in st_row[0]:
        cur.execute("""
        CREATE TABLE tb_status_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_usuario INTEGER DEFAULT 1,
            nome TEXT NOT NULL,
            cor TEXT NOT NULL,
            borda TEXT NOT NULL,
            bg TEXT NOT NULL,
            ordem INTEGER DEFAULT 0,
            ativo INTEGER DEFAULT 1,
            UNIQUE(id_usuario, nome)
        );
        """)
        cur.execute("""
        INSERT INTO tb_status_v2 (id, id_usuario, nome, cor, borda, bg, ordem, ativo)
        SELECT id, COALESCE(id_usuario, 1), nome, cor, borda, bg, ordem, ativo
        FROM tb_status;
        """)
        cur.execute("DROP TABLE tb_status;")
        cur.execute("ALTER TABLE tb_status_v2 RENAME TO tb_status;")

    # Garante índice único composto em tb_prioridades
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tb_prioridades';")
    pr_row = cur.fetchone()
    if pr_row and "UNIQUE(id_usuario, nome)" not in pr_row[0]:
        cur.execute("""
        CREATE TABLE tb_prioridades_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_usuario INTEGER DEFAULT 1,
            nome TEXT NOT NULL,
            cor TEXT NOT NULL,
            borda TEXT NOT NULL,
            bg TEXT NOT NULL,
            ordem INTEGER DEFAULT 0,
            ativo INTEGER DEFAULT 1,
            UNIQUE(id_usuario, nome)
        );
        """)
        cur.execute("""
        INSERT INTO tb_prioridades_v2 (id, id_usuario, nome, cor, borda, bg, ordem, ativo)
        SELECT id, COALESCE(id_usuario, 1), nome, cor, borda, bg, ordem, ativo
        FROM tb_prioridades;
        """)
        cur.execute("DROP TABLE tb_prioridades;")
        cur.execute("ALTER TABLE tb_prioridades_v2 RENAME TO tb_prioridades;")

    # Carga inicial de credenciais para o usuário 1 se vazio
    cur.execute("SELECT COUNT(*) FROM tb_credenciais WHERE id_usuario = 1;")
    if cur.fetchone()[0] == 0:
        bitlocker_cred = (
            1,
            'Segurança / BitLocker',
            'Chave de Recuperação BitLocker - Windows',
            '5E667192-7087-409F-892E-A2C9FC6FF69C',
            '6L4u3j1rWk/Xn6lH06mZ14j2U+2s/4oXo31F0V8Q3V1V+61qK2w0P9y2C4m8D7m1',
            'aHR0cHM6Ly9nby5taWNyb3NvZnQuY29t',
            'Yml0bG9ja2VyLXNhbHQtMjAyNg==',
            'Unidade de disco protegida por BitLocker. Comparar o início do identificador antes de usar.'
        )
        cur.execute("""
        INSERT INTO tb_credenciais (id_usuario, categoria, titulo, usuario, senha_cifrada, iv, salt, observacoes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, bitlocker_cred)

    # Carga inicial de projetos para o usuário 1 se vazio
    cur.execute("SELECT COUNT(*) FROM tb_projetos WHERE id_usuario = 1;")
    if cur.fetchone()[0] == 0:
        projetos = [
            (1, 'IFF Argentina', 'IFF-AR', 'Profissional'),
            (1, 'IFF Brasil / México', 'IFF-BR-MX', 'Profissional'),
            (1, 'IFF México', 'IFF-MX', 'Profissional'),
            (1, 'Unimed Campinas', 'UNIMED', 'Profissional'),
            (1, 'Caldic', 'CALDIC', 'Profissional'),
            (1, 'Eurofarma', 'EUROFARMA', 'Profissional'),
            (1, 'Vida Pessoal / Hábitos', 'PESSOAL', 'Pessoal')
        ]
        cur.executemany("INSERT INTO tb_projetos (id_usuario, nome, sigla, tipo) VALUES (?, ?, ?, ?);", projetos)

    # Carga inicial de tarefas para o usuário 1 se vazio
    cur.execute("SELECT COUNT(*) FROM tb_tarefas WHERE id_usuario = 1;")
    if cur.fetchone()[0] == 0:
        tarefas = [
            (1, '#001', 7, 'Configuração inicial do Assistente Pessoal', 'Profissional', 'Alta', 'Concluída', 'Estrutura base criada', '2026-10-09', 0),
            (1, '#002', 1, 'Viabilizar ambiente de QAS', 'Profissional', 'Alta', 'Concluída', 'Ambiente QAS funcionando perfeitamente', '2026-10-09', 0),
            (1, '#003', 1, 'Ativar e-mail sobre mudança de data de chegada (ZS)', 'Profissional', 'Média', 'Em testes', 'Liberada para testes em QAS', None, 0),
            (1, '#004', 2, 'Colocar código e descrição do Material no e-mail de aviso (ZS)', 'Profissional', 'Média', 'Em testes', 'Acompanhar homologação dos usuários', None, 0),
            (1, '#005', 1, 'Atualizar QAS com base em PRD', 'Profissional', 'Alta', 'Concluída', 'Refresh de base finalizado com sucesso', '2026-10-09', 0),
            (1, '#006', 2, 'Integração de Incoterm na carga do pedido', 'Profissional', 'Alta', 'Não iniciada', 'Mapear campos INCO1 e INCO2 no segmento da BAPI/IDoc', None, 0),
            (1, '#007', 3, 'Validar lançamentos contábeis com Joel', 'Profissional', 'Alta', 'Não iniciada', 'Agendar 15 min focados nas contas razão', None, 0),
            (1, '#008', 1, 'Erro ao abrir processo A...000109', 'Profissional', 'Alta', 'Concluída', 'Processo com erro investigado e resolvido', '2026-10-09', 0),
            (1, '#009', 2, 'Integração da NCM na carga de materiais', 'Profissional', 'Alta', 'Não iniciada', 'Validar campo NCM e regra cadastral', None, 0),
            (1, '#010', 2, 'Carregar tabela de vias de Transporte', 'Profissional', 'Média', 'Aguardando retorno', 'Aguardando planilha de dados para carga', None, 0),
            (1, '#011', 2, 'Buscar DOC CFIN com erro, pedir mais detalhes', 'Profissional', 'Alta', 'Aguardando retorno', 'Solicitar detalhes aos usuários (/AIF/ERR)', None, 0),
            (1, '#012', 2, 'Verificar execução de JOBs', 'Profissional', 'Média', 'Não iniciada', 'Acompanhamento de rotinas em background (SM37)', None, 0),
            (1, '#013', 2, 'Erro na carga do TXT do despachante (json)', 'Profissional', 'Alta', 'Concluída', 'Parsing e carga do TXT concluídos com sucesso', '2026-10-09', 0),
            (1, '#014', 2, 'Limpar conditions antes de enviar MIRO', 'Profissional', 'Alta', 'Não iniciada', 'Localizar BAdI/exit antes da BAPI e limpar conditions', None, 0),
            (1, '#015', 4, 'Correção da interface de fornecedores com MV', 'Profissional', 'Alta', 'Em testes', 'Ajustes concluídos, aguardando testes com MV', None, 0),
            (1, '#016', 4, 'Interface de NF com 2 pedidos', 'Profissional', 'Alta', 'Em testes', 'Ajustes concluídos, aguardando testes de múltiplos pedidos', None, 0),
            (1, '#017', 6, 'Aplicar melhorias da Caldic', 'Profissional', 'Média', 'Aguardando retorno', 'Replicar após estabilização na Caldic', None, 0),
            (1, '#018', 5, 'Atualizar produção', 'Profissional', 'Alta', 'Em andamento', 'Alinhar deploy em produção', None, 0),
            (1, '#019', 5, 'Refatorar Follow up', 'Profissional', 'Média', 'Não iniciada', 'Otimização de queries SQL e loops aninhados', None, 0),
            (1, '#020', 5, 'Corrigir eliminação de Invoice', 'Profissional', 'Alta', 'Não iniciada', 'Debugar rotina de exclusão', None, 0),
            (1, '#P01', 7, 'Fazer Duolingo', 'Pessoal', 'Média', 'Concluída', 'Ofensiva diária mantida hoje', '2026-10-09', 1),
            (1, '#P02', 7, 'Caminhada, calistênica', 'Pessoal', 'Alta', 'Concluída', 'Separar 30 a 45 min para atividade física', '2026-10-09', 1)
        ]
        cur.executemany("""
        INSERT INTO tb_tarefas (id_usuario, codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, data_conclusao, recorrencia_dias)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, tarefas)

    # Carga inicial de status para usuário 1 se vazio
    cur.execute("SELECT COUNT(*) FROM tb_status WHERE id_usuario = 1;")
    if cur.fetchone()[0] == 0:
        status_iniciais = [
            (1, 'Não iniciada', '#cbd5e1', '#475569', '#1e293b', 1),
            (1, 'Em andamento', '#38bdf8', '#0284c7', '#0369a130', 2),
            (1, 'Aguardando retorno', '#facc15', '#eab308', '#854d0e30', 3),
            (1, 'Pendente', '#facc15', '#eab308', '#854d0e30', 4),
            (1, 'Em testes', '#4ade80', '#22c55e', '#065f4630', 5),
            (1, 'Concluída', '#94a3b8', '#64748b', '#1e293b', 6)
        ]
        cur.executemany("INSERT INTO tb_status (id_usuario, nome, cor, borda, bg, ordem, ativo) VALUES (?, ?, ?, ?, ?, ?, 1);", status_iniciais)

    # Carga inicial de prioridades para usuário 1 se vazio
    cur.execute("SELECT COUNT(*) FROM tb_prioridades WHERE id_usuario = 1;")
    if cur.fetchone()[0] == 0:
        prio_iniciais = [
            (1, 'Alta', '#f87171', '#ef444450', '#ef444420', 1),
            (1, 'Média', '#fbbf24', '#f59e0b50', '#f59e0b20', 2),
            (1, 'Baixa', '#60a5fa', '#3b82f650', '#3b82f620', 3)
        ]
        cur.executemany("INSERT INTO tb_prioridades (id_usuario, nome, cor, borda, bg, ordem, ativo) VALUES (?, ?, ?, ?, ?, ?, 1);", prio_iniciais)

    conn.commit()
    conn.close()

def create_new_user(login, nome, senha):
    """Cadastra um novo usuário no sistema e inicializa seu ambiente 100% isolado."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM tb_usuarios WHERE LOWER(login) = LOWER(?);", (login.strip(),))
    if cur.fetchone():
        conn.close()
        return None, "Este login já está cadastrado. Escolha outro nome de usuário."

    pwd_hash = hash_password(senha)
    now_str = get_now_br().strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("INSERT INTO tb_usuarios (login, nome, senha_hash, data_criacao) VALUES (?, ?, ?, ?);",
                (login.strip(), nome.strip(), pwd_hash, now_str))
    new_uid = cur.lastrowid

    # Seed projetos padrão do novo usuário
    cur.execute("INSERT INTO tb_projetos (id_usuario, nome, sigla, tipo) VALUES (?, 'Geral', 'GERAL', 'Profissional');", (new_uid,))
    cur.execute("INSERT INTO tb_projetos (id_usuario, nome, sigla, tipo) VALUES (?, 'Vida Pessoal / Hábitos', 'PESSOAL', 'Pessoal');", (new_uid,))

    # Seed status padrão do novo usuário
    status_iniciais = [
        ('Não iniciada', '#cbd5e1', '#475569', '#1e293b', 1),
        ('Em andamento', '#38bdf8', '#0284c7', '#0369a130', 2),
        ('Aguardando retorno', '#facc15', '#eab308', '#854d0e30', 3),
        ('Pendente', '#facc15', '#eab308', '#854d0e30', 4),
        ('Em testes', '#4ade80', '#22c55e', '#065f4630', 5),
        ('Concluída', '#94a3b8', '#64748b', '#1e293b', 6)
    ]
    cur.executemany("INSERT INTO tb_status (id_usuario, nome, cor, borda, bg, ordem, ativo) VALUES (?, ?, ?, ?, ?, ?, 1);",
                    [(new_uid, s[0], s[1], s[2], s[3], s[4]) for s in status_iniciais])

    # Seed prioridades padrão do novo usuário
    prio_iniciais = [
        ('Alta', '#f87171', '#ef444450', '#ef444420', 1),
        ('Média', '#fbbf24', '#f59e0b50', '#f59e0b20', 2),
        ('Baixa', '#60a5fa', '#3b82f650', '#3b82f620', 3)
    ]
    cur.executemany("INSERT INTO tb_prioridades (id_usuario, nome, cor, borda, bg, ordem, ativo) VALUES (?, ?, ?, ?, ?, ?, 1);",
                    [(new_uid, p[0], p[1], p[2], p[3], p[4]) for p in prio_iniciais])

    conn.commit()
    conn.close()
    return {"id": new_uid, "login": login.strip(), "nome": nome.strip()}, None

def check_recurrence():
    """Verifica e reseta tarefas concluídas cujo horário de recorrência (corte às 04:00 BRT) já chegou."""
    try:
        now_br = get_now_br()
        now_iso = now_br.strftime('%Y-%m-%dT%H:%M:%S')
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("""
        SELECT codigo, titulo, recorrencia_dias, data_recorrencia, data_conclusao
        FROM tb_tarefas
        WHERE status = 'Concluída' 
          AND recorrencia_dias > 0;
        """)
        tasks = cur.fetchall()
        for t in tasks:
            cod, titulo, rec_dias, dt_rec, dt_conc = t
            should_reset = False
            if dt_rec:
                if dt_rec <= now_iso:
                    should_reset = True
            else:
                if not dt_conc:
                    should_reset = True
                else:
                    try:
                        c_dt = datetime.fromisoformat(dt_conc.split()[0])
                        calc_target = calculate_recurrence_target(rec_dias, c_dt)
                        if calc_target and calc_target <= now_iso:
                            should_reset = True
                    except Exception:
                        should_reset = True

            if should_reset:
                cur.execute("""
                UPDATE tb_tarefas 
                SET status = 'Pendente', data_conclusao = NULL, data_recorrencia = NULL
                WHERE codigo = ?;
                """, (cod,))
                cur.execute("INSERT INTO tb_historico (codigo_tarefa, descricao) VALUES (?, ?);", 
                            (cod, f"Tarefa retornou a Pendente automaticamente às 04:00 (regra de {rec_dias} dia(s))."))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao verificar recorrência: {e}")

def recurrence_background_loop():
    """Worker em background que checa a cada 60s se o horário das 04:00 chegou."""
    while True:
        try:
            time.sleep(60)
            check_recurrence()
        except Exception:
            pass

class CloudAssistantHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean_path = path.split('?', 1)[0].split('#', 1)[0]
        if clean_path in ('/', '/painel', '/index.html'):
            return HTML_FILE
        return os.path.join(BASE_DIR, clean_path.lstrip('/'))

    def get_current_user_id(self):
        uid = self.headers.get('X-User-Id')
        if uid and str(uid).strip().isdigit():
            return int(str(uid).strip())
        return 1

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-User-Id')
        self.end_headers()

    def do_GET(self):
        clean_path = self.path.split('?', 1)[0].split('#', 1)[0]
        if clean_path in ('/', '/painel', '/painel.html', '/index.html'):
            if os.path.exists(HTML_FILE):
                with open(HTML_FILE, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                self.wfile.write(content)
                return

        uid = self.get_current_user_id()

        if self.path == '/api/auth/me':
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT id, login, nome FROM tb_usuarios WHERE id = ?;", (uid,))
            user = cur.fetchone()
            conn.close()
            if user:
                self._send_json({"autenticado": True, "user": dict(user)})
            else:
                self._send_json({"autenticado": False, "error": "Usuário não encontrado"}, 401)

        elif self.path == '/api/tarefas':
            check_recurrence()
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
            SELECT t.id, t.codigo, p.id AS projeto_id, p.nome AS projeto, t.titulo, t.tipo, t.prioridade, 
                   t.status, t.observacoes, t.recorrencia_dias, t.data_conclusao, t.data_recorrencia
            FROM tb_tarefas t
            LEFT JOIN tb_projetos p ON t.id_projeto = p.id
            WHERE t.id_usuario = ?
            ORDER BY 
                CASE t.status 
                    WHEN 'Em andamento' THEN 1 
                    WHEN 'Pendente' THEN 2
                    WHEN 'Aguardando retorno' THEN 3
                    WHEN 'Não iniciada' THEN 4
                    WHEN 'Liberado p/ testes' THEN 5 
                    WHEN 'Aguardando testes' THEN 6 
                    WHEN 'Planejada' THEN 7 
                    ELSE 8 
                END,
                t.codigo;
            """, (uid,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            self._send_json(rows)

        elif self.path == '/api/projetos':
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT id, nome, tipo FROM tb_projetos WHERE id_usuario = ? ORDER BY nome;", (uid,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            self._send_json(rows)

        elif self.path == '/api/credenciais':
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
            SELECT id, categoria, titulo, usuario, senha_cifrada, iv, salt, observacoes
            FROM tb_credenciais
            WHERE id_usuario = ?
            ORDER BY categoria, titulo;
            """, (uid,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            self._send_json(rows)

        elif self.path == '/api/dominios':
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT id, nome, cor, borda, bg, ordem FROM tb_status WHERE id_usuario = ? AND ativo = 1 ORDER BY ordem, id;", (uid,))
            status_list = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT id, nome, cor, borda, bg, ordem FROM tb_prioridades WHERE id_usuario = ? AND ativo = 1 ORDER BY ordem, id;", (uid,))
            prio_list = [dict(r) for r in cur.fetchall()]
            conn.close()
            self._send_json({"status": status_list, "prioridades": prio_list})

        elif self.path in ('/sw.js', '/service-worker.js'):
            sw_file = os.path.join(BASE_DIR, "sw.js")
            if os.path.exists(sw_file):
                with open(sw_file, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/javascript; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Service-Worker-Allowed', '/')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Arquivo sw.js não encontrado")

        elif self.path == '/manifest.json':
            man_file = os.path.join(BASE_DIR, "manifest.json")
            if os.path.exists(man_file):
                with open(man_file, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/manifest+json; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Arquivo manifest.json não encontrado")

        elif self.path == '/icon.svg':
            icon_file = os.path.join(BASE_DIR, "icon.svg")
            if os.path.exists(icon_file):
                with open(icon_file, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'image/svg+xml')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Arquivo icon.svg não encontrado")

        else:
            super().do_GET()

    def do_POST(self):
        uid = self.get_current_user_id()

        if self.path == '/api/auth/login':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                login = data.get('login', '').strip()
                senha = data.get('senha', '').strip()

                if not login or not senha:
                    self._send_json({"error": "Login e senha são obrigatórios"}, 400)
                    return

                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT id, login, nome, senha_hash FROM tb_usuarios WHERE LOWER(login) = LOWER(?);", (login,))
                user = cur.fetchone()
                conn.close()

                if not user or not verify_password(senha, user['senha_hash']):
                    self._send_json({"error": "Usuário ou senha inválidos."}, 401)
                    return

                self._send_json({
                    "success": True,
                    "user": {
                        "id": user['id'],
                        "login": user['login'],
                        "nome": user['nome']
                    }
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == '/api/auth/cadastro':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                login = data.get('login', '').strip()
                nome = data.get('nome', '').strip() or login
                senha = data.get('senha', '').strip()

                if not login or not senha:
                    self._send_json({"error": "Login e senha são obrigatórios"}, 400)
                    return

                user_info, err = create_new_user(login, nome, senha)
                if err:
                    self._send_json({"error": err}, 400)
                    return

                self._send_json({"success": True, "user": user_info})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == '/api/tarefa/status':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                codigo = data.get('codigo', '').strip()
                novo_status = data.get('status', '').strip()

                if not codigo or not novo_status:
                    self._send_json({"error": "Parâmetros inválidos"}, 400)
                    return

                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()

                # Busca dados atuais para cálculo de recorrência dentro do escopo do usuário
                cur.execute("SELECT recorrencia_dias FROM tb_tarefas WHERE id_usuario = ? AND codigo = ?;", (uid, codigo))
                row = cur.fetchone()
                rec_dias = row[0] if row else 0

                data_conc = None
                data_rec = None
                if novo_status == 'Concluída':
                    now_br = get_now_br()
                    data_conc = now_br.strftime('%Y-%m-%d %H:%M:%S')
                    if rec_dias and rec_dias > 0:
                        data_rec = calculate_recurrence_target(rec_dias, now_br)
                    cur.execute("""
                    UPDATE tb_tarefas 
                    SET status = ?, data_conclusao = ?, data_recorrencia = ? 
                    WHERE id_usuario = ? AND codigo = ?;
                    """, (novo_status, data_conc, data_rec, uid, codigo))
                else:
                    cur.execute("""
                    UPDATE tb_tarefas 
                    SET status = ?, data_conclusao = NULL, data_recorrencia = NULL 
                    WHERE id_usuario = ? AND codigo = ?;
                    """, (novo_status, uid, codigo))

                cur.execute("INSERT INTO tb_historico (id_usuario, codigo_tarefa, descricao) VALUES (?, ?, ?);", 
                            (uid, codigo, f"Status atualizado para: {novo_status}"))
                conn.commit()
                conn.close()

                # Atualiza Markdown se o arquivo existir localmente e for o usuário principal
                if uid == 1 and os.path.exists(MD_FILE):
                    try:
                        with open(MD_FILE, 'r', encoding='utf-8') as f:
                            content = f.read()
                        pattern = rf"(\| \*\*{re.escape(codigo)}\*\* \| [^\|]+ \| [^\|]+ \| [^\|]+ \| )([^\|]+)( \|)"
                        content = re.sub(pattern, rf"\g<1>{novo_status}\g<3>", content)
                        with open(MD_FILE, 'w', encoding='utf-8') as f:
                            f.write(content)
                    except Exception:
                        pass

                self._send_json({"success": True, "codigo": codigo, "status": novo_status})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == '/api/tarefa/editar':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                codigo = data.get('codigo', '').strip()
                titulo = data.get('titulo', '').strip()
                projeto_input = str(data.get('projeto', '') or data.get('projeto_id', '')).strip()
                prioridade = data.get('prioridade', 'Alta').strip()
                tipo = data.get('tipo', 'Profissional').strip()
                status = data.get('status', 'Não iniciada').strip()
                observacoes = data.get('observacoes', '').strip()
                recorrencia_dias = int(data.get('recorrencia_dias', 0))

                if not codigo or not titulo:
                    self._send_json({"error": "Código e Título são obrigatórios"}, 400)
                    return

                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()

                # Trata projeto isolado por usuário
                projeto_id = 1
                if projeto_input.isdigit():
                    projeto_id = int(projeto_input)
                elif projeto_input:
                    cur.execute("SELECT id FROM tb_projetos WHERE id_usuario = ? AND LOWER(nome) = LOWER(?);", (uid, projeto_input))
                    proj_found = cur.fetchone()
                    if proj_found:
                        projeto_id = proj_found[0]
                    else:
                        cur.execute("INSERT INTO tb_projetos (id_usuario, nome, sigla, tipo) VALUES (?, ?, ?, ?);",
                                    (uid, projeto_input, projeto_input[:6].upper(), tipo))
                        projeto_id = cur.lastrowid
                else:
                    cur.execute("SELECT id FROM tb_projetos WHERE id_usuario = ? ORDER BY id ASC LIMIT 1;", (uid,))
                    proj_f = cur.fetchone()
                    if proj_f:
                        projeto_id = proj_f[0]

                cur.execute("SELECT status, data_conclusao, data_recorrencia FROM tb_tarefas WHERE id_usuario = ? AND codigo = ?;", (uid, codigo))
                old_row = cur.fetchone()
                old_status = old_row[0] if old_row else ''
                old_conc = old_row[1] if old_row else None
                old_rec = old_row[2] if old_row else None

                data_conc = old_conc
                data_rec = old_rec
                if status == 'Concluída':
                    now_br = get_now_br()
                    if old_status != 'Concluída' or not data_conc:
                        data_conc = now_br.strftime('%Y-%m-%d %H:%M:%S')
                    if recorrencia_dias > 0:
                        data_rec = calculate_recurrence_target(recorrencia_dias, now_br)
                    else:
                        data_rec = None
                else:
                    data_conc = None
                    data_rec = None

                cur.execute("""
                UPDATE tb_tarefas
                SET titulo = ?, id_projeto = ?, prioridade = ?, tipo = ?, status = ?, observacoes = ?, 
                    recorrencia_dias = ?, data_conclusao = ?, data_recorrencia = ?
                WHERE id_usuario = ? AND codigo = ?;
                """, (titulo, projeto_id, prioridade, tipo, status, observacoes, recorrencia_dias, data_conc, data_rec, uid, codigo))
                cur.execute("INSERT INTO tb_historico (id_usuario, codigo_tarefa, descricao) VALUES (?, ?, ?);", 
                            (uid, codigo, f"Tarefa editada: {titulo}"))
                conn.commit()
                conn.close()

                self._send_json({"success": True, "codigo": codigo})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == '/api/tarefa/excluir':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                codigo = data.get('codigo', '').strip()

                if not codigo:
                    self._send_json({"error": "Código é obrigatório"}, 400)
                    return

                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()
                cur.execute("DELETE FROM tb_tarefas WHERE id_usuario = ? AND codigo = ?;", (uid, codigo))
                cur.execute("INSERT INTO tb_historico (id_usuario, codigo_tarefa, descricao) VALUES (?, ?, ?);", 
                            (uid, codigo, "Tarefa excluída"))
                conn.commit()
                conn.close()

                self._send_json({"success": True, "codigo": codigo})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == '/api/credenciais':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                categoria = data.get('categoria', 'Geral').strip()
                titulo = data.get('titulo', '').strip()
                usuario = data.get('usuario', '').strip()
                senha_cifrada = data.get('senha_cifrada', '').strip()
                iv = data.get('iv', '').strip()
                salt = data.get('salt', '').strip()
                observacoes = data.get('observacoes', '').strip()

                if not titulo or not senha_cifrada or not iv or not salt:
                    self._send_json({"error": "Campos obrigatórios ausentes"}, 400)
                    return

                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()
                cur.execute("""
                INSERT INTO tb_credenciais (id_usuario, categoria, titulo, usuario, senha_cifrada, iv, salt, observacoes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (uid, categoria, titulo, usuario, senha_cifrada, iv, salt, observacoes))
                conn.commit()
                conn.close()

                self._send_json({"success": True, "titulo": titulo})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == '/api/credenciais/excluir':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                cred_id = data.get('id')
                if not cred_id:
                    self._send_json({"error": "ID ausente"}, 400)
                    return

                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()
                cur.execute("DELETE FROM tb_credenciais WHERE id_usuario = ? AND id = ?;", (uid, cred_id))
                conn.commit()
                conn.close()

                self._send_json({"success": True, "id": cred_id})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == '/api/tarefa/nova':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                projeto_input = str(data.get('projeto', '') or data.get('projeto_id', '')).strip()
                titulo = data.get('titulo', '').strip()
                prioridade = data.get('prioridade', 'Alta').strip()
                observacoes = data.get('observacoes', '').strip()
                tipo = data.get('tipo', 'Profissional').strip()
                recorrencia_dias = int(data.get('recorrencia_dias', 0))

                if not titulo:
                    self._send_json({"error": "Título é obrigatório"}, 400)
                    return

                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()

                # Trata projeto no escopo do usuário
                projeto_id = 1
                if projeto_input.isdigit():
                    projeto_id = int(projeto_input)
                elif projeto_input:
                    cur.execute("SELECT id FROM tb_projetos WHERE id_usuario = ? AND LOWER(nome) = LOWER(?);", (uid, projeto_input))
                    proj_found = cur.fetchone()
                    if proj_found:
                        projeto_id = proj_found[0]
                    else:
                        cur.execute("INSERT INTO tb_projetos (id_usuario, nome, sigla, tipo) VALUES (?, ?, ?, ?);",
                                    (uid, projeto_input, projeto_input[:6].upper(), tipo))
                        projeto_id = cur.lastrowid
                else:
                    cur.execute("SELECT id FROM tb_projetos WHERE id_usuario = ? ORDER BY id ASC LIMIT 1;", (uid,))
                    proj_f = cur.fetchone()
                    if proj_f:
                        projeto_id = proj_f[0]

                # Gera o próximo código isolado por usuário
                if tipo == 'Pessoal':
                    cur.execute("SELECT codigo FROM tb_tarefas WHERE id_usuario = ? AND codigo LIKE '#P%' ORDER BY id DESC LIMIT 1;", (uid,))
                    last = cur.fetchone()
                    if last:
                        last_num = int(re.sub(r'\D', '', last[0]) or 0)
                        codigo = f"#P{last_num + 1:02d}"
                    else:
                        codigo = "#P01"
                else:
                    cur.execute("SELECT codigo FROM tb_tarefas WHERE id_usuario = ? AND codigo NOT LIKE '#P%' ORDER BY id DESC LIMIT 1;", (uid,))
                    last = cur.fetchone()
                    if last:
                        last_num = int(re.sub(r'\D', '', last[0]) or 0)
                        codigo = f"#{last_num + 1:03d}"
                    else:
                        codigo = "#001"

                cur.execute("""
                INSERT INTO tb_tarefas (id_usuario, codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, recorrencia_dias)
                VALUES (?, ?, ?, ?, ?, ?, 'Não iniciada', ?, ?);
                """, (uid, codigo, projeto_id, titulo, tipo, prioridade, observacoes, recorrencia_dias))

                cur.execute("INSERT INTO tb_historico (id_usuario, codigo_tarefa, descricao) VALUES (?, ?, ?);", 
                            (uid, codigo, f"Nova tarefa criada: {titulo}"))
                conn.commit()

                # Busca nome do projeto
                cur.execute("SELECT nome FROM tb_projetos WHERE id = ?;", (projeto_id,))
                proj_row = cur.fetchone()
                proj_nome = proj_row[0] if proj_row else "Geral"
                conn.close()

                # Atualiza Markdown se existir e for Renato
                if uid == 1 and os.path.exists(MD_FILE):
                    try:
                        with open(MD_FILE, 'r', encoding='utf-8') as f:
                            content = f.read()
                        new_entry = f"- **{get_now_br().strftime('%Y-%m-%d')}:** [{codigo}] {proj_nome}: Nova tarefa cadastrada ({titulo}).\n"
                        content += new_entry
                        with open(MD_FILE, 'w', encoding='utf-8') as f:
                            f.write(content)
                    except Exception:
                        pass

                self._send_json({
                    "success": True, 
                    "codigo": codigo, 
                    "titulo": titulo, 
                    "projeto": proj_nome, 
                    "prioridade": prioridade, 
                    "observacoes": observacoes,
                    "recorrencia_dias": recorrencia_dias
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == '/api/sync':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                changes = data.get('changes', [])
                client_id = data.get('client_id', 'unknown')
                
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                
                applied = 0
                for item in changes:
                    action = item.get('action')
                    if action == 'status':
                        cod = item.get('codigo', '').strip()
                        st = item.get('status', '').strip()
                        if cod and st:
                            cur.execute("SELECT recorrencia_dias FROM tb_tarefas WHERE id_usuario = ? AND codigo = ?;", (uid, cod))
                            row = cur.fetchone()
                            rec_d = row[0] if row else 0
                            data_conc = None
                            data_rec = None
                            if st == 'Concluída':
                                now_br = get_now_br()
                                data_conc = now_br.strftime('%Y-%m-%d %H:%M:%S')
                                if rec_d > 0:
                                    data_rec = calculate_recurrence_target(rec_d, now_br)
                            cur.execute("UPDATE tb_tarefas SET status = ?, data_conclusao = ?, data_recorrencia = ? WHERE id_usuario = ? AND codigo = ?;", (st, data_conc, data_rec, uid, cod))
                            applied += 1
                    elif action == 'nova':
                        tit = item.get('titulo', '').strip()
                        proj_in = str(item.get('projeto', '') or item.get('projeto_id', '')).strip()
                        tipo = item.get('tipo', 'Profissional').strip()
                        prio = item.get('prioridade', 'Alta').strip()
                        obs = item.get('observacoes', '').strip()
                        rec_d = int(item.get('recorrencia_dias', 0))
                        if tit:
                            projeto_id = 1
                            if proj_in.isdigit():
                                projeto_id = int(proj_in)
                            elif proj_in:
                                cur.execute("SELECT id FROM tb_projetos WHERE id_usuario = ? AND LOWER(nome) = LOWER(?);", (uid, proj_in))
                                found = cur.fetchone()
                                if found:
                                    projeto_id = found[0]
                                else:
                                    cur.execute("INSERT INTO tb_projetos (id_usuario, nome, sigla, tipo) VALUES (?, ?, ?, ?);", (uid, proj_in, proj_in[:6].upper(), tipo))
                                    projeto_id = cur.lastrowid
                            else:
                                cur.execute("SELECT id FROM tb_projetos WHERE id_usuario = ? ORDER BY id ASC LIMIT 1;", (uid,))
                                proj_f = cur.fetchone()
                                if proj_f:
                                    projeto_id = proj_f[0]

                            if tipo == 'Pessoal':
                                cur.execute("SELECT codigo FROM tb_tarefas WHERE id_usuario = ? AND codigo LIKE '#P%' ORDER BY id DESC LIMIT 1;", (uid,))
                                last = cur.fetchone()
                                cod = f"#P{int(re.sub(r'\\D', '', last[0]) or 0) + 1:02d}" if last else "#P01"
                            else:
                                cur.execute("SELECT codigo FROM tb_tarefas WHERE id_usuario = ? AND codigo NOT LIKE '#P%' ORDER BY id DESC LIMIT 1;", (uid,))
                                last = cur.fetchone()
                                cod = f"#{int(re.sub(r'\\D', '', last[0]) or 0) + 1:03d}" if last else "#001"
                            cur.execute("INSERT INTO tb_tarefas (id_usuario, codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, recorrencia_dias) VALUES (?, ?, ?, ?, ?, ?, 'Não iniciada', ?, ?);", (uid, cod, projeto_id, tit, tipo, prio, obs, rec_d))
                            applied += 1
                    elif action == 'editar':
                        cod = item.get('codigo', '').strip()
                        tit = item.get('titulo', '').strip()
                        proj_in = str(item.get('projeto', '') or item.get('projeto_id', '')).strip()
                        tipo = item.get('tipo', 'Profissional').strip()
                        prio = item.get('prioridade', 'Alta').strip()
                        st = item.get('status', 'Não iniciada').strip()
                        obs = item.get('observacoes', '').strip()
                        rec_d = int(item.get('recorrencia_dias', 0))
                        if cod and tit:
                            projeto_id = 1
                            if proj_in.isdigit():
                                projeto_id = int(proj_in)
                            elif proj_in:
                                cur.execute("SELECT id FROM tb_projetos WHERE id_usuario = ? AND LOWER(nome) = LOWER(?);", (uid, proj_in))
                                found = cur.fetchone()
                                if found:
                                    projeto_id = found[0]
                                else:
                                    cur.execute("INSERT INTO tb_projetos (id_usuario, nome, sigla, tipo) VALUES (?, ?, ?, ?);", (uid, proj_in, proj_in[:6].upper(), tipo))
                                    projeto_id = cur.lastrowid
                            cur.execute("UPDATE tb_tarefas SET titulo = ?, id_projeto = ?, tipo = ?, prioridade = ?, status = ?, observacoes = ?, recorrencia_dias = ? WHERE id_usuario = ? AND codigo = ?;", (tit, projeto_id, tipo, prio, st, obs, rec_d, uid, cod))
                            if cur.rowcount == 0:
                                cur.execute("""
                                INSERT INTO tb_tarefas (id_usuario, codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, recorrencia_dias)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                                """, (uid, cod, projeto_id, tit, tipo, prio, st, obs, rec_d))
                            applied += 1
                
                conn.commit()
                
                # Retorna dados atualizados filtrados pelo usuário
                check_recurrence()
                cur.execute("""
                SELECT t.id, t.codigo, p.id AS projeto_id, p.nome AS projeto, t.titulo, t.tipo, t.prioridade, 
                       t.status, t.observacoes, t.recorrencia_dias, t.data_conclusao, t.data_recorrencia
                FROM tb_tarefas t
                LEFT JOIN tb_projetos p ON t.id_projeto = p.id
                WHERE t.id_usuario = ?
                ORDER BY t.id;
                """, (uid,))
                tarefas = [dict(r) for r in cur.fetchall()]
                cur.execute("SELECT id, nome, tipo FROM tb_projetos WHERE id_usuario = ? ORDER BY nome;", (uid,))
                projetos = [dict(r) for r in cur.fetchall()]
                cur.execute("SELECT id, nome, cor, borda, bg, ordem FROM tb_status WHERE id_usuario = ? AND ativo = 1 ORDER BY ordem, id;", (uid,))
                status_list = [dict(r) for r in cur.fetchall()]
                cur.execute("SELECT id, nome, cor, borda, bg, ordem FROM tb_prioridades WHERE id_usuario = ? AND ativo = 1 ORDER BY ordem, id;", (uid,))
                prio_list = [dict(r) for r in cur.fetchall()]
                conn.close()
                
                self._send_json({
                    "success": True,
                    "applied_changes": applied,
                    "server_time": get_now_br().strftime('%Y-%m-%dT%H:%M:%S'),
                    "tarefas": tarefas,
                    "projetos": projetos,
                    "status": status_list,
                    "prioridades": prio_list
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        else:
            self._send_json({"error": "Rota não encontrada"}, 404)

    def _send_json(self, data, status=200):
        response = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-User-Id')
        self.end_headers()
        self.wfile.write(response)

if __name__ == "__main__":
    init_db()
    check_recurrence()
    threading.Thread(target=recurrence_background_loop, daemon=True).start()

    print("=" * 60)
    print("   🚀 ASSISTENTE PESSOAL CLOUD (SQLite + Vault) - ARPEGO")
    print("=" * 60)
    print(f"Servidor ouvindo na porta {PORT}...")
    print(f"Banco SQLite ativo em: {DB_FILE}")
    print("Regra de recorrência: Corte diário às 04:00 (Brasília)")
    print("=" * 60)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), CloudAssistantHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor encerrado.")
