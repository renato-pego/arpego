# -*- coding: utf-8 -*-
"""
=============================================================================
Assistente Pessoal - ARPego: Módulo de Monitoramento de E-mails (Outlook MAPI)
=============================================================================
Funcionalidades:
1. Conecta ao Microsoft Outlook Desktop via MAPI (sessão já logada).
2. Varre todas as contas e caixas de entrada configuradas.
3. Associa mensagens a tarefas existentes com base em palavras-chave e remetentes.
4. Gera apontamentos automáticos no histórico das tarefas vinculadas.
5. Identifica solicitações de novas demandas e cria sugestões para aprovação.
6. Calcula SLA de resposta para e-mails aguardando retorno (Atenção >2h, Alerta >4h, Crítico >8h).
7. Mantém tabelas tb_emails_monitorados e tb_sugestoes_tarefas no SQL Server e SQLite.
"""

import sys
import os
import json
import sqlite3
import re
from datetime import datetime, timezone, timedelta, date

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

TZ_BR = timezone(timedelta(hours=-3))

def get_now_br():
    return datetime.now(timezone.utc).astimezone(TZ_BR).replace(tzinfo=None)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from app_windows import get_db_connection
except ImportError:
    def get_db_connection():
        return None

# ==================== CRIAÇÃO / MIGRAÇÃO DE TABELAS ====================

def init_email_tables():
    """Garante as tabelas de monitoramento de e-mails no SQL Server e nos bancos SQLite."""
    # 1. SQL Server
    conn_sql = get_db_connection()
    if conn_sql:
        try:
            cur = conn_sql.cursor()
            cur.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_emails_monitorados')
            BEGIN
                CREATE TABLE tb_emails_monitorados (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    entry_id NVARCHAR(255) NOT NULL UNIQUE,
                    conta NVARCHAR(150) NULL,
                    remetente NVARCHAR(255) NULL,
                    remetente_email NVARCHAR(255) NULL,
                    assunto NVARCHAR(500) NULL,
                    data_recebimento DATETIME NULL,
                    codigo_tarefa_vinculada NVARCHAR(20) NULL,
                    status_processamento NVARCHAR(50) DEFAULT 'Aguardando',
                    precisa_resposta BIT DEFAULT 0,
                    respondido BIT DEFAULT 0,
                    horas_sem_resposta FLOAT DEFAULT 0,
                    sla_status NVARCHAR(50) DEFAULT 'Normal',
                    corpo_resumo NVARCHAR(MAX) NULL,
                    data_processamento DATETIME DEFAULT GETDATE()
                );
            END
            """)

            cur.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_sugestoes_tarefas')
            BEGIN
                CREATE TABLE tb_sugestoes_tarefas (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    email_entry_id NVARCHAR(255) NULL,
                    titulo NVARCHAR(255) NOT NULL,
                    projeto NVARCHAR(150) NULL,
                    prioridade NVARCHAR(50) DEFAULT 'Média',
                    tipo NVARCHAR(50) DEFAULT 'Profissional',
                    resumo NVARCHAR(MAX) NULL,
                    status NVARCHAR(50) DEFAULT 'Pendente',
                    data_criacao DATETIME DEFAULT GETDATE()
                );
            END
            """)
            conn_sql.commit()
            conn_sql.close()
            print("✅ [SQL Server] Tabelas de e-mails verificadas com sucesso.")
        except Exception as e:
            print(f"⚠️ [SQL Server] Erro ao criar tabelas de e-mails: {e}")

    # 2. SQLite (assistpe.db e assistpe_desktop.db)
    for db_name in ("assistpe.db", "assistpe_desktop.db"):
        db_path = os.path.join(BASE_DIR, db_name)
        try:
            conn_lite = sqlite3.connect(db_path)
            cur = conn_lite.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_emails_monitorados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT UNIQUE NOT NULL,
                conta TEXT,
                remetente TEXT,
                remetente_email TEXT,
                assunto TEXT,
                data_recebimento TEXT,
                codigo_tarefa_vinculada TEXT,
                status_processamento TEXT DEFAULT 'Aguardando',
                precisa_resposta INTEGER DEFAULT 0,
                respondido INTEGER DEFAULT 0,
                horas_sem_resposta REAL DEFAULT 0,
                sla_status TEXT DEFAULT 'Normal',
                corpo_resumo TEXT,
                data_processamento TEXT
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_sugestoes_tarefas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_entry_id TEXT,
                titulo TEXT NOT NULL,
                projeto TEXT,
                prioridade TEXT DEFAULT 'Média',
                tipo TEXT DEFAULT 'Profissional',
                resumo TEXT,
                status TEXT DEFAULT 'Pendente',
                data_criacao TEXT
            );
            """)
            conn_lite.commit()
            conn_lite.close()
            print(f"✅ [SQLite] Tabelas de e-mails verificadas em {db_name}.")
        except Exception as e:
            print(f"⚠️ [SQLite] Erro em {db_name}: {e}")

# ==================== MAPAS DE PALAVRAS-CHAVE E CLIENTES ====================

PALAVRAS_CHAVE_TAREFAS = [
    {
        "codigo": "#024",
        "cliente": "Boa",
        "termos": ["follow up", "followup", "sem eic", "modulo de importacao", "módulo de importação", "boa", "boasupermercados"]
    },
    {
        "codigo": "#025",
        "cliente": "IFF Brasil / México",
        "termos": ["interface de pedido", "interface pedido", "erro pedido", "refatorar abap", "pedido sap", "pedido de venda", "sales order"]
    },
    {
        "codigo": "#026",
        "cliente": "IFF Brasil / México",
        "termos": ["krom", "txt da krom", "txt krom", "carga do txt", "carga txt", "despachante"]
    },
    {
        "codigo": "#003",
        "cliente": "IFF Argentina",
        "termos": ["condition zs", "zs", "argentina", "data de chegada", "calculo zs", "cálculo zs"]
    },
    {
        "codigo": "#004",
        "cliente": "IFF Brasil / México",
        "termos": ["material no e-mail", "descricao do material", "codigo do material"]
    },
    {
        "codigo": "#007",
        "cliente": "IFF México",
        "termos": ["joel", "lancamentos contabeis", "lançamentos contábeis", "cfin"]
    },
    {
        "codigo": "#018",
        "cliente": "Caldic",
        "termos": ["caldic", "atualizar producao", "atualizar produção", "deploy producao"]
    },
    {
        "codigo": "#022",
        "cliente": "Caldic",
        "termos": ["posicao", "posição", "integracao de pedidos", "integração de pedidos"]
    },
    {
        "codigo": "#015",
        "cliente": "Unimed",
        "termos": ["unimed", "mv", "interface de fornecedores", "fornecedores mv"]
    },
    {
        "codigo": "#016",
        "cliente": "Unimed",
        "termos": ["unimed", "nf com 2 pedidos", "dois pedidos", "duplo pedido"]
    }
]

TERMOS_NOVA_DEMANDA = [
    "favor verificar", "por favor verificar", "solicito", "urgente", "novo chamado",
    "erro em producao", "erro em produção", "falha na interface", "novo ajuste",
    "novo pedido", "necessidade", "ajuste solicitado", "ticket", "chamado", "incidente"
]

def identificar_tarefa(assunto, corpo, remetente):
    """Correlaciona o e-mail com tarefas ativas."""
    texto = f"{assunto} {corpo} {remetente}".lower()
    for item in PALAVRAS_CHAVE_TAREFAS:
        for termo in item["termos"]:
            if termo in texto:
                return item["codigo"], item["cliente"]
    return None, None

def identificar_potencial_nova_tarefa(assunto, corpo):
    """Detecta se uma mensagem não vinculada contém padrões de nova solicitação."""
    texto = f"{assunto} {corpo}".lower()
    for termo in TERMOS_NOVA_DEMANDA:
        if termo in texto:
            return True, termo
    return False, None

# ==================== LEITURA DE E-MAILS DO OUTLOOK ====================

def conectar_outlook():
    """Conecta à instância do Outlook Desktop via COM MAPI."""
    # Garante inclusão de diretórios de DLL do pywin32 se necessário
    for p in sys.path:
        sys32_dir = os.path.join(p, "pywin32_system32")
        if os.path.isdir(sys32_dir):
            if sys32_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = sys32_dir + os.pathsep + os.environ.get("PATH", "")
            if sys32_dir not in sys.path:
                sys.path.insert(0, sys32_dir)
            try:
                os.add_dll_directory(sys32_dir)
            except Exception:
                pass
            break

    try:
        import win32com.client
    except (ImportError, ModuleNotFoundError):
        import subprocess
        print("Ajustando instalação pywin32...")
        py_exe = sys.executable
        post_script = os.path.join(os.path.dirname(py_exe), "Scripts", "pywin32_postinstall.py")
        if os.path.exists(post_script):
            subprocess.run([py_exe, post_script, "-install"], check=False)
        else:
            subprocess.run([py_exe, "-m", "pip", "install", "--upgrade", "pywin32"], check=False)
        import win32com.client

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        return outlook, namespace
    except Exception as e:
        print(f"⚠️ Não foi possível conectar ao Outlook Application: {e}")
        return None, None

def escanear_caixas_outlook(horas_atras=360, limite_por_pasta=1000):
    """
    Varre as Caixas de Entrada de todas as contas configuradas no Outlook.
    Retorna uma lista de e-mails normalizados.
    """
    outlook, namespace = conectar_outlook()
    if not namespace:
        return []

    now_br = get_now_br()
    limite_data = now_br - timedelta(hours=horas_atras)
    emails_encontrados = []

    print(f"\n🔍 Iniciando varredura das contas no Outlook (Últimos {horas_atras // 24} dias / {horas_atras}h)...")

    try:
        # Itera por todas as Stores (Contas de e-mail / Arquivos de dados)
        stores = namespace.Stores
        print(f"📦 Total de perfis/contas detectadas no Outlook: {stores.Count}")

        for i in range(1, stores.Count + 1):
            store = stores.Item(i)
            nome_conta = store.DisplayName
            print(f"   📂 Verificando conta: [{nome_conta}]")

            try:
                # Pasta 6 = olFolderInbox (Caixa de Entrada oficial da Store)
                inbox = store.GetDefaultFolder(6)
            except Exception:
                try:
                    # Alternativa: procurar pasta chamada 'Inbox' ou 'Caixa de Entrada'
                    root = store.GetRootFolder()
                    inbox = None
                    for f in root.Folders:
                        if f.Name.lower() in ('caixa de entrada', 'inbox', 'mensagens recebidas'):
                            inbox = f
                            break
                    if not inbox:
                        continue
                except Exception:
                    continue

            # Acessa os itens da Caixa de Entrada ordenados por data decrescente
            try:
                items = inbox.Items
                items.Sort("[ReceivedTime]", True)
            except Exception:
                items = inbox.Items

            contagem = 0
            for item in items:
                contagem += 1
                if contagem > limite_por_pasta:
                    break

                try:
                    # Verifica se é uma mensagem de correio eletrônico
                    if item.Class != 43: # 43 = olMail
                        continue

                    recv_time = item.ReceivedTime
                    # Converte recv_time para datetime naive BRT
                    if hasattr(recv_time, 'year'):
                        dt_recv = datetime(recv_time.year, recv_time.month, recv_time.day,
                                           recv_time.hour, recv_time.minute, recv_time.second)
                    else:
                        continue

                    if dt_recv < limite_data:
                        # Como está ordenado decrescente, itens seguintes serão mais antigos
                        break

                    entry_id = str(item.EntryID)
                    assunto = str(item.Subject or "(Sem Assunto)").strip()
                    corpo = str(item.Body or "").strip()[:1000] # Primeiros 1000 caracteres

                    remetente_nome = ""
                    remetente_email = ""
                    try:
                        remetente_nome = str(item.SenderName or "")
                        remetente_email = str(item.SenderEmailAddress or "")
                    except Exception:
                        pass

                    nao_lido = bool(item.UnRead)
                    
                    # Verifica se o e-mail foi respondido (propriedade PR_LAST_VERB_EXECUTED = 102 para reply, 103 reply all)
                    foi_respondido = False
                    try:
                        # 0x10810003 = PidTagLastVerbExecuted
                        prop_val = item.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x10810003")
                        if prop_val in (102, 103):
                            foi_respondido = True
                    except Exception:
                        pass

                    # Cálculo do tempo sem resposta
                    horas_sem_resp = (now_br - dt_recv).total_seconds() / 3600.0

                    emails_encontrados.append({
                        "entry_id": entry_id,
                        "conta": nome_conta,
                        "remetente": remetente_nome,
                        "remetente_email": remetente_email,
                        "assunto": assunto,
                        "corpo": corpo,
                        "data_recebimento": dt_recv,
                        "nao_lido": nao_lido,
                        "foi_respondido": foi_respondido,
                        "horas_sem_resposta": round(horas_sem_resp, 1)
                    })
                except Exception as err_item:
                    continue

    except Exception as e:
        print(f"⚠️ Erro ao iterar caixas do Outlook: {e}")

    print(f"📧 Total de mensagens recentes capturadas: {len(emails_encontrados)}")
    return emails_encontrados

# ==================== PROCESSAMENTO E INTELIGÊNCIA ====================

def processar_emails(horas_atras=360, limite_por_pasta=1000):
    """
    Executa a leitura, classificação, vinculação e cálculo de SLA dos e-mails.
    Grava os resultados no banco de dados e aponta no histórico das tarefas.
    """
    init_email_tables()
    mensagens = escanear_caixas_outlook(horas_atras=horas_atras, limite_por_pasta=limite_por_pasta)
    if not mensagens:
        print("ℹ️ Nenhuma mensagem nova para processar ou Outlook não estava disponível.")
        return {"total": 0, "vinculados": 0, "sugestoes": 0, "sla_atencao": 0}

    now_br = get_now_br()
    now_str = now_br.strftime('%Y-%m-%d %H:%M:%S')

    # Busca tarefas ativas para referência
    tarefas_vinculadas_count = 0
    sugestoes_count = 0
    sla_atencao_count = 0

    conn_sql = get_db_connection()
    db_lite = os.path.join(BASE_DIR, "assistpe.db")
    conn_lite = sqlite3.connect(db_lite) if os.path.exists(db_lite) else None

    print("\n🧠 Analisando mensagens e correlacionando com tarefas ativas...")

    for msg in mensagens:
        entry_id = msg["entry_id"]
        assunto = msg["assunto"]
        corpo = msg["corpo"]
        remetente = msg["remetente"]
        horas_sem_resp = msg["horas_sem_resposta"]
        foi_resp = msg["foi_respondido"]

        # Calcula status do SLA
        if foi_resp:
            sla_status = "Respondido"
            precisa_resposta = 0
        else:
            precisa_resposta = 1
            if horas_sem_resp > 8.0:
                sla_status = "Crítico (>8h)"
                sla_atencao_count += 1
            elif horas_sem_resp > 4.0:
                sla_status = "Alerta (>4h)"
                sla_atencao_count += 1
            elif horas_sem_resp > 2.0:
                sla_status = "Atenção (>2h)"
                sla_atencao_count += 1
            else:
                sla_status = "Recente (<2h)"

        # 1. Tenta identificar se pertence a uma tarefa existente
        cod_tarefa, cliente = identificar_tarefa(assunto, corpo, remetente)

        # 2. Se não pertence a tarefa existente, avalia se é nova demanda
        potencial_nova = False
        termo_achado = None
        if not cod_tarefa:
            potencial_nova, termo_achado = identificar_potencial_nova_tarefa(assunto, corpo)

        status_proc = "Vinculado" if cod_tarefa else ("Sugestão" if potencial_nova else "Geral")

        # Registro / Atualização no SQLite
        if conn_lite:
            try:
                cur_l = conn_lite.cursor()
                cur_l.execute("SELECT id, status_processamento FROM tb_emails_monitorados WHERE entry_id = ?", (entry_id,))
                row = cur_l.fetchone()
                dt_rec_str = msg["data_recebimento"].strftime('%Y-%m-%d %H:%M:%S')

                if not row:
                    cur_l.execute("""
                    INSERT INTO tb_emails_monitorados (
                        entry_id, conta, remetente, remetente_email, assunto, data_recebimento,
                        codigo_tarefa_vinculada, status_processamento, precisa_resposta, respondido,
                        horas_sem_resposta, sla_status, corpo_resumo, data_processamento
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        entry_id, msg["conta"], remetente, msg["remetente_email"], assunto, dt_rec_str,
                        cod_tarefa, status_proc, precisa_resposta, int(foi_resp),
                        horas_sem_resp, sla_status, corpo[:300], now_str
                    ))

                    # Se vinculou a uma tarefa, adiciona no histórico da tarefa
                    if cod_tarefa:
                        cur_l.execute("""
                        INSERT INTO tb_historico (id_usuario, codigo_tarefa, descricao)
                        VALUES (1, ?, ?)
                        """, (cod_tarefa, f"📧 [Outlook] E-mail de '{remetente}': '{assunto[:80]}' ({dt_rec_str})"))
                        tarefas_vinculadas_count += 1

                    # Se identificou como sugestão de nova tarefa
                    if potencial_nova:
                        cur_l.execute("""
                        INSERT INTO tb_sugestoes_tarefas (
                            email_entry_id, titulo, projeto, prioridade, resumo, status, data_criacao
                        ) VALUES (?, ?, ?, 'Alta' if 'urgente' in assunto.lower() else 'Média', ?, 'Pendente', ?)
                        """, (entry_id, f"Analisar: {assunto[:80]}", cliente or "Geral", f"Detectado via e-mail de {remetente}. Termo: '{termo_achado}'.", now_str))
                        sugestoes_count += 1
                else:
                    # Atualiza SLA e status de resposta
                    cur_l.execute("""
                    UPDATE tb_emails_monitorados
                    SET respondido = ?, horas_sem_resposta = ?, sla_status = ?
                    WHERE entry_id = ?
                    """, (int(foi_resp), horas_sem_resp, sla_status, entry_id))

                conn_lite.commit()
            except Exception as e:
                pass

        # Registro / Atualização no SQL Server
        if conn_sql:
            try:
                cur_s = conn_sql.cursor()
                cur_s.execute("SELECT id FROM tb_emails_monitorados WHERE entry_id = ?", (entry_id,))
                if not cur_s.fetchone():
                    cur_s.execute("""
                    INSERT INTO tb_emails_monitorados (
                        entry_id, conta, remetente, remetente_email, assunto, data_recebimento,
                        codigo_tarefa_vinculada, status_processamento, precisa_resposta, respondido,
                        horas_sem_resposta, sla_status, corpo_resumo, data_processamento
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        entry_id, msg["conta"], remetente, msg["remetente_email"], assunto, msg["data_recebimento"],
                        cod_tarefa, status_proc, precisa_resposta, int(foi_resp),
                        horas_sem_resp, sla_status, corpo[:300], now_br
                    ))
                    if cod_tarefa:
                        cur_s.execute("""
                        INSERT INTO tb_historico (codigo_tarefa, descricao, data_hora)
                        VALUES (?, ?, ?)
                        """, (cod_tarefa, f"📧 [Outlook] E-mail de '{remetente}': '{assunto[:80]}'", now_br))
                else:
                    cur_s.execute("""
                    UPDATE tb_emails_monitorados
                    SET respondido = ?, horas_sem_resposta = ?, sla_status = ?
                    WHERE entry_id = ?
                    """, (int(foi_resp), horas_sem_resp, sla_status, entry_id))
                conn_sql.commit()
            except Exception as e:
                pass

    if conn_lite:
        conn_lite.close()
    if conn_sql:
        conn_sql.close()

    print("\n" + "=" * 65)
    print("🎯 RELATÓRIO DO MONITOR DE E-MAILS")
    print("=" * 65)
    print(f"📩 Total de mensagens varridas: {len(mensagens)}")
    print(f"🔗 Apontamentos vinculados a tarefas ativas: {tarefas_vinculadas_count}")
    print(f"💡 Novas tarefas sugeridas para aprovação: {sugestoes_count}")
    print(f"⏰ E-mails em alerta de SLA (>2h sem retorno): {sla_atencao_count}")
    print("=" * 65)

    return {
        "total": len(mensagens),
        "vinculados": tarefas_vinculadas_count,
        "sugestoes": sugestoes_count,
        "sla_atencao": sla_atencao_count
    }

def obter_dados_emails_painel():
    """Retorna lista de e-mails monitorados e métricas para a interface."""
    conn_sql = get_db_connection()
    use_sql = True if conn_sql else False
    if not conn_sql:
        db_path = os.path.join(BASE_DIR, "assistpe.db")
        if not os.path.exists(db_path):
            db_path = os.path.join(BASE_DIR, "assistpe_desktop.db")
        conn = sqlite3.connect(db_path) if os.path.exists(db_path) else None
    else:
        conn = conn_sql

    if not conn:
        return {"emails": [], "metricas": {"total": 0, "critico": 0, "alerta": 0, "atencao": 0, "vinculados": 0}}

    cur = conn.cursor()
    query = """
    SELECT id, entry_id, conta, remetente, remetente_email, assunto, 
           data_recebimento, codigo_tarefa_vinculada, status_processamento, 
           precisa_resposta, respondido, horas_sem_resposta, sla_status, corpo_resumo
    FROM tb_emails_monitorados
    ORDER BY precisa_resposta DESC, horas_sem_resposta DESC, id DESC;
    """
    try:
        cur.execute(query)
        rows = cur.fetchall()
        emails = []
        critico = 0
        alerta = 0
        atencao = 0
        vinculados = 0

        for r in rows:
            precisa = bool(r[9])
            respondido = bool(r[10])
            horas = float(r[11] or 0)
            sla = str(r[12] or "Normal")
            cod_tarefa = str(r[7] or "")

            if cod_tarefa:
                vinculados += 1
            if precisa and not respondido:
                if horas > 8.0:
                    critico += 1
                elif horas > 4.0:
                    alerta += 1
                elif horas > 2.0:
                    atencao += 1

            emails.append({
                "id": r[0],
                "entry_id": r[1],
                "conta": r[2],
                "remetente": r[3],
                "remetente_email": r[4],
                "assunto": r[5],
                "data_recebimento": str(r[6]),
                "codigo_tarefa_vinculada": cod_tarefa,
                "status_processamento": r[8],
                "precisa_resposta": precisa,
                "respondido": respondido,
                "horas_sem_resposta": horas,
                "sla_status": sla,
                "corpo_resumo": r[13]
            })

        conn.close()
        return {
            "emails": emails,
            "metricas": {
                "total": len(emails),
                "critico": critico,
                "alerta": alerta,
                "atencao": atencao,
                "vinculados": vinculados
            }
        }
    except Exception as e:
        conn.close()
        return {"emails": [], "error": str(e), "metricas": {"total": 0, "critico": 0, "alerta": 0, "atencao": 0, "vinculados": 0}}

def marcar_email_respondido(entry_id):
    """Marca um e-mail como respondido manualmente no SQL Server e SQLite."""
    conn_sql = get_db_connection()
    if conn_sql:
        try:
            cur = conn_sql.cursor()
            cur.execute("""
            UPDATE tb_emails_monitorados 
            SET respondido = 1, precisa_resposta = 0, sla_status = 'Respondido'
            WHERE entry_id = ?;
            """, (entry_id,))
            conn_sql.commit()
            conn_sql.close()
        except Exception:
            pass

    for db_name in ("assistpe.db", "assistpe_desktop.db"):
        db_path = os.path.join(BASE_DIR, db_name)
        if os.path.exists(db_path):
            try:
                conn_lite = sqlite3.connect(db_path)
                cur = conn_lite.cursor()
                cur.execute("""
                UPDATE tb_emails_monitorados 
                SET respondido = 1, precisa_resposta = 0, sla_status = 'Respondido'
                WHERE entry_id = ?;
                """, (entry_id,))
                conn_lite.commit()
                conn_lite.close()
            except Exception:
                pass
    return True

def obter_sugestoes_pendentes():
    """Retorna sugestões de novas tarefas aguardando aprovação."""
    conn_sql = get_db_connection()
    conn = conn_sql if conn_sql else None
    if not conn:
        db_path = os.path.join(BASE_DIR, "assistpe.db")
        if not os.path.exists(db_path):
            db_path = os.path.join(BASE_DIR, "assistpe_desktop.db")
        conn = sqlite3.connect(db_path) if os.path.exists(db_path) else None

    if not conn:
        return []

    cur = conn.cursor()
    try:
        cur.execute("""
        SELECT id, email_entry_id, titulo, projeto, prioridade, tipo, resumo, status, data_criacao
        FROM tb_sugestoes_tarefas
        WHERE status = 'Pendente'
        ORDER BY id DESC;
        """)
        rows = cur.fetchall()
        sugestoes = []
        for r in rows:
            sugestoes.append({
                "id": r[0],
                "email_entry_id": r[1],
                "titulo": r[2],
                "projeto": r[3],
                "prioridade": r[4],
                "tipo": r[5],
                "resumo": r[6],
                "status": r[7],
                "data_criacao": str(r[8])
            })
        conn.close()
        return sugestoes
    except Exception:
        conn.close()
        return []

def descartar_sugestao(sugestao_id):
    """Marca sugestão como descartada."""
    conn_sql = get_db_connection()
    if conn_sql:
        try:
            cur = conn_sql.cursor()
            cur.execute("UPDATE tb_sugestoes_tarefas SET status = 'Descartada' WHERE id = ?;", (sugestao_id,))
            conn_sql.commit()
            conn_sql.close()
        except Exception:
            pass

    for db_name in ("assistpe.db", "assistpe_desktop.db"):
        db_path = os.path.join(BASE_DIR, db_name)
        if os.path.exists(db_path):
            try:
                conn_lite = sqlite3.connect(db_path)
                cur = conn_lite.cursor()
                cur.execute("UPDATE tb_sugestoes_tarefas SET status = 'Descartada' WHERE id = ?;", (sugestao_id,))
                conn_lite.commit()
                conn_lite.close()
            except Exception:
                pass
    return True

if __name__ == '__main__':
    print("🚀 Varredura Ampliada de E-mails ARPego (Últimos 15 dias / 360h)")
    processar_emails(horas_atras=360, limite_por_pasta=1000)
