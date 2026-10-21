# -*- coding: utf-8 -*-
"""
Adicionar Tarefa #024 (Follow UP sem EIC - IFF Argentina) e Sincronizar em Lote Único
"""

import sys
import os
import json
import sqlite3
import urllib.request
import subprocess
from datetime import datetime, timezone, timedelta

TZ_BR = timezone(timedelta(hours=-3))

def get_now_br():
    return datetime.now(timezone.utc).astimezone(TZ_BR).replace(tzinfo=None)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from app_windows import get_db_connection, CLOUD_URL

def main():
    print("=" * 65)
    print("🚀 CADASTRO TAREFA #024 (FOLLOW UP SEM EIC) + SINCRONIZAÇÃO")
    print("=" * 65)

    now_br = get_now_br()
    now_str = now_br.strftime('%Y-%m-%d %H:%M:%S')

    tarefa_024 = {
        "codigo": "#024",
        "projeto": "IFF Argentina",
        "id_projeto": 3,
        "titulo": "Criação do Follow UP sem EIC - Novo módulo de importação",
        "tipo": "Profissional",
        "prioridade": "Alta",
        "status": "Em andamento",
        "observacoes": "Desenvolver e estruturar novo módulo de importação para gerar o Follow Up sem dependência do SAP EIC.",
        "recorrencia_dias": 0,
        "data_conclusao": None,
        "data_recorrencia": None,
        "ultima_atualizacao": now_str
    }

    # 1. SQL Server Local
    conn_sql = get_db_connection()
    if conn_sql:
        try:
            cur_sql = conn_sql.cursor()
            cur_sql.execute("SET DATEFORMAT ymd;")
            # Garante projeto IFF Argentina
            cur_sql.execute("SELECT id FROM tb_projetos WHERE LOWER(nome) = 'iff argentina';")
            row_p = cur_sql.fetchone()
            proj_id = row_p[0] if row_p else 3

            cur_sql.execute("SELECT id FROM tb_tarefas WHERE codigo = '#024';")
            if cur_sql.fetchone():
                cur_sql.execute("""
                UPDATE tb_tarefas 
                SET id_projeto = ?, titulo = ?, tipo = ?, prioridade = ?, status = ?, observacoes = ?, ultima_atualizacao = ?, sync_pendente = 1
                WHERE codigo = '#024';
                """, (proj_id, tarefa_024["titulo"], tarefa_024["tipo"], tarefa_024["prioridade"], tarefa_024["status"], tarefa_024["observacoes"], now_br))
            else:
                cur_sql.execute("""
                INSERT INTO tb_tarefas (codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, recorrencia_dias, sync_pendente, ultima_atualizacao)
                VALUES ('#024', ?, ?, ?, ?, ?, ?, 0, 1, ?);
                """, (proj_id, tarefa_024["titulo"], tarefa_024["tipo"], tarefa_024["prioridade"], tarefa_024["status"], tarefa_024["observacoes"], now_br))

            cur_sql.execute("""
            INSERT INTO tb_historico (codigo_tarefa, descricao, data_hora)
            VALUES ('#024', 'Nova tarefa criada em paralelo: Criação do Follow UP sem EIC', ?);
            """, (now_br,))

            conn_sql.commit()
            conn_sql.close()
            print("✅ SQL Server local atualizado com #024!")
        except Exception as e:
            print(f"⚠️ Erro SQL Server: {e}")
    else:
        print("ℹ️ SQL Server não conectado.")

    # 2. SQLite Local (assistpe.db)
    db_file = os.path.join(BASE_DIR, "assistpe.db")
    if os.path.exists(db_file):
        try:
            conn_lite = sqlite3.connect(db_file)
            cur_lite = conn_lite.cursor()
            cur_lite.execute("SELECT id FROM tb_projetos WHERE LOWER(nome) = 'iff argentina';")
            row_pl = cur_lite.fetchone()
            proj_id_lite = row_pl[0] if row_pl else 3

            cur_lite.execute("SELECT id FROM tb_tarefas WHERE id_usuario = 1 AND codigo = '#024';")
            if cur_lite.fetchone():
                cur_lite.execute("""
                UPDATE tb_tarefas 
                SET id_projeto = ?, titulo = ?, tipo = ?, prioridade = ?, status = ?, observacoes = ?, ultima_atualizacao = ?
                WHERE id_usuario = 1 AND codigo = '#024';
                """, (proj_id_lite, tarefa_024["titulo"], tarefa_024["tipo"], tarefa_024["prioridade"], tarefa_024["status"], tarefa_024["observacoes"], now_str))
            else:
                cur_lite.execute("""
                INSERT INTO tb_tarefas (id_usuario, codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, recorrencia_dias, ultima_atualizacao)
                VALUES (1, '#024', ?, ?, ?, ?, ?, ?, 0, ?);
                """, (proj_id_lite, tarefa_024["titulo"], tarefa_024["tipo"], tarefa_024["prioridade"], tarefa_024["status"], tarefa_024["observacoes"], now_str))

            cur_lite.execute("""
            INSERT INTO tb_historico (id_usuario, codigo_tarefa, descricao)
            VALUES (1, '#024', 'Nova tarefa criada em paralelo: Criação do Follow UP sem EIC');
            """)
            conn_lite.commit()
            conn_lite.close()
            print("✅ SQLite local (assistpe.db) atualizado com #024!")
        except Exception as e:
            print(f"⚠️ Erro SQLite: {e}")

    # 3. seed_tarefas.json
    seed_file = os.path.join(BASE_DIR, "seed_tarefas.json")
    if os.path.exists(seed_file):
        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                seed_data = json.load(f)
            tarefas_list = seed_data.get("tarefas", [])
            existing = False
            for t in tarefas_list:
                if t.get("codigo") == "#024":
                    t.update(tarefa_024)
                    existing = True
                    break
            if not existing:
                tarefas_list.append(tarefa_024)
            seed_data["total_tarefas"] = len(tarefas_list)
            seed_data["exportado_em"] = now_str
            with open(seed_file, "w", encoding="utf-8") as f:
                json.dump(seed_data, f, ensure_ascii=False, indent=2)
            print("✅ seed_tarefas.json atualizado com #024!")
        except Exception as e:
            print(f"⚠️ Erro seed_tarefas.json: {e}")

    # 4. Envia para a Nuvem Render via /api/sync
    print("\n☁️ Enviando #024 para o Hub da Nuvem...")
    try:
        changes = [
            {
                "action": "nova",
                "codigo": "#024",
                "titulo": tarefa_024["titulo"],
                "projeto": tarefa_024["projeto"],
                "tipo": tarefa_024["tipo"],
                "prioridade": tarefa_024["prioridade"],
                "status": tarefa_024["status"],
                "observacoes": tarefa_024["observacoes"],
                "timestamp": now_str
            }
        ]
        sync_payload = json.dumps({"client_id": "cli-batch", "changes": changes, "tarefas": [tarefa_024]}).encode('utf-8')
        req = urllib.request.Request(
            f"{CLOUD_URL.rstrip('/')}/api/sync",
            data=sync_payload,
            headers={"Content-Type": "application/json", "X-User-Id": "1"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            sync_res = json.loads(resp.read().decode('utf-8'))
        if sync_res.get("success"):
            print(f"✅ Nuvem sincronizada! (Alterações aplicadas: {sync_res.get('applied_changes')})")
        else:
            print(f"⚠️ Aviso Nuvem: {sync_res}")
    except Exception as e:
        print(f"⚠️ Erro sync Nuvem: {e}")

    # 5. Git Commit & Push
    print("\n📦 Versionando no Git...")
    try:
        subprocess.run(["git", "add", "seed_tarefas.json", "adicionar_tarefa_024.py"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "commit", "-m", "feat(iff): cadastrar tarefa paralela #024 (Follow UP sem EIC)"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=False)
    except Exception as e:
        print(f"Aviso Git: {e}")

    print("\n" + "=" * 65)
    print("🎉 TAREFA #024 CRIADA E SINCRONIZADA EM TODAS AS BASES!")
    print("=" * 65)

if __name__ == '__main__':
    main()
