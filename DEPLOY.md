# Guia de Deploy — iAmigo

Este guia descreve como implantar o bot iAmigo em produção, com monitoramento
via Zabbix eBackup automático do banco de dados.

---

## 🖥️ Ambiente recomendado

- Ubuntu 20.04 ou superior (ou qualquer distro Linux com systemd)
- Python 3.8 ou superior
- Redis (opcional, para filas se precisar escalar)
- Zabbix Agent (para monitoramento)

## 1. Preparar o servidor

```bash
# Atualizar o sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependências básicas
sudo apt install -y python3 python3-venv python3-pip
```

## 2. Criar o usuário de execução

```bash
sudo useradd -m -s /bin/bash iamigo
sudo mkdir -p /var/lib/iamigo
sudo chown iamigo:iamigo /var/lib/iamigo
```

## 3. Clonar o repositório

```bash
sudo -u iamigo git clone <repositorio> /opt/iamigo
cd /opt/iamigo
```

## 4. Configurar o ambiente

```bash
sudo -u iamigo python3 -m venv venv
sudo -u iamigo source venv/bin/activate
sudo -u iamigo pip install --upgrade pip
sudo -u iamigo pip install -r requirements.txt
```

## 5. Configurar variáveis de ambiente

Crie o arquivo `/etc/iamigo/iamigo.env`:

```ini
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_USER_ID=12345678
IAMIGO_DB_PATH=/var/lib/iamigo/agenda.db
```

## 6. Configurar o serviço systemd

Crie o arquivo `/etc/systemd/system/iamigo.service`:

```ini
[Unit]
Description=iAmigo - Bot de compromissos Telegram
After=network.target

[Service]
Type=simple
User=iamigo
Group=iamigo
EnvironmentFile=/etc/iamigo/iamigo.env
ExecStart=/opt/iamigo/venv/bin/python /opt/iamigo/main.py
WorkingDirectory=/opt/iamigo
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Habilite e inicie o serviço:

```bash
sudo systemctl daemon-reload
sudo systemctl enable iamigo
sudo systemctl start iamigo
sudo systemctl status iamigo
```

## 7. Configurar o banco de dados

O banco é um arquivo SQLite criado automaticamente na primeira execução. Certifique-se
que o usuário `iamigo` tem permissão de escrita no diretório:

```bash
sudo chown -R iamigo:iamigo /var/lib/iamigo
```

## 8. Configurar backups

Crie um script de backup e ative um cron ou systemd timer:

```bash
sudo -u iamigo bash <<'EOF'
sudo cp zabbix/backup_db.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/backup_db.sh
EOF
```

## 9. Configurar monitoramento com Zabbix

### Instalar Zabbix Agent

```bash
sudo apt install -y zabbix-agent
```

### Configurar o agente

Edite `/etc/zabbix/zabbix_agentd.conf`:

```ini
Server=192.168.100.3
ServerActive=192.168.100.3
Hostname=iamigo-iamigo
```

### Configurar UserParameters (se necessário)

Adicione ao final do mesmo arquivo:

```ini
UserParameter=cpu.load.avg,awk '/^cpu /{printf "%.2f%%", ($2+$4)*100/($2+$4)}' /proc/stat
UserParameter=mem.total,awk '/MemTotal/{print $2/1024}' /proc/meminfo
UserParameter=mem.free,awk '/MemFree/{print $2/1024}' /proc/meminfo
UserParameter=iamigo.process.state,pgrep -f "python.*main.py" >/dev/null 2>&1 && echo 1 || echo 0
UserParameter=iamigo.healthcheck,/usr/bin/python3 /opt/iamigo/zabbix/healthcheck.py
```

### Reiniciar o agente

```bash
sudo systemctl restart zabbix-agent
```

## 10. Verificar

```bash
sudo systemctl status iamigo
sudo systemctl status zabbix-agent
sudo systemctl logs -u iamigo --tail=50
```

O bot deve estar respondendo nas conversas privadas do Telegram.

---

## 🔄 Manutenção

### 11. Opcional — Deploy com Docker Compose (método preferido — Fase 1)

```bash
# Pré-requisito: Docker + Docker Compose instalados
docker pull ollama/ollama:latest
docker compose pull
docker compose up -d

docker compose ps          # verificar estado
docker compose logs -f bot # verificar logs
```

O stack fica composto por:
- `bot`  → `main.py`, com o banco SQLite em volume (`iamigo-data`), no caminho
  `/var/lib/iamigo/agenda.db` (padrão do projeto);
- `ollama` → Ollama, acesso interno em `http://ollama:11434`
  (`.env` define `OLLAMA_BASE_URL=http://ollama:11434`).

Os serviços `bot` e `ollama` estão na rede `iamigo-net`; nenhum dos dois expõe
portas para a máquina host (o CLI do Ollama só precisaria acesso via
`--add-host=host.docker.internal:host-gateway`).

> Quando o usuário tiver o Zabbix instalado e configurado no host, é possível
> adicionar o serviço `zabbix-agent` ao `docker-compose.yml` (fuso horário
> `America/Sao_Paulo`, logs via `json-file`).

### Atualizar

```bash
# Versão Docker
docker compose pull
docker compose up -d
# versão systemd (referência)
sudo -u iamigo git pull origin main
sudo -u iamigo venv/bin/pip install -r requirements.txt
sudo systemctl restart iamigo
```

### Ver logs

```bash
sudo journalctl -u iamigo -f
sudo journalctl -u zabbix-agent -f
```

### Restaurar backup

```bash
gunzip -c /var/backups/iamigo/agenda_20250101_020000.sql.gz | sqlite3 /var/lib/iamigo/agenda.db
```

---

## 🔒 Segurança

- Mantenha o `TELEGRAM_BOT_TOKEN` em um local seguro
- Nenhuma configuração sensível deve estar no repositório
- Use `chmod 600` nos arquivos de configuração
- O serviço systemd está configurado com `Restart=always` para alta disponibilidade

---

## ⚠️ Troubleshooting

### O bot não responde

1. Verifique se o serviço está rodando: `systemctl status iamigo`
2. Verifique os logs: `journalctl -u iamigo`
3. Verifique o token do bot no `.env`

### O banco de dados está corrompido

Restaure do backup mais recente:
```bash
gunzip -c /var/backups/iamigo/agenda_*.sql.gz | sqlite3 /var/lib/iamigo/agenda.db
```

### O Zabbix não está recebendo métricas

1. Verifique se o agente está rodando: `systemctl status zabbix-agent`
2. Verifique se o hostname está correto no servidor Zabbix
3. Verifique a conexão de rede

---

## 📞 Suporte

Reporte problemas ou sugira melhorias no repositório do projeto.

### 📤 Pipeline de integração contínua (Fase 4)
O repositório possui `.github/workflows/test.yml` com 3 jobs:

| Job | O que faz |
|---|---|
| `test` | `pytest` com cobertura (limite 100% reportado) + suíte `unittest` (compatibilidade) |
| `test:docker` | Build + `up` do compose, verifica `healthy`, envia update simulado via `getUpdates`, remove o ambiente |
| `docs` | Valida `docker compose config`, compila os módulos Python e `bash -n` do script de smoke |

**Executar localmente (igual ao que o CI faz):**

```bash
# 1. Testes + cobertura
python3 -m venv .venv && source .venv/bin/activate
pip install pytest coverage
coverage run -m pytest tests/ -v --tb=short
coverage report --show-missing --fail-under=100

# 2. Smoke test (requer Docker e token do BotFather no .env)
./scripts/ci_smoke.sh
```

O smoke test sobe o compose, aguarda os contêineres `healthy` e envia um
`update` simulado para o bot (o `getUpdates` não exige token). Com um
token inválido só o envio de mensagem retorna `401` — é o comportamento
documentado, a stack e o loop de `getUpdates` estão verificados.

### 📤 Push para o repositório (Fase 5)
1. `git add -A && git commit -m "Fase 4: suíte de contrato, fluxo de áudio,
   CI com cobertura + pytest, smoke test"`
2. `git push origin main`
3. Verificar-se o status dos jobs do GitHub Actions (todos `green` antes do
   deploy final).

