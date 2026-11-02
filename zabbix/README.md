# Monitoramento e Backup — iAmigo

Este diretório contém os artefatos para monitorar o bot iAmigo via Zabbix e
realizar backups automáticos do banco de dados. Agora em formato de guia
público (excluindo ambientes internos).

---

## 📁 Arquivos

| Arquivo | Descrição |
|---|---|
| `README.md` | Este guia |
| `healthcheck.py` | Verificação de saúde do bot (processo, banco, logs) |
| `backup_db.sh` | Script de backup automático do SQLite para `.sql.gz` |
| `iamigo_agent.conf` | Userparameters e configuração do Zabbix Agent |

---

## 🩺 Saúde do bot

`healthcheck.py` verifica três pontos e sai com código de resultado:

| Código | Significado |
|---|---|
| 0 | OK — processo ativo, banco acessível, logs limpos |
| 1 | ALERTA — processo inativo ou erros recorrentes no log |
| 2 | CRÍTICO — banco inacessível |

Uso direto:

```bash
python3 zabbix/healthcheck.py
```

## 💾 Backup automático

`backup_db.sh` copia `agenda.db` para `/var/backups/iamigo/`, compacta com gzip e
mantém apenas os 7 dias mais recentes.

Instalação (com systemd timer):

```bash
sudo cp zabbix/backup_db.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/backup_db.sh
```

Crie um serviço systemd para rodar o backup diariamente:

```ini
[Unit]
Description=Backup do banco iAmigo

[Service]
Type=oneshot
ExecStart=/usr/local/bin/backup_db.sh
Nice=19
IOSchedulingClass=best-effort
```

```ini
[Unit]
Description=Backup do banco iAmigo
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=multi-user.target
```

Ative o timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iamigo-backup.timer
```

O backup é compactado com gzip, mantido por 7 dias e salvo em `/var/backups/iamigo`.

## 🔌 Zabbix Agent

Copie os `UserParameter` do arquivo `iamigo_agent.conf` para o `conf.d` do agente:

```bash
sudo mkdir -p /etc/zabbix/zabbix_agentd.conf.d
sudo cp zabbix/iamigo_agent.conf /etc/zabbix/zabbix_agentd.conf.d/iamigo.conf
sudo systemctl restart zabbix-agent
```

> Ajuste o `Hostname` e o `Server` conforme a sua infraestrutura.
