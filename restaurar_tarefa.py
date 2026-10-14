# -*- coding: utf-8 -*-
"""
Script utilitário para restaurar a tarefa de manutenção do carro:
'Conserto do alarme do carro - acionamento de fechadura pelo controle'
vinculada ao projeto 'Carro' (Pessoal).
"""

import os
import sys
import sqlite3
import re
from app_windows import get_db_connection, SQLITE_FALLBACK_FILE, sync_with_cloud

def restaurar_tarefa_carro():
    print("=" * 60)
    print("🚗 RESTAURANDO TAREFA DE MANUTENÇÃO DO CARRO...")
    print("=" * 60)

    conn = get_db_connection()
    use_sql = True if conn else False
    if not conn:
        print("SQL Server não respondeu. Utilizando banco local SQLite de fallback...")
        conn = sqlite3.connect(SQLITE_FALLBACK_FILE)
    else:
        print("Conectado ao SQL Server local (ASSISTPE)!")

    cur = conn.cursor()

    # 1. Garante que o projeto 'Carro' exista
    cur.execute("SELECT id FROM tb_projetos WHERE LOWER(nome) = 'carro';")
    p_row = cur.fetchone()
    if p_row:
        proj_id = p_row[0]
        print(f"Projeto 'Carro' encontrado (ID: {proj_id}).")
    else:
        print("Criando projeto 'Carro'...")
        cur.execute("INSERT INTO tb_projetos (nome, sigla, tipo) VALUES ('Carro', 'CARRO', 'Pessoal');")
        if use_sql:
            proj_id = cur.execute("SELECT @@IDENTITY;").fetchone()[0]
        else:
            proj_id = cur.lastrowid
        print(f"Projeto 'Carro' cadastrado com sucesso (ID: {proj_id}).")

    # 2. Localiza o próximo código #P livre
    cur.execute("SELECT codigo FROM tb_tarefas WHERE codigo LIKE '#P%';")
    codes = [r[0] for r in cur.fetchall()]
    max_num = 0
    for c in codes:
        nums = re.findall(r'\d+', c)
        if nums:
            max_num = max(max_num, int(nums[0]))
    next_cod = f"#P{max_num + 1:02d}"

    titulo = "Conserto do alarme do carro"
    obs = "Acionamento de fechadura pelo controle"

    # Verifica se já existe exatamente essa tarefa para não duplicar
    cur.execute("SELECT codigo FROM tb_tarefas WHERE LOWER(titulo) LIKE '%alarme%carro%';")
    existing = cur.fetchone()
    if existing:
        print(f"Aviso: Já existe uma tarefa cadastrada com este assunto ({existing[0]}).")
        conn.close()
        return existing[0]

    print(f"Inserindo tarefa com código único {next_cod}...")
    cur.execute("""
    INSERT INTO tb_tarefas (codigo, id_projeto, titulo, tipo, prioridade, status, observacoes, recorrencia_dias, sync_pendente)
    VALUES (?, ?, ?, 'Pessoal', 'Alta', 'Não iniciada', ?, 0, 1);
    """, (next_cod, proj_id, titulo, obs))

    conn.commit()
    conn.close()
    print(f"✅ Sucesso! Tarefa {next_cod} '{titulo}' cadastrada e marcada para sincronização.")

    print("\n🔄 Disparando sincronização com a Nuvem...")
    ok, msg = sync_with_cloud(verbose=True)
    if ok:
        print(f"☁️ Sincronização com a Nuvem: CONCLUÍDA ({msg})")
    else:
        print(f"⚠️ Aviso na sincronização: {msg} (será sincronizado na próxima inicialização)")

    return next_cod

if __name__ == '__main__':
    restaurar_tarefa_carro()
