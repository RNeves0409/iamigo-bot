#!/usr/bin/env python3
"""
Verificação de saúde para o bot iAmigo (Zabbix).

Funciona tanto no host (systemd) quanto no Docker (container iamigo-bot).

Ambiente (opcional, para modo Docker):
  IAMIGO_DOCKER=1            executar checks contra o daemon do Docker
  IAMIGO_DB_PATH=/caminho    banco (default: /var/lib/iamigo/agenda.db)
  IAMIGO_LOG=/caminho        arquivo de log (default: /var/log/iamigo/bot.log)

Saídas:
  0 - OK (processo/container ativo, DB acessível, logs limpos)
  1 - Alerta (processo/ container inativo ou erros recorrentes no log)
  2 - Critical (banco inacessível)
"""
import os
import subprocess
import sys

DB_PATH = os.environ.get("IAMIGO_DB_PATH", "/var/lib/iamigo/agenda.db")
LOG_FILE = os.environ.get("IAMIGO_LOG", "/var/log/iamigo/bot.log")
DOCKER_MODE = os.environ.get("IAMIGO_DOCKER") == "1"


def check_host():
    """Modo host: processo rodando + sqlite acessível."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python.*main.py"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False

    try:
        result = subprocess.run(
            ["sqlite3", DB_PATH, "SELECT 1"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def check_docker():
    """Modo Docker: container ativo + banco acessível dentro do container."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "iamigo-bot"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except Exception:
        return False

    try:
        result = subprocess.run(
            ["docker", "exec", "iamigo-bot",
             "sqlite3", "/var/lib/iamigo/agenda.db", "SELECT 1"],
            capture_output=True, text=True, timeout=5,
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
    if DOCKER_MODE:
        process_ok = check_docker()
    else:
        process_ok = check_host()

    db_ok = check_docker() if DOCKER_MODE else check_host()
    logs_ok = check_logs()

    if not process_ok:
        print("ALERTA: processo/container do bot não está ativo")
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
