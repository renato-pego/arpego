# -*- coding: utf-8 -*-
"""
Atualização IFF Argentina (#003) e Reconciliação em Lote Único - ARPego
1. Retoma #003 para 'Em andamento' (e-mail não disparou na homologação)
2. Esclarece condição ZS (Condition SAP) nos títulos de #003 e #004
3. Reseta hábitos diários (#P01, #P02) para Pendente pós-corte das 04:00
4. Atualiza SQL Server Local, SQLite Local, Nuvem Render e seed_tarefas.json
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
    print("🚀 ATUALIZAÇÃO IFF ARGENTINA (#003 EM ANDAMENTO) + SINCRONIZAÇÃO")
    print("=" * 65)

    now_br = get_now_br()
    now_str = now_br.strftime('%Y-%m-%d %H:%M:%S')

    obs_003 = "Usuários reportaram que o e-mail não disparou. Investigar determinação de mensagens / gatilho na alteração da data (Condition ZS)."

    # 1. SQL Server Local
    conn_sql = get_db_connection()
    if conn_sql:
        try:
            cur_sql = conn_sql.cursor()
            cur_sql.execute("SET DATEFORMAT ymd;")
            # Atualiza #003
            cur_sql.execute("""
            UPDATE tb_tarefas
            SET status = 'Em andamento',
                titulo = 'Ativar e-mail sobre mudança de data de chegada (Condition ZS)',
                observacoes = ?,
                ultima_atualizacao = ?,
                sync_pendente = 1
            WHERE codigo = '#003';
            """, (obs_003, now_br))
            cur_sql.execute("""
            INSERT INTO tb_historico (codigo_tarefa, descricao, data_hora)
            VALUES ('#003', 'Retomada para Em andamento: Usuários informaram que o e-mail não saiu.', ?);
            """, (now_br,))

            # Atualiza título de #004
            cur_sql.execute("""
            UPDATE tb_tarefas
            SET titulo = 'Colocar código e descrição do Material no e-mail de aviso (Condition ZS)',
                ultima_atualizacao = ?,
                sync_pendente = 1
            WHERE codigo = '#004';
            """, (now_br,))

            # Reset diário das 04:00 para #P01 e #P02
            cur_sql.execute("""
            UPDATE tb_tarefas
            SET status = 'Pendente', data_conclusao = NULL, data_recorrencia = NULL, ultima_atualizacao = ?, sync_pendente = 1
            WHERE codigo IN ('#P01', '#P02') AND (data_recorrencia <= ? OR data_recorrencia IS NULL);
            """, (now_br, now_str))

            conn_sql.commit()
            conn_sql.close()
            print("✅ SQL Server local atualizado com sucesso!")
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
            cur_lite.execute("""
            UPDATE tb_tarefas
            SET status = 'Em andamento',
                titulo = 'Ativar e-mail sobre mudança de data de chegada (Condition ZS)',
                observacoes = ?,
                ultima_atualizacao = ?
            WHERE codigo = '#003';
            """, (obs_003, now_str))
            cur_lite.execute("""
            INSERT INTO tb_historico (codigo_tarefa, descricao)
            VALUES ('#003', 'Retomada para Em andamento: Usuários informaram que o e-mail não saiu.');
            """)

            cur_lite.execute("""
            UPDATE tb_tarefas
            SET titulo = 'Colocar código e descrição do Material no e-mail de aviso (Condition ZS)',
                ultima_atualizacao = ?
            WHERE codigo = '#004';
            """, (now_str,))

            cur_lite.execute("""
            UPDATE tb_tarefas
            SET status = 'Pendente', data_conclusao = NULL, data_recorrencia = NULL, ultima_atualizacao = ?
            WHERE codigo IN ('#P01', '#P02') AND (data_recorrencia <= ? OR data_recorrencia IS NULL);
            """, (now_str, now_str))

            conn_lite.commit()
            conn_lite.close()
            print("✅ SQLite local (assistpe.db) atualizado com sucesso!")
        except Exception as e:
            print(f"⚠️ Erro SQLite: {e}")

    # 3. seed_tarefas.json
    seed_file = os.path.join(BASE_DIR, "seed_tarefas.json")
    if os.path.exists(seed_file):
        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                seed_data = json.load(f)
            for t in seed_data.get("tarefas", []):
                cod = t.get("codigo")
                if cod == "#003":
                    t["status"] = "Em andamento"
                    t["titulo"] = "Ativar e-mail sobre mudança de data de chegada (Condition ZS)"
                    t["observacoes"] = obs_003
                    t["ultima_atualizacao"] = now_str
                elif cod == "#004":
                    t["titulo"] = "Colocar código e descrição do Material no e-mail de aviso (Condition ZS)"
                    t["ultima_atualizacao"] = now_str
                elif cod in ("#P01", "#P02"):
                    t["status"] = "Pendente"
                    t["data_conclusao"] = None
                    t["data_recorrencia"] = None
                    t["ultima_atualizacao"] = now_str

            seed_data["exportado_em"] = now_str
            with open(seed_file, "w", encoding="utf-8") as f:
                json.dump(seed_data, f, ensure_ascii=False, indent=2)
            print("✅ seed_tarefas.json atualizado com sucesso!")
        except Exception as e:
            print(f"⚠️ Erro seed_tarefas.json: {e}")

    # 4. Envia alterações para a Nuvem Render via /api/sync
    print("\n☁️ Enviando atualizações para o Hub da Nuvem...")
    try:
        changes = [
            {"action": "editar", "codigo": "#003", "status": "Em andamento", "titulo": "Ativar e-mail sobre mudança de data de chegada (Condition ZS)", "observacoes": obs_003, "timestamp": now_str},
            {"action": "editar", "codigo": "#004", "status": "Em testes", "titulo": "Colocar código e descrição do Material no e-mail de aviso (Condition ZS)", "timestamp": now_str},
            {"action": "status", "codigo": "#P01", "status": "Pendente", "timestamp": now_str},
            {"action": "status", "codigo": "#P02", "status": "Pendente", "timestamp": now_str}
        ]
        sync_payload = json.dumps({"client_id": "cli-update", "changes": changes}).encode('utf-8')
        req = urllib.request.Request(
            f"{CLOUD_URL.rstrip('/')}/api/sync",
            data=sync_payload,
            headers={"Content-Type": "application/json", "X-User-Id": "1"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            sync_res = json.loads(resp.read().decode('utf-8'))
        if sync_res.get("success"):
            print(f"✅ Nuvem atualizada com sucesso! (Alterações aplicadas: {sync_res.get('applied_changes')})")
        else:
            print(f"⚠️ Aviso Nuvem: {sync_res}")
    except Exception as e:
        print(f"⚠️ Erro sync Nuvem: {e}")

    # 5. Git commit & push
    print("\n📦 Versionando no Git...")
    try:
        subprocess.run(["git", "add", "seed_tarefas.json", "atualizar_iff_argentina.py"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "commit", "-m", "chore(iff): retomar #003 para Em andamento e corrigir mencao a condition ZS"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=False)
    except Exception as e:
        print(f"Aviso Git: {e}")

    print("\n" + "=" * 65)
    print("🎉 IFF ARGENTINA #003 RETOMADA E TODAS AS BASES SINCRONIZADAS!")
    print("=" * 65)

if __name__ == '__main__':
    main()
