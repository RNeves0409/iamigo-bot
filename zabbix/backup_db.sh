#!/bin/bash
# Script de backup do banco de dados do iAmigo
#
# Uso no host (deploy Docker):
#   DB_PATH=/var/lib/iamigo/agenda.db ./zabbix/backup_db.sh
#
# Uso dentro do container (recomendado — snapshot consistente sem parar o serviço):
#   docker exec iamigo-bot sqlite3 /var/lib/iamigo/agenda.db ".backup '/tmp/agenda.sql'"
#   docker cp iamigo-bot:/tmp/agenda.sql .
#
# O migrate .backup do SQLite garante um snapshot consistente mesmo com WAL
# (o gzip puro do script original, aplicado só no arquivo .db, pode perder commits).
#
# Configurações:
#   DB_PATH          (default: /var/lib/iamigo/agenda.db)
#   BACKUP_DIR       (default: /var/backups/iamigo)
#   KEEP_DAYS=7      (mantém os backups dos últimos 7 dias)

set -euo pipefail

DB_PATH="${DB_PATH:-/var/lib/iamigo/agenda.db}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/iamigo}"
KEEP_DAYS=7

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/agenda_${TIMESTAMP}.sql.gz"

if [ -f "$DB_PATH" ]; then
    # Snapshot real via .backup do SQLite (WAL-safe), compactado em gzip
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE.sql'" 2>/dev/null \
            && gzip -f "$BACKUP_FILE.sql" \
            && echo "Backup criado: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
    else
        echo "AVISO: sqlite3 não disponível — backup ignorado" >&2
    fi
else
    echo "AVISO: Banco de dados não encontrado em $DB_PATH" >&2
fi

find "$BACKUP_DIR" -name "agenda_*.sql.gz" -mtime +"$KEEP_DAYS" -delete
echo "Backup concluído"
