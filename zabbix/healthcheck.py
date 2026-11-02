#!/usr/bin/env python3
"""
Verificação de saúde para o bot iAmigo (Zabbix).

Usado via Zabbix Agent:
  UserParameter=iamigo.healthcheck,/usr/bin/python3 /home/renato/projetos/iamigo/zabbix/healthcheck.py

Saidas:
  0 - OK (processo ativo, DB acessivel, logs limpos)
  1 - Alerta (processo inativo ou DB inacessivel)
  2 - Critical (erro grave)
"""

import os
import subprocess
import sys

PROJECT_DIR = "/home/renato/projetos/iamigo"
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "bot.log")
DB_PATH = "/var/lib/iamigo/agenda.db"

def check_process():
    """Verifica se o processo do bot está rodando."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python.*main.py"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def check_db():
    """Verifica se o banco de dados está acessível."""
    try:
        result = subprocess.run(
            ["sqlite3", DB_PATH, "SELECT 1"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def check_logs():
    """Verifica se o último log não está com erro crítico."""
    try:
        if not os.path.exists(LOG_FILE):
            return True
        with open(LOG_FILE, "r", errors="ignore") as f:
            lines = f.readlines()
            if not lines:
                return True
            last = lines[-1]
            return "erro" not in last.lower() and "falha" not in last.lower()
    except Exception:
        return True

def main():
    process_ok = check_process()
    db_ok = check_db()
    logs_ok = check_logs()

    if not process_ok:
        print("ALERTA: processo do bot não está ativo")
        sys.exit(1)
    if not db_ok:
        print("CRÍTICO: banco de dados não acessível")
        sys.exit(2)
    if not logs_ok:
        print("AVISO: há erros no log recente")
        sys.exit(1)

    print("OK: todos os checks passaram")
    sys.exit(0)

if __name__ == "__main__":
    main()
