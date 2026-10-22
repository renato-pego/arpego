# -*- coding: utf-8 -*-
"""
=============================================================================
Assistente Pessoal - ARPego: Gestão e Governança de Apontamentos (IADBMNG)
=============================================================================
Objetivo:
Auxiliar o usuário a manter seus apontamentos de horas sempre em dia,
alertando sobre dias pendentes, lançamentos sem tarefa no PSOffice e
sugerindo a distribuição de horas do dia com base nas tarefas executadas.
"""

import sys
import os
import sqlite3
from datetime import datetime, timezone, timedelta, date

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

TZ_BR = timezone(timedelta(hours=-3))

def get_now_br():
    return datetime.now(timezone.utc).astimezone(TZ_BR).replace(tzinfo=None)

IADBMNG_SQLITE = r"c:\IADBMNG\db\iadbmng.db"

def get_iadbmng_connection():
    """Tenta conectar ao SQL Server IADBMNG ou ao SQLite local de contingência."""
    try:
        import pyodbc
        # 1. SQL Server com usuário IADBMNG
        conn_str = "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=IADBMNG;UID=IADBMNG;PWD=IADBMNG;TrustServerCertificate=yes;"
        return pyodbc.connect(conn_str, timeout=2), "sqlserver"
    except Exception:
        try:
            # 2. SQL Server com Autenticação Windows
            conn_str_win = "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=IADBMNG;Trusted_Connection=yes;TrustServerCertificate=yes;"
            return pyodbc.connect(conn_str_win, timeout=2), "sqlserver"
        except Exception:
            pass

    # 3. Fallback SQLite
    if os.path.exists(IADBMNG_SQLITE):
        try:
            return sqlite3.connect(IADBMNG_SQLITE), "sqlite"
        except Exception:
            pass

    return None, None

def obter_status_apontamentos():
    """
    Retorna o diagnóstico completo da situação dos apontamentos:
    - Horas apontadas hoje (Data atual)
    - Total da semana atual
    - Dias úteis recentes sem apontamento (ou < 8h)
    - Lançamentos pendentes de PSOffice (sem_tarefa / nao_lancado)
    """
    now_br = get_now_br()
    hoje_str = now_br.strftime('%Y-%m-%d')
    conn, engine = get_iadbmng_connection()

    if not conn:
        return {
            "status": "erro",
            "mensagem": "Não foi possível conectar ao banco IADBMNG.",
            "horas_hoje": 0.0,
            "dias_pendentes": []
        }

    cur = conn.cursor()
    try:
        # 1. Horas apontadas hoje
        query_hoje = "SELECT COALESCE(SUM(HorasTrabalhadas), 0) FROM ApontamentosHoras WHERE DataApontamento = ?;"
        cur.execute(query_hoje, (hoje_str,))
        row_h = cur.fetchone()
        horas_hoje = float(row_h[0]) if row_h and row_h[0] is not None else 0.0

        # 2. Histórico dos últimos 7 dias úteis
        dias_a_verificar = []
        d = now_br.date()
        for i in range(10):
            check_date = d - timedelta(days=i)
            # Apenas dias úteis (segunda a sexta)
            if check_date.weekday() < 5:
                dias_a_verificar.append(check_date.strftime('%Y-%m-%d'))
            if len(dias_a_verificar) >= 5:
                break

        resumo_dias = []
        dias_pendentes = []

        for dia in dias_a_verificar:
            cur.execute("SELECT COALESCE(SUM(HorasTrabalhadas), 0), COUNT(*) FROM ApontamentosHoras WHERE DataApontamento = ?;", (dia,))
            r = cur.fetchone()
            tot = float(r[0]) if r and r[0] is not None else 0.0
            qtd = int(r[1]) if r else 0

            is_hoje = (dia == hoje_str)
            ok = (tot >= 8.0)

            if not ok and not is_hoje:
                dias_pendentes.append({"data": dia, "horas": tot, "faltam": round(8.0 - tot, 1)})

            resumo_dias.append({
                "data": dia,
                "horas": tot,
                "qtd_lancamentos": qtd,
                "completo": ok,
                "is_hoje": is_hoje
            })

        # 3. Lançamentos com StatusPsoffice irregular (sem_tarefa / nao_lancado)
        query_ps = """
        SELECT TOP 10 DataApontamento, Projeto, HorasTrabalhadas, StatusPsoffice, DescricaoTarefa
        FROM ApontamentosHoras
        WHERE StatusPsoffice IN ('sem_tarefa', 'nao_lancado')
        ORDER BY DataApontamento DESC;
        """ if engine == "sqlserver" else """
        SELECT DataApontamento, Projeto, HorasTrabalhadas, StatusPsoffice, DescricaoTarefa
        FROM ApontamentosHoras
        WHERE StatusPsoffice IN ('sem_tarefa', 'nao_lancado')
        ORDER BY DataApontamento DESC
        LIMIT 10;
        """
        cur.execute(query_ps)
        rows_ps = cur.fetchall()
        pendencias_ps = []
        for p in rows_ps:
            pendencias_ps.append({
                "data": str(p[0]),
                "projeto": p[1],
                "horas": p[2],
                "status_ps": p[3],
                "descricao": p[4]
            })

        conn.close()

        return {
            "status": "ok",
            "data_hoje": hoje_str,
            "horas_hoje": horas_hoje,
            "meta_atingida": (horas_hoje >= 8.0),
            "resumo_dias": resumo_dias,
            "dias_pendentes": dias_pendentes,
            "pendencias_psoffice": pendencias_ps,
            "total_pendencias_ps": len(pendencias_ps)
        }

    except Exception as e:
        conn.close()
        return {
            "status": "erro",
            "mensagem": str(e),
            "horas_hoje": 0.0,
            "dias_pendentes": []
        }

def gerar_sugestao_apontamento_dia(tarefas_em_andamento):
    """
    Gera sugestão pronta de apontamento com base nas tarefas que o usuário está atuando.
    """
    if not tarefas_em_andamento:
        return []

    # Se há 3 tarefas em paralelo (como hoje: #024 Boa, #025 IFF, #026 IFF)
    # Sugere divisão proporcional (ex: 4h Boa, 4h IFF)
    sugestoes = []
    qtd = len(tarefas_em_andamento)
    horas_base = round(8.0 / qtd, 1)

    for idx, t in enumerate(tarefas_em_andamento):
        sugestoes.append({
            "cliente": t.get("projeto", "Geral"),
            "horas": horas_base,
            "descricao": f"[{t.get('codigo')}] {t.get('titulo')}"
        })

    return sugestoes

if __name__ == '__main__':
    res = obter_status_apontamentos()
    print("STATUS APONTAMENTOS:", res)
