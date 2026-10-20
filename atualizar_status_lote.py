# -*- coding: utf-8 -*-
"""
Atualização de Status em Lote Único - ARPego
Atualiza:
- #018 -> 'Aguardando retorno'
- #020 -> 'Em testes'
Sincroniza no SQL Server Local, SQLite Local, seed_tarefas.json e Nuvem Render.
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
    print("🚀 ATUALIZANDO STATUS DAS TAREFAS #018 E #020")
    print("=" * 65)

    now_br = get_now_br()
    now_str = now_br.strftime('%Y-%m-%d %H:%M:%S')

    updates = [
        {"codigo": "#018", "status": "Aguardando retorno", "titulo": "Atualizar produção"},
        {"codigo": "#020", "status": "Em testes", "titulo": "Corrigir eliminação de Invoice"}
    ]

    # 1. SQL Server Local
    conn_sql = get_db_connection()
    if conn_sql:
        try:
            cur_sql = conn_sql.cursor()
            cur_sql.execute("SET DATEFORMAT ymd;")
            for u in updates:
                cur_sql.execute("""
                UPDATE tb_tarefas
                SET status = ?, ultima_atualizacao = ?, sync_pendente = 1
                WHERE codigo = ?;
                """, (u["status"], now_br, u["codigo"]))
                cur_sql.execute("""
                INSERT INTO tb_historico (codigo_tarefa, descricao, data_hora)
                VALUES (?, ?, ?);
                """, (u["codigo"], f"Status atualizado para: {u['status']}", now_br))
            conn_sql.commit()
            conn_sql.close()
            print("✅ SQL Server local atualizado!")
        except Exception as e:
            print(f"⚠️ Erro SQL Server: {e}")
    else:
        print("ℹ️ SQL Server não conectado, atualizando bases locais...")

    # 2. SQLite Local (assistpe.db)
    db_file = os.path.join(BASE_DIR, "assistpe.db")
    if os.path.exists(db_file):
        try:
            conn_lite = sqlite3.connect(db_file)
            cur_lite = conn_lite.cursor()
            for u in updates:
                cur_lite.execute("""
                UPDATE tb_tarefas
                SET status = ?, ultima_atualizacao = ?
                WHERE codigo = ?;
                """, (u["status"], now_str, u["codigo"]))
                cur_lite.execute("""
                INSERT INTO tb_historico (codigo_tarefa, descricao)
                VALUES (?, ?);
                """, (u["codigo"], f"Status atualizado para: {u['status']}"))
            conn_lite.commit()
            conn_lite.close()
            print("✅ SQLite local (assistpe.db) atualizado!")
        except Exception as e:
            print(f"⚠️ Erro SQLite: {e}")

    # 3. seed_tarefas.json
    seed_file = os.path.join(BASE_DIR, "seed_tarefas.json")
    if os.path.exists(seed_file):
        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                seed_data = json.load(f)
            for t in seed_data.get("tarefas", []):
                for u in updates:
                    if t.get("codigo") == u["codigo"]:
                        t["status"] = u["status"]
                        t["ultima_atualizacao"] = now_str
            seed_data["exportado_em"] = now_str
            with open(seed_file, "w", encoding="utf-8") as f:
                json.dump(seed_data, f, ensure_ascii=False, indent=2)
            print("✅ seed_tarefas.json atualizado!")
        except Exception as e:
            print(f"⚠️ Erro seed_tarefas.json: {e}")

    # 4. Sincroniza com a Nuvem (Render)
    print("\n☁️ Enviando deltas para a Nuvem...")
    try:
        changes = [
            {"action": "status", "codigo": u["codigo"], "status": u["status"], "timestamp": now_str}
            for u in updates
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

    # 5. Git Commit & Push
    print("\n📦 Versionando no Git...")
    try:
        subprocess.run(["git", "add", "seed_tarefas.json", "atualizar_status_lote.py"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "commit", "-m", "chore: atualizar status #018 (Aguardando retorno) e #020 (Em testes)"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=False)
    except Exception as e:
        print(f"Aviso Git: {e}")

    print("\n" + "=" * 65)
    print("🎉 STATUS ATUALIZADOS COM SUCESSO EM TODAS AS BASES!")
    print("=" * 65)

if __name__ == '__main__':
    main()
