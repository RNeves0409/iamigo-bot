#!/bin/bash
# Script de backup do banco de dados do iAmigo
# Instale via systemd: sudo cp zabbix/backup_db.sh /usr/local/bin/
#                    sudo chmod +x /usr/local/bin/backup_db.sh
#                    sudo nano /etc/systemd/system/iamigo-backup.service
#
# Arquivo de serviço:
# [Unit]
# Description=Backup do banco iAmigo
# OnCalendar=*-*-* 02:00:00
# [Service]
# Type=oneshot
# ExecStart=/usr/local/bin/backup_db.sh
# [Install]
# WantedBy=multi-user.target

set -euo pipefail

BACKUP_DIR="/var/backups/iamigo"
DB_PATH="/var/lib/iamigo/agenda.db"
KEEP_DAYS=7

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/agenda_${TIMESTAMP}.sql.gz"

if [ -f "$DB_PATH" ]; then
    gzip -c "$DB_PATH" > "$BACKUP_FILE"
    echo "Backup criado: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
else
    echo "AVISO: Banco de dados não encontrado em $DB_PATH"
fi

find "$BACKUP_DIR" -name "agenda_*.sql.gz" -mtime +$KEEP_DAYS -delete
echo "Backup concluído"
