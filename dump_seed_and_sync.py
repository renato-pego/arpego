# -*- coding: utf-8 -*-
"""
Script de Carga e Sincronização Unificada - ARPego
Exporta os 28 registros do SQL Server Desktop para seed_tarefas.json
e despacha a sincronização bidirecional completa com a Nuvem.
"""
import os
import json
import sqlite3
from datetime import datetime
from app_windows import get_db_connection, SQLITE_FALLBACK_FILE, CLOUD_URL, sync_with_cloud, get_now_br
from app import init_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEED_FILE = os.path.join(BASE_DIR, "seed_tarefas.json")

def main():
    print("=" * 60)
    print("🚀 ARPEGO: EXPORTAÇÃO DE SEED E SINCRONIZAÇÃO COMPLETA")
    print("=" * 60)

    conn = get_db_connection()
    use_sql = True if conn else False
    if not conn:
        print("⚠️ Conectando via SQLite Fallback...")
        conn = sqlite3.connect(SQLITE_FALLBACK_FILE)
    else:
        print("✅ Conectado ao SQL Server local (ASSISTPE)!")

    cur = conn.cursor()

    # 1. Busca todos os projetos
    cur.execute("SELECT id, nome, sigla, tipo FROM tb_projetos ORDER BY id;")
    projs = []
    for r in cur.fetchall():
        projs.append({
            "id": r[0],
            "nome": r[1],
            "sigla": r[2],
            "tipo": r[3]
        })
    print(f"📁 Projetos encontrados: {len(projs)} ({[p['nome'] for p in projs]})")

    # 2. Busca todas as 28 tarefas locais com carimbo de tempo
    now_str = get_now_br().strftime('%Y-%m-%d %H:%M:%S')
    if use_sql:
        cur.execute("""
        SELECT t.codigo, t.id_projeto, p.nome, t.titulo, t.tipo, t.prioridade, 
               t.status, t.observacoes, t.data_conclusao, t.recorrencia_dias, t.data_recorrencia,
               CONVERT(VARCHAR(19), t.ultima_atualizacao, 120) AS ultima_atualizacao
        FROM tb_tarefas t
        LEFT JOIN tb_projetos p ON t.id_projeto = p.id
        ORDER BY t.id;
        """)
    else:
        cur.execute("""
        SELECT t.codigo, t.id_projeto, p.nome, t.titulo, t.tipo, t.prioridade, 
               t.status, t.observacoes, t.data_conclusao, t.recorrencia_dias, t.data_recorrencia,
               t.ultima_atualizacao
        FROM tb_tarefas t
        LEFT JOIN tb_projetos p ON t.id_projeto = p.id
        ORDER BY t.id;
        """)

    tasks = []
    for r in cur.fetchall():
        u_ts = str(r[11]) if r[11] else now_str
        tasks.append({
            "codigo": r[0],
            "id_projeto": r[1],
            "projeto": r[2] or "Geral",
            "titulo": r[3],
            "tipo": r[4],
            "prioridade": r[5],
            "status": r[6],
            "observacoes": r[7] or "",
            "data_conclusao": r[8],
            "recorrencia_dias": r[9] or 0,
            "data_recorrencia": r[10],
            "ultima_atualizacao": u_ts
        })

    print(f"📋 Tarefas encontradas no Desktop: {len(tasks)}")
    conn.close()

    # 3. Grava seed_tarefas.json
    seed_data = {
        "exportado_em": now_str,
        "total_tarefas": len(tasks),
        "projetos": projs,
        "tarefas": tasks
    }

    with open(SEED_FILE, "w", encoding="utf-8") as f:
        json.dump(seed_data, f, ensure_ascii=False, indent=2)

    print(f"💾 Arquivo seed gerado com sucesso: {SEED_FILE}")

    # 4. Atualiza banco SQLite local (assistpe.db) diretamente com o seed
    print("🔄 Atualizando banco SQLite de desenvolvimento/produção local...")
    init_db()

    # 5. Executa sincronização com o Hub da Nuvem (Render)
    print("☁️ Enviando snapshot completo com timestamps para a Nuvem...")
    ok, msg = sync_with_cloud(verbose=True)
    if ok:
        print(f"✅ Sincronização com a Nuvem concluída com sucesso: {msg}")
    else:
        print(f"⚠️ Aviso na sincronização: {msg}")

    print("=" * 60)
    print("🎉 OPERAÇÃO FINALIZADA!")
    print("=" * 60)

if __name__ == '__main__':
    main()
