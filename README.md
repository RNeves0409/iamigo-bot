# iAmigo — Bot de Lembretes Telegram

**iAmigo** é um bot de mensagens para Telegram que ajuda a lembrar de compromissos.
Cadastre compromissos, receba avisos automáticos e visualize sua agenda a qualquer
momento, de qualquer lugar.

---

## 📋 Funcionalidades

| Comando | Descrição |
|---|---|
| `/start` ou `/ajuda` | Mostra este guia |
| `/novo Título \| data hora \| aviso_minutos` | Cria um novo compromisso (pede confirmação) |
| `/confirmar` | Salva o compromisso em dúvida |
| `/abandonar` | Descarta o compromisso em dúvida |
| `/agenda` | Lista compromissos futuros |
| `/cancelar N` | Cancela o compromisso de número N |

### Exemplo de uso

```text
/novo Consulta odontológica | 05/11/2026 14:00 | 60
```

Resposta:

```
Confirma este compromisso?
Consulta odontológica
Compromisso: 05/11/2026 às 14:00
Aviso: 05/11/2026 às 13:00
Fuso: America/Sao_Paulo
/novo para salvar ou /abandonar para descartar.
```

Depois de confirmar, o compromisso será salvo e pode ser visualizado com `/agenda`.
O bot envia lembretes automáticos 60 minutos antes do horário definido (configurável
pelo aviso).

---

## ⚙️ Como rodar localmente

### Pré-requisitos

- Python 3.8 ou superior
- Telegram Bot Token (obtido no [@BotFather](https://t.me/BotFather) do Telegram)
- ID do usuário (obtido via `@userinfobot` ou `getUpdates`)

### Instalação

```bash
# 1. Clone ou copie o código
cd iamigo

# 2. Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/macOS
# > venv\Scripts\activate  # Windows

# 3. Instale as dependências (vazio: o bot usa apenas módulos padrão do Python)
pip install -r requirements.txt
```

### Configuração

O bot lê as variáveis de ambiente `TELEGRAM_BOT_TOKEN` e `TELEGRAM_USER_ID`.
Para desenvolvimento local, defina-as antes de rodar. Exemplo com um arquivo `.env`:

```bash
cat > .env <<'EOF'
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_USER_ID=12345678
EOF
export $(cat .env | xargs)
```

> Em produção, use um `EnvironmentFile` (systemd) — consulte `DEPLOY.md`.

### Executando

```bash
# Com o Docker instalado e .env configurado:
docker compose up -d
```

O bot estará disponível na conversa privada com você no Telegram.

### (Antigo deploy com systemd)

O deploy em produção via systemd e `python main.py` foi mantido como referência
do projeto. O novo fluxo preferido é o Docker Compose (acima) — veja
`DEPLOY.md` em "Deploy com Docker".

---

## 🧪 Testando

```bash
# Rodar os testes unitários
python -m unittest test_db -v
python -m unittest tests.test_service -v
```

---

## 🐳 Rodando com Docker (Fase 1)

O projeto é entregue em containers. Requisitos: Docker + Docker Compose instalados.

```bash
# 1. Copie o modelo de variáveis de ambiente
cp .env.example .env
# Edite .env com seu TELEGRAM_BOT_TOKEN e TELEGRAM_USER_ID

# 2. Leve os modelos do Ollama (pode demorar um pouco)
docker pull ollama/ollama:latest
docker compose pull

# 3. Suba a stack
docker compose up -d

# 4. Verifique
docker compose ps
docker compose logs -f bot
```

Internamente:
- `bot`  → `main.py` (API Telegram + agenda SQLite no volume `iamigo-data`)
- `ollama` → Ollama, acesso interno em `http://ollama:11434`
- Banco no padrão `/var/lib/iamigo/agenda.db` (volume)

> A camada de IA (interpretador de linguagem natural e áudio) entra na
> **Fase 2**; os comandos `/novo`, `/confirmar`, `/agenda`, `/cancelar`
> continuam disponíveis inclusive sem a IA ativa.

## 📤 Publicando no GitHub

1. Crie o repositório no GitHub (com README, licença e workflows — o projeto
   já traz tudo);
2. No repositório local, conecte ao GitHub:

```bash
git remote add origin git@github.com:SEU_USUARIO/iamigo.git
git branch -M main
git push -u origin main
```

O fluxo `CI` (GitHub Actions) roda todos os testes em cada `push` ou
`pull_request`.

---

## 📦 Estrutura do projeto

```
iamigo/
├── api/                    # Cliente da API do Telegram
│   ├── __init__.py
│   └── client.py
├── db/                     # Acesso ao banco de dados SQLite
│   ├── __init__.py
│   └── connection.py
├── services/               # Lógica de negócio e comandos
│   ├── __init__.py
│   └── handler.py
├── tests/                  # Testes unitários
│   └── test_service.py
├── zabbix/                 # Scripts e configuração do Zabbix
├── main.py                 # Ponto de entrada do bot
├── test_db.py              # Testes unitários da camada de dados
├── requirements.txt        # Dependências (vazio: módulos padrão do Python)
├── DEPLOY.md               # Guia de deploy em produção
├── GUIA_USO.md             # Guia do usuário final
└── .github/
    └── workflows/
        └── test.yml        # CI: rodar testes em push/pull_request
```

> `bot.py` é o código original (monolito) que serve de referência para o
> `services/` + `api/` + `db/` hoje. `logs/` e `venv/` são ignorados via `.gitignore`.

---

## 🐛 Solução de problemas

| Problema | Solução |
|---|---|
| `KeyError: TELEGRAM_BOT_TOKEN` | Defina `TELEGRAM_BOT_TOKEN` como variável de ambiente |
| `telegram.error` | Token inválido ou bot não ativado |
| Mensagem não recebida | Verifique se o `TELEGRAM_USER_ID` está correto |

---

## 📜 Licença

Distribuído sobre a licença [MIT](LICENSE). Veja o arquivo para os termos completos.
