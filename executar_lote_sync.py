# -*- coding: utf-8 -*-
"""
Execução Consolidada em Lote Único - ARPego
Executa:
1. dump_seed_and_sync.py (Dump do SQL Server + sincronização com a nuvem)
2. diagnostico_sync.py (Verificação de paridade de tarefas e status)
3. git add, commit e push (Deploy da sincronização com timestamps no Render)
"""
import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def run_cmd(cmd):
    print(f"\n>> Executando: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print(res.stderr)
    return res.returncode

def main():
    print("=" * 65)
    print("🚀 INICIANDO EXECUÇÃO CONSOLIDADA EM LOTE ÚNICO")
    print("=" * 65)

    # 1. Exporta seed e sincroniza com a nuvem
    ret = run_cmd([sys.executable, "dump_seed_and_sync.py"])
    if ret != 0:
        print("⚠️ Erro durante dump_seed_and_sync.py")

    # 2. Diagnóstico de paridade
    ret_diag = run_cmd([sys.executable, "diagnostico_sync.py"])
    if ret_diag != 0:
        print("⚠️ Erro durante diagnostico_sync.py")

    # 3. Git add, commit e push para o Render
    print("\n📦 Git: versionando e enviando para o repositório principal...")
    run_cmd(["git", "add", "app.py", "app_windows.py", "painel.html", "painel_desktop.html", "sw.js", "dump_seed_and_sync.py", "seed_tarefas.json", "executar_lote_sync.py"])
    run_cmd(["git", "commit", "-m", "fix(desktop): blindar conversao de datetime no SQL Server eliminando erro 22007"])
    run_cmd(["git", "push", "origin", "main"])

    print("\n" + "=" * 65)
    print("✅ LOTE ÚNICO CONCLUÍDO COM SUCESSO!")
    print("=" * 65)

if __name__ == '__main__':
    main()
