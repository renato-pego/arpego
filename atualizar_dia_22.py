# -*- coding: utf-8 -*-
"""
Atualização do Dia 22/10 - ARPego:
1. Conclui hábitos diários de hoje: #P01 (Duolingo) e #P02 (Caminhada) com corte para 23/10 04:00
2. Mantém #024 (Boa - Follow UP) em andamento
3. Cria/ativa as 2 novas frentes de foco da IFF Brasil / México:
   - #025: Refatorar ABAP interface de pedido (Apareceu um erro) -> Em andamento
   - #026: Erro na carga do TXT da Krom -> Em andamento
4. Sincroniza em lote único: SQL Server Local, SQLite Local, Nuvem Render, seed_tarefas.json e Git
"""

import sys
import os
import json
import sqlite3
import urllib.request
import subprocess
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

TZ_BR = timezone(timedelta(hours=-3))

def get_now_br():
    return datetime.now(timezone.utc).astimezone(TZ_BR).replace(tzinfo=None)

def calculate_recurrence_target(rec_dias, from_dt=None):
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from app_windows import get_db_connection, CLOUD_URL

def main():
    print("=" * 65)
    print("🚀 ATUALIZAÇÃO 22/10: HÁBITOS CONCLUÍDOS + NOVAS FRENTES IFF BR/MX")
    print("=" * 65)

    now_br = get_now_br()
    now_str = now_br.strftime('%Y-%m-%d %H:%M:%S')
    target_rec = calculate_recurrence_target(1, now_br)

    novas_tarefas = [
        {
            "codigo": "#025",
            "projeto": "IFF Brasil / México",
            "id_projeto": 4,
            "titulo": "Refatorar ABAP interface de pedido",
            "tipo": "Profissional",
            "prioridade": "Alta",
            "status": "Em andamento",
            "observacoes": "Apareceu um erro na interface de pedido. Refatorar e debugar rotina ABAP.",
            "recorrencia_dias": 0,
            "data_conclusao": None,
            "data_recorrencia": None,
            "ultima_atualizacao": now_str
        },
        {
            "codigo": "#026",
            "projeto": "IFF Brasil / México",
            "id_projeto": 4,
            "titulo": "Erro na carga do TXT da Krom",
            "tipo": "Profissional",
            "prioridade": "Alta",
            "status": "Em andamento",
            "observacoes": "Investigar e corrigir erro na carga do TXT da despachante Krom.",
            "recorrencia_dias": 0,
            "data_conclusao": None,
            "data_recorrencia": None,
            "ultima_atualizacao": now_str
        }
    ]

    # 1. SQL Server Local
    conn_sql = get_db_connection()
    if conn_sql:
        try:
            cur_sql = conn_sql.cursor()
            cur_sql.execute("SET DATEFORMAT ymd;")
            # Conclui #P01 e #P02
            for cod in ['#P01', '#P02']:
                cur_sql.execute("""
                UPDATE tb_tarefas 
                SET status = 'Concluída', data_conclusao = ?, data_recorrencia = ?, ultima_atualizacao = ?, sync_pendente = 1
                WHERE codigo = ?;
                """, (now_br, target_rec, now_br, cod))
                cur_sql.execute("INSERT INTO tb_historico (codigo_tarefa, descricao, data_hora) VALUES (?, 'Tarefa diária concluída.', ?);", (cod, now_br))

            # Garante ID do projeto IFF Brasil / México
            cur_sql.execute("SELECT id FROM tb_projetos WHERE LOWER(nome) = 'iff brasil / méxico';")
            row_p = cur_sql.fetchone()
            proj_id_sql = row_p[0] if row_p else 4

            # Insere/atualiza #025 e #026
            for nt in novas_tarefas:
                cur_sql.execute("SELECT id FROM tb_tarefas WHERE codigo = ?;", (nt["codigo"],))
                if cur_sql.fetchone():
                    cur_sql.execute("""
                    UPDATE tb_tarefas
                    SET id_projeto = ?, titulo = ?, tipo = ?, prioridade = ?, status = ?, observacoes = ?, ultima_atualizacao = ?, sync_pendente = 1
                    WHERE codigo = ?;
                    """, (proj_id_sql, nt["titulo"], nt["tipo"], nt["prioridade"], nt["status"], nt["observacoes"], now_br, nt["codigo"]))
                else:
                    cur_sql.execute("""
                    INSERT INTO tb_tarefas (codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, recorrencia_dias, sync_pendente, ultima_atualizacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1, ?);
                    """, (nt["codigo"], proj_id_sql, nt["titulo"], nt["tipo"], nt["prioridade"], nt["status"], nt["observacoes"], now_br))
                cur_sql.execute("INSERT INTO tb_historico (codigo_tarefa, descricao, data_hora) VALUES (?, 'Nova tarefa iniciada em andamento.', ?);", (nt["codigo"], now_br))

            conn_sql.commit()
            conn_sql.close()
            print("✅ SQL Server local atualizado com sucesso!")
        except Exception as e:
            print(f"⚠️ Erro SQL Server: {e}")
    else:
        print("ℹ️ SQL Server local indisponível.")

    # 2. SQLite Local (assistpe.db)
    db_file = os.path.join(BASE_DIR, "assistpe.db")
    if os.path.exists(db_file):
        try:
            conn_lite = sqlite3.connect(db_file)
            cur_lite = conn_lite.cursor()
            # Conclui #P01 e #P02
            for cod in ['#P01', '#P02']:
                cur_lite.execute("""
                UPDATE tb_tarefas 
                SET status = 'Concluída', data_conclusao = ?, data_recorrencia = ?, ultima_atualizacao = ?
                WHERE id_usuario = 1 AND codigo = ?;
                """, (now_str, target_rec, now_str, cod))
                cur_lite.execute("INSERT INTO tb_historico (id_usuario, codigo_tarefa, descricao) VALUES (1, ?, 'Tarefa diária concluída.');", (cod,))

            # Garante ID do projeto IFF Brasil / México no SQLite
            cur_lite.execute("SELECT id FROM tb_projetos WHERE id_usuario = 1 AND LOWER(nome) = 'iff brasil / méxico';")
            row_pl = cur_lite.fetchone()
            proj_id_lite = row_pl[0] if row_pl else 4

            # Insere/atualiza #025 e #026
            for nt in novas_tarefas:
                cur_lite.execute("SELECT id FROM tb_tarefas WHERE id_usuario = 1 AND codigo = ?;", (nt["codigo"],))
                if cur_lite.fetchone():
                    cur_lite.execute("""
                    UPDATE tb_tarefas 
                    SET id_projeto = ?, titulo = ?, tipo = ?, prioridade = ?, status = ?, observacoes = ?, ultima_atualizacao = ?
                    WHERE id_usuario = 1 AND codigo = ?;
                    """, (proj_id_lite, nt["titulo"], nt["tipo"], nt["prioridade"], nt["status"], nt["observacoes"], now_str, nt["codigo"]))
                else:
                    cur_lite.execute("""
                    INSERT INTO tb_tarefas (id_usuario, codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, recorrencia_dias, ultima_atualizacao)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, 0, ?);
                    """, (nt["codigo"], proj_id_lite, nt["titulo"], nt["tipo"], nt["prioridade"], nt["status"], nt["observacoes"], now_str))
                cur_lite.execute("INSERT INTO tb_historico (id_usuario, codigo_tarefa, descricao) VALUES (1, ?, 'Nova tarefa iniciada em andamento.');", (nt["codigo"],))

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

            tarefas_list = seed_data.get("tarefas", [])
            for t in tarefas_list:
                if t.get("codigo") in ('#P01', '#P02'):
                    t["status"] = "Concluída"
                    t["data_conclusao"] = now_str
                    t["data_recorrencia"] = target_rec
                    t["ultima_atualizacao"] = now_str

            for nt in novas_tarefas:
                found = False
                for t in tarefas_list:
                    if t.get("codigo") == nt["codigo"]:
                        t.update(nt)
                        found = True
                        break
                if not found:
                    tarefas_list.append(nt)

            seed_data["total_tarefas"] = len(tarefas_list)
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
            {"action": "status", "codigo": "#P01", "status": "Concluída", "timestamp": now_str},
            {"action": "status", "codigo": "#P02", "status": "Concluída", "timestamp": now_str},
            {
                "action": "nova",
                "codigo": "#025",
                "titulo": novas_tarefas[0]["titulo"],
                "projeto": novas_tarefas[0]["projeto"],
                "tipo": novas_tarefas[0]["tipo"],
                "prioridade": novas_tarefas[0]["prioridade"],
                "status": novas_tarefas[0]["status"],
                "observacoes": novas_tarefas[0]["observacoes"],
                "timestamp": now_str
            },
            {
                "action": "nova",
                "codigo": "#026",
                "titulo": novas_tarefas[1]["titulo"],
                "projeto": novas_tarefas[1]["projeto"],
                "tipo": novas_tarefas[1]["tipo"],
                "prioridade": novas_tarefas[1]["prioridade"],
                "status": novas_tarefas[1]["status"],
                "observacoes": novas_tarefas[1]["observacoes"],
                "timestamp": now_str
            }
        ]
        sync_payload = json.dumps({"client_id": "cli-update", "changes": changes, "tarefas": novas_tarefas}).encode('utf-8')
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
        subprocess.run(["git", "add", "seed_tarefas.json", "atualizar_dia_22.py"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "commit", "-m", "feat(iff): criar #025 e #026 (IFF BR/MX) e registrar habitos concluidos"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=False)
    except Exception as e:
        print(f"Aviso Git: {e}")

    print("\n" + "=" * 65)
    print("🎉 ATUALIZAÇÃO 22/10 FINALIZADA E SINCRONIZADA EM TODAS AS BASES!")
    print("=" * 65)

if __name__ == '__main__':
    main()
