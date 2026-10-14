# -*- coding: utf-8 -*-
import urllib.request
import json
import sqlite3
import re
from app_windows import get_db_connection, SQLITE_FALLBACK_FILE, CLOUD_URL

def diagnosticar():
    print("=" * 60)
    print("🔍 DIAGNÓSTICO DE SINCRONIZAÇÃO")
    print("=" * 60)

    # 1. Consulta SQL Server local
    conn = get_db_connection()
    if not conn:
        conn = sqlite3.connect(SQLITE_FALLBACK_FILE)
    cur = conn.cursor()
    cur.execute("""
    SELECT t.codigo, t.status, p.nome, t.titulo, t.sync_pendente
    FROM tb_tarefas t
    LEFT JOIN tb_projetos p ON t.id_projeto = p.id
    ORDER BY t.id;
    """)
    local_tasks = cur.fetchall()
    conn.close()

    print(f"\n💻 DESKTOP (SQL Server): Total de {len(local_tasks)} tarefas")
    pends = [t for t in local_tasks if t[1] not in ('Concluída', 'Em testes') and not 'teste' in t[1].lower()]
    testes = [t for t in local_tasks if 'teste' in t[1].lower() or t[1] == 'Em testes']
    concs = [t for t in local_tasks if t[1] == 'Concluída']
    print(f"   • Pendentes: {len(pends)} | Em Testes: {len(testes)} | Concluídas: {len(concs)}")
    
    sync_pends = [t for t in local_tasks if t[4] == 1]
    print(f"   • Tarefas com sync_pendente=1 no Desktop: {len(sync_pends)}")
    for t in sync_pends:
        print(f"     -> {t[0]}: {t[3]} (Proj: {t[2]})")

    # 2. Consulta Nuvem (Render)
    req_url = f"{CLOUD_URL.rstrip('/')}/api/tarefas"
    req = urllib.request.Request(req_url, headers={"X-User-Id": "1", "User-Agent": "ARPegoDiagnostico"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            cloud_tasks = json.loads(resp.read().decode('utf-8'))
        print(f"\n☁️ NUVEM (Render): Total de {len(cloud_tasks)} tarefas retornadas por /api/tarefas")
        c_pends = [t for t in cloud_tasks if t['status'] not in ('Concluída', 'Em testes') and not 'teste' in t['status'].lower()]
        c_testes = [t for t in cloud_tasks if 'teste' in t['status'].lower() or t['status'] == 'Em testes']
        c_concs = [t for t in cloud_tasks if t['status'] == 'Concluída']
        print(f"   • Pendentes: {len(c_pends)} | Em Testes: {len(c_testes)} | Concluídas: {len(c_concs)}")
        
        # Mostra as tarefas na nuvem
        cloud_codes = set(t['codigo'] for t in cloud_tasks)
        local_codes = set(t[0] for t in local_tasks)

        missing_in_cloud = local_codes - cloud_codes
        print(f"\n⚠️ Tarefas no Desktop que NÃO ESTÃO na Nuvem: {missing_in_cloud}")
        for t in local_tasks:
            if t[0] in missing_in_cloud:
                print(f"   • {t[0]}: {t[3]} (Proj: {t[2]} | Status: {t[1]})")

        # Verifica projetos na Nuvem
        req_p = urllib.request.Request(f"{CLOUD_URL.rstrip('/')}/api/projetos", headers={"X-User-Id": "1", "User-Agent": "ARPegoDiagnostico"})
        with urllib.request.urlopen(req_p, timeout=10) as resp_p:
            cloud_projs = json.loads(resp_p.read().decode('utf-8'))
        print(f"\n📁 PROJETOS NA NUVEM: {[p['nome'] for p in cloud_projs]}")

    except Exception as e:
        print(f"\n❌ Erro ao consultar a Nuvem: {e}")

if __name__ == '__main__':
    diagnosticar()
