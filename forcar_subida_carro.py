# -*- coding: utf-8 -*-
import json
import urllib.request
import sqlite3
from app_windows import get_db_connection, SQLITE_FALLBACK_FILE, CLOUD_URL, sync_with_cloud

def forcar_sync_carro():
    print("=" * 60)
    print("🚀 FORÇANDO SINCRONIZAÇÃO DAS TAREFAS DO CARRO")
    print("=" * 60)

    conn = get_db_connection()
    if not conn:
        conn = sqlite3.connect(SQLITE_FALLBACK_FILE)
    cur = conn.cursor()

    # Marca sync_pendente = 1 para todas as tarefas do carro
    cur.execute("""
    UPDATE tb_tarefas
    SET sync_pendente = 1
    WHERE codigo IN ('#021', '#P03', '#P04', '#P05');
    """)
    conn.commit()
    conn.close()
    print("Marcado sync_pendente = 1 para #021, #P03, #P04, #P05 no Desktop.")

    # Executa sync_with_cloud
    print("\nEnviando para a Nuvem (Render)...")
    success, msg = sync_with_cloud(verbose=True)
    print(f"Resultado do sync: {msg} (Sucesso: {success})")

    # Verifica na Nuvem
    req_url = f"{CLOUD_URL.rstrip('/')}/api/tarefas"
    req = urllib.request.Request(req_url, headers={"X-User-Id": "1", "User-Agent": "ARPegoCheck"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        cloud_tasks = json.loads(resp.read().decode('utf-8'))
    
    print(f"\n☁️ Total de tarefas na Nuvem agora: {len(cloud_tasks)}")
    carro_tasks = [t for t in cloud_tasks if (t.get('projeto') or '').lower() == 'carro']
    print(f"🚗 Tarefas do projeto 'Carro' na Nuvem: {len(carro_tasks)}")
    for t in carro_tasks:
        print(f"   • {t['codigo']}: {t['titulo']} ({t['status']})")

if __name__ == '__main__':
    forcar_sync_carro()
