# -*- coding: utf-8 -*-
"""
Atualização de Status:
- #003 (IFF Argentina): Liberada para testes -> 'Em testes'
- #024 (Boa): Permanece 'Em andamento'
Sincronização consolidada em Lote Único em todas as bases.
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
    print("🚀 ATUALIZANDO STATUS: #003 -> 'Em testes' | #024 -> 'Em andamento'")
    print("=" * 65)

    now_br = get_now_br()
    now_str = now_br.strftime('%Y-%m-%d %H:%M:%S')

    obs_003 = "Ajustes realizados. Liberada para testes e homologação pelos usuários em QAS."

    # 1. SQL Server Local
    conn_sql = get_db_connection()
    if conn_sql:
        try:
            cur_sql = conn_sql.cursor()
            cur_sql.execute("SET DATEFORMAT ymd;")
            # Atualiza #003
            cur_sql.execute("""
            UPDATE tb_tarefas 
            SET status = 'Em testes', observacoes = ?, ultima_atualizacao = ?, sync_pendente = 1
            WHERE codigo = '#003';
            """, (obs_003, now_br))
            cur_sql.execute("""
            INSERT INTO tb_historico (codigo_tarefa, descricao, data_hora)
            VALUES ('#003', 'Status atualizado para: Em testes (Liberada para homologação)', ?);
            """, (now_br,))

            # Atualiza #024 (confirma em andamento)
            cur_sql.execute("""
            UPDATE tb_tarefas 
            SET status = 'Em andamento', ultima_atualizacao = ?, sync_pendente = 1
            WHERE codigo = '#024';
            """, (now_br,))

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
            SET status = 'Em testes', observacoes = ?, ultima_atualizacao = ?
            WHERE id_usuario = 1 AND codigo = '#003';
            """, (obs_003, now_str))
            cur_lite.execute("""
            INSERT INTO tb_historico (id_usuario, codigo_tarefa, descricao)
            VALUES (1, '#003', 'Status atualizado para: Em testes (Liberada para homologação)');
            """)

            cur_lite.execute("""
            UPDATE tb_tarefas 
            SET status = 'Em andamento', ultima_atualizacao = ?
            WHERE id_usuario = 1 AND codigo = '#024';
            """, (now_str,))

            conn_lite.commit()
            conn_lite.close()
            print("✅ SQLite local atualizado com sucesso!")
        except Exception as e:
            print(f"⚠️ Erro SQLite: {e}")

    # 3. seed_tarefas.json
    seed_file = os.path.join(BASE_DIR, "seed_tarefas.json")
    if os.path.exists(seed_file):
        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                seed_data = json.load(f)

            for t in seed_data.get("tarefas", []):
                if t.get("codigo") == "#003":
                    t["status"] = "Em testes"
                    t["observacoes"] = obs_003
                    t["ultima_atualizacao"] = now_str
                elif t.get("codigo") == "#024":
                    t["status"] = "Em andamento"
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
            {"action": "status", "codigo": "#003", "status": "Em testes", "timestamp": now_str},
            {"action": "status", "codigo": "#024", "status": "Em andamento", "timestamp": now_str}
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
            print(f"✅ Nuvem sincronizada! (Alterações aplicadas: {sync_res.get('applied_changes')})")
        else:
            print(f"⚠️ Aviso Nuvem: {sync_res}")
    except Exception as e:
        print(f"⚠️ Erro sync Nuvem: {e}")

    # 5. Git Commit & Push
    print("\n📦 Versionando no Git...")
    try:
        subprocess.run(["git", "add", "seed_tarefas.json", "atualizar_status_003_024.py"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "commit", "-m", "chore: atualizar #003 para 'Em testes' e manter #024 'Em andamento'"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=False)
    except Exception as e:
        print(f"Aviso Git: {e}")

    print("\n" + "=" * 65)
    print("🎉 STATUS ATUALIZADOS E SINCRONIZADOS COM SUCESSO!")
    print("=" * 65)

if __name__ == '__main__':
    main()
