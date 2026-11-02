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
python main.py
```

O bot estará disponível na conversa privada com você no Telegram.

---

## 🧪 Testando

```bash
# Rodar os testes unitários
python -m unittest test_db -v
python -m unittest tests.test_service -v
```

---

## 📤 Publicando no GitHub

1. Crie um repositório no GitHub (sem adicionar README, licença ou workflows —
   este projeto já os traz);
2. No repositório local, conecte ao GitHub:

```bash
git remote add origin git@github.com:SEU_USUARIO/iamigo.git
git branch -M main
git push -u origin main
```

O fluxo `CI` (GitHub Actions) roda todos os testes a cada `push` ou `pull_request`.

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
