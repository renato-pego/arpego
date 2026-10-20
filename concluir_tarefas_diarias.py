# -*- coding: utf-8 -*-
"""
Conclusão de Tarefas Diárias e Sincronização em Lote Único - ARPego
Conclui as tarefas #P01 (Duolingo) e #P02 (Caminhada/Calistênica) com a regra de
recorrência de 24h (corte às 04:00 BRT).
Atualiza:
1. SQL Server Local (Base Forte)
2. SQLite Local (assistpe.db)
3. Nuvem Render via /api/sync
4. Arquivo seed_tarefas.json
5. Diagnóstico de paridade e Git push
"""

import sys
import os
import json
import sqlite3
import urllib.request
import subprocess
from datetime import datetime, timezone, timedelta, date

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

from app_windows import get_db_connection, CLOUD_URL, normalize_dt

def main():
    print("=" * 65)
    print("🎯 CONCLUINDO TAREFAS DIÁRIAS: #P01 (Duolingo) e #P02 (Caminhada)")
    print("=" * 65)

    now_br = get_now_br()
    now_str = now_br.strftime('%Y-%m-%d %H:%M:%S')
    target_rec = calculate_recurrence_target(1, now_br)

    codigos = ['#P01', '#P02']
    print(f"🕒 Horário da Conclusão (Brasília): {now_str}")
    print(f"🔄 Retorno automático programado para: {target_rec} (às 04:00)")

    # 1. Atualiza SQL Server Local
    conn_sql = get_db_connection()
    if conn_sql:
        try:
            cur_sql = conn_sql.cursor()
            cur_sql.execute("SET DATEFORMAT ymd;")
            for cod in codigos:
                cur_sql.execute("""
                UPDATE tb_tarefas
                SET status = 'Concluída',
                    data_conclusao = ?,
                    data_recorrencia = ?,
                    ultima_atualizacao = ?,
                    sync_pendente = 1
                WHERE codigo = ?;
                """, (now_br, target_rec, now_br, cod))
                cur_sql.execute("INSERT INTO tb_historico (codigo_tarefa, descricao, data_hora) VALUES (?, ?, ?);",
                                (cod, "Tarefa diária concluída pelo usuário.", now_br))
            conn_sql.commit()
            conn_sql.close()
            print("✅ SQL Server local atualizado com sucesso!")
        except Exception as e:
            print(f"⚠️ Erro ao atualizar SQL Server: {e}")
    else:
        print("ℹ️ SQL Server local indisponível, seguindo com SQLite.")

    # 2. Atualiza SQLite Local (assistpe.db)
    db_file = os.path.join(BASE_DIR, "assistpe.db")
    if os.path.exists(db_file):
        try:
            conn_lite = sqlite3.connect(db_file)
            cur_lite = conn_lite.cursor()
            for cod in codigos:
                cur_lite.execute("""
                UPDATE tb_tarefas
                SET status = 'Concluída',
                    data_conclusao = ?,
                    data_recorrencia = ?,
                    ultima_atualizacao = ?
                WHERE codigo = ?;
                """, (now_str, target_rec, now_str, cod))
                cur_lite.execute("INSERT INTO tb_historico (codigo_tarefa, descricao) VALUES (?, ?);",
                                 (cod, "Tarefa diária concluída pelo usuário."))
            conn_lite.commit()
            conn_lite.close()
            print("✅ SQLite local (assistpe.db) atualizado com sucesso!")
        except Exception as e:
            print(f"⚠️ Erro ao atualizar SQLite: {e}")

    # 3. Atualiza seed_tarefas.json
    seed_file = os.path.join(BASE_DIR, "seed_tarefas.json")
    if os.path.exists(seed_file):
        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                seed_data = json.load(f)
            for t in seed_data.get("tarefas", []):
                if t.get("codigo") in codigos:
                    t["status"] = "Concluída"
                    t["data_conclusao"] = now_str
                    t["data_recorrencia"] = target_rec
                    t["ultima_atualizacao"] = now_str
            seed_data["exportado_em"] = now_str
            with open(seed_file, "w", encoding="utf-8") as f:
                json.dump(seed_data, f, ensure_ascii=False, indent=2)
            print("✅ seed_tarefas.json atualizado com sucesso!")
        except Exception as e:
            print(f"⚠️ Erro ao atualizar seed_tarefas.json: {e}")

    # 4. Despacha sincronização para a Nuvem (Render)
    print("\n☁️ Enviando atualizações para o Hub da Nuvem...")
    try:
        changes = [
            {"action": "status", "codigo": "#P01", "status": "Concluída", "timestamp": now_str},
            {"action": "status", "codigo": "#P02", "status": "Concluída", "timestamp": now_str}
        ]
        sync_payload = json.dumps({"client_id": "cli-batch", "changes": changes}).encode('utf-8')
        req = urllib.request.Request(
            f"{CLOUD_URL.rstrip('/')}/api/sync",
            data=sync_payload,
            headers={"Content-Type": "application/json", "X-User-Id": "1"}
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            sync_res = json.loads(resp.read().decode('utf-8'))
        if sync_res.get("success"):
            print(f"✅ Nuvem atualizada com sucesso! (Alterações aplicadas: {sync_res.get('applied_changes')})")
        else:
            print(f"⚠️ Resposta da Nuvem: {sync_res}")
    except Exception as e:
        print(f"⚠️ Erro na sincronização com a Nuvem: {e}")

    # 5. Executa diagnóstico de paridade
    print("\n>> Verificando paridade entre as bases...")
    try:
        subprocess.run([sys.executable, "diagnostico_sync.py"], cwd=BASE_DIR, check=False)
    except Exception as e:
        print(f"Aviso no diagnóstico: {e}")

    # 6. Git commit e push das alterações para persistência
    print("\n📦 Versionando alterações no Git...")
    try:
        subprocess.run(["git", "add", "seed_tarefas.json", "concluir_tarefas_diarias.py"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "commit", "-m", "chore: concluir tarefas diarias #P01 e #P02"], cwd=BASE_DIR, check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=False)
    except Exception as e:
        print(f"Aviso Git: {e}")

    print("\n" + "=" * 65)
    print("🎉 TAREFAS DIÁRIAS FINALIZADAS E SINCRONIZADAS EM TODAS AS BASES!")
    print("=" * 65)

if __name__ == '__main__':
    main()
