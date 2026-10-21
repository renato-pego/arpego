# -*- coding: utf-8 -*-
"""
Ajuste de Projeto da Tarefa #024 para 'Boa' e Sincronização em Lote Único
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
    print("🚀 AJUSTANDO PROJETO DA TAREFA #024 PARA 'Boa' + SINCRONIZAÇÃO")
    print("=" * 65)

    now_br = get_now_br()
    now_str = now_br.strftime('%Y-%m-%d %H:%M:%S')

    # 1. SQL Server Local
    conn_sql = get_db_connection()
    if conn_sql:
        try:
            cur_sql = conn_sql.cursor()
            cur_sql.execute("SET DATEFORMAT ymd;")
            # Garante projeto 'Boa'
            cur_sql.execute("SELECT id FROM tb_projetos WHERE LOWER(nome) = 'boa';")
            row_p = cur_sql.fetchone()
            if row_p:
                proj_id_sql = row_p[0]
            else:
                cur_sql.execute("INSERT INTO tb_projetos (nome, sigla, tipo) VALUES ('Boa', 'BOA', 'Profissional');")
                proj_id_sql = cur_sql.execute("SELECT @@IDENTITY;").fetchone()[0]

            # Atualiza #024
            cur_sql.execute("""
            UPDATE tb_tarefas 
            SET id_projeto = ?, ultima_atualizacao = ?, sync_pendente = 1
            WHERE codigo = '#024';
            """, (proj_id_sql, now_br))

            cur_sql.execute("""
            INSERT INTO tb_historico (codigo_tarefa, descricao, data_hora)
            VALUES ('#024', 'Projeto corrigido para: Boa', ?);
            """, (now_br,))

            conn_sql.commit()
            conn_sql.close()
            print(f"✅ SQL Server local atualizado! Projeto 'Boa' ID={proj_id_sql}")
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
            cur_lite.execute("SELECT id FROM tb_projetos WHERE id_usuario = 1 AND LOWER(nome) = 'boa';")
            row_pl = cur_lite.fetchone()
            if row_pl:
                proj_id_lite = row_pl[0]
            else:
                cur_lite.execute("INSERT INTO tb_projetos (id_usuario, nome, sigla, tipo) VALUES (1, 'Boa', 'BOA', 'Profissional');")
                proj_id_lite = cur_lite.lastrowid

            cur_lite.execute("""
            UPDATE tb_tarefas 
            SET id_projeto = ?, ultima_atualizacao = ?
            WHERE id_usuario = 1 AND codigo = '#024';
            """, (proj_id_lite, now_str))

            cur_lite.execute("""
            INSERT INTO tb_historico (id_usuario, codigo_tarefa, descricao)
            VALUES (1, '#024', 'Projeto corrigido para: Boa');
            """)
            conn_lite.commit()
            conn_lite.close()
            print(f"✅ SQLite local atualizado! Projeto 'Boa' ID={proj_id_lite}")
        except Exception as e:
            print(f"⚠️ Erro SQLite: {e}")

    # 3. seed_tarefas.json
    seed_file = os.path.join(BASE_DIR, "seed_tarefas.json")
    if os.path.exists(seed_file):
        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                seed_data = json.load(f)

            # Verifica lista de projetos
            projs_list = seed_data.get("projetos", [])
            boa_exists = any(p.get("nome", "").lower() == "boa" for p in projs_list)
            if not boa_exists:
                next_id = max((p.get("id", 0) for p in projs_list), default=0) + 1
                projs_list.append({"id": next_id, "nome": "Boa", "sigla": "BOA", "tipo": "Profissional"})
                seed_data["projetos"] = projs_list

            for t in seed_data.get("tarefas", []):
                if t.get("codigo") == "#024":
                    t["projeto"] = "Boa"
                    t["ultima_atualizacao"] = now_str
                    break

            seed_data["exportado_em"] = now_str
            with open(seed_file, "w", encoding="utf-8") as f:
                json.dump(seed_data, f, ensure_ascii=False, indent=2)
            print("✅ seed_tarefas.json atualizado com projeto 'Boa'!")
        except Exception as e:
            print(f"⚠️ Erro seed_tarefas.json: {e}")

    # 4. Envia para a Nuvem Render via /api/sync
    print("\n☁️ Enviando alteração para a Nuvem...")
    try:
        changes = [
            {
                "action": "editar",
                "codigo": "#024",
                "projeto": "Boa",
                "titulo": "Criação do Follow UP sem EIC - Novo módulo de importação",
                "tipo": "Profissional",
                "prioridade": "Alta",
                "status": "Em andamento",
                "timestamp": now_str
            }
        ]
        sync_payload = json.dumps({
            "client_id": "cli-update",
            "projetos": [{"nome": "Boa", "tipo": "Profissional"}],
            "changes": changes
        }).encode('utf-8')
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
        subprocess.run(["git", "add", "seed_tarefas.json", "ajustar_projeto_024.py"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "commit", "-m", "fix: ajustar projeto da tarefa #024 para 'Boa'"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=False)
    except Exception as e:
        print(f"Aviso Git: {e}")

    print("\n" + "=" * 65)
    print("🎉 PROJETO DA TAREFA #024 CORRIGIDO PARA 'Boa' COM SUCESSO!")
    print("=" * 65)

if __name__ == '__main__':
    main()
