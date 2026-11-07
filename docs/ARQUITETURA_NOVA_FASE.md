# iAmigo — Fase 2: Docker + IA local (Ollama)

> Entrega para a nova fase do iAmigo: rodar o bot em Docker, com um modelo Ollama
> local que interpreta linguagem natural e (fase 2) áudio, e mantém os comandos
> legados. Baseia-se no código atual (`main.py`, `api/client.py`, `db/connection.py`,
> `services/handler.py`, `tests/`, `DEPLOY.md`, `zabbix/`).

---

## 1. Cambio da arquitetura

O projeto passa de **um processo systemd que pollia a API do Telegram** para um
**conjunto de containers** no Docker Compose. A camada de negócio (`services/`),
camada de dados (`db/`) e o cliente de API (`api/`) permanecem; o que muda é a
*execução*, a *linha de comunicação com a IA* e o *resíduo de estado* que a IA
consome.

### 1.1 Contêineres e volumes

| Contêiner | Função | Imagem | Ports | Dependencies | Volume |
|---|---|---|---|---|---|
| `iamigo-bot` | Bot Telegram (main.py) | `python:3.14-slim` (build) | — | `ollama` | `iamigo-db` → `/var/lib/iamigo` |
| `ollama` | Serviço de IA local | `ollama/ollama` | `11434:11434` | — | — |
| `redis` | *Opcional* filas/Redis e cache | `redis:7-alpine` | `6379:6379` | — | — |
| `zabbix-agent` | Monitoramento (opcional, neste host) | `zabbix/zabbix-agent` | 10050 | `iamigo-bot` | — |

- **SQLite:** o caminho de produção é `/var/lib/iamigo/agenda.db`, sempre
  dentro do volume `iamigo-db` (não bind-mounted para o host, a não ser que o
  operador prefira). O `PRAGMA journal_mode=WAL` já existe na camada `db/`.
- **`iamigo-bot`** recebe as seguintes variáveis de ambiente:
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_ID` (iguais ao atual)
  - `OLLAMA_BASE_URL` (padrão `http://ollama:11434`)
  - `IAMIGO_DB_PATH` (padrão `/var/lib/iamigo/agenda.db`)
  - `IAMIGO_MODEL` (padrão `llama3.2:1b` ou `phi3-mini:3.8b`)
- **`redis` é opcional.** O plano de fase 1 não exige fila. Ele serve para:
  - cache assíncrono de respostas do modelo e *rate limit* de chamadas;
  - fila de "tarefas pendentes" (envio de avisos, re-tentativas) se o bot for
    escalado para mais de um contêiner;
  - substituto do `config.rascunho` se a conversa for desmembrada em estado
    externo (não é o caso de fase 1 — mantemos o `config.rascunho` SQLite).

### 1.2 `docker-compose.yml` (esqueleto)

```yaml
services:
  bot:
    build: .
    image: iamigo-bot:0.2
    env_file: [.env]
    depends_on:
      - ollama
    volumes:
      - iamigo-db:/var/lib/iamigo
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import sqlite3; sqlite3.connect('/var/lib/iamigo/agenda.db').execute('SELECT 1')"]
      interval: 30s
      timeout: 5s
      retries: 3

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    environment:
      - OLLAMA_MODELS=/ollama/models
    volumes:
      - ollama-data:/ollama/models
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 4G

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    restart: unless-stopped

volumes:
  iamigo-db:
  ollama-data:
```

### 1.3 Troca de deploy

- O systemd `iamigo.service` deixa de chamar `python main.py` e passa a ser o
  *gestor* do Compose (`docker compose up -d`), com `restart: unless-stopped` no
  Compose soando como alta disponibilidade.
- O `zabbix_agentd` permanece no host; o `healthcheck.py` continua válido, mas o
  checklist de monitoramento passa a cobrir: `restart` do contêiner, `oom_kill`,
  uso de memória do `ollama`, e tamanhos do volume `iamigo-db` (log de crescimento).

---

## 2. Modelo de comunicação com a IA

**Resposta de fase 1: HTTP síncrono via `POST /api/generate`.** Não se usa
streaming nesta fase, pelo seguinte:

- **Re-tentáveis de forma determinística:** em caso de timeout, o chamador repete
  o mesmo `POST` sem consumir estado parcial (no streaming, resposta parcial
  desperdiça e a lógica de *resume* fica mais complexa);
- **Testável com contrato fixo:** basta mockar uma resposta JSON estável;
- **Simplifica o estado de "aguardando resposta":** o bot só avança quando a
  resposta chega, e não incrementalmente.

A interface usada é a de **chat** (não puro generate), via

```
POST http://ollama:11434/api/chat
Content-Type: application/json
{
  "model": "llama3.2:1b",
  "messages": [{"role": "user", "content": "..."}],
  "stream": false,
  "options": {"temperature": 0.2, "top_p": 0.9}
}
```

Retorno esperado: `{"model": ..., "message": {"role":"assistant","content":"..."}, "done": true}`.

- **Temperatura baixa (0.1–0.3)** para decisões de intenção/cadastro serem
  previsíveis;
- **Timeout:** 60s por chamada; o bot repete com backoff exponencial (máx. 3
  tentativas);
- **Streaming** (SSE `POST /api/generate?stream=true`) é o *Fase 2*, quando o
  UX exiger aceitação de texto à medida.

---

## 3. Fluxo de requisição: Telegram → IA → usuário

```
Telegram (usuário)
   │  1. Mensagem / áudio
   ▼
[iamigo-bot]  api.getUpdates (polling)
   │  2. message.text / message.voice/audio/document
   ▼
[handler]  classifica a mensagem
   ├─ MATCH/CONEXÃO:  /novo, /confirmar, /agenda, /cancelar, /ajuda  →  caminho LEGADO (descrito em §6)
   └─ NOMATCH:        →  NLP (IA)            (descrito em §4/§5)
   ▼
[services.nlp]   POST /api/chat → ollama
   │  3. system prompt + (intenção de lembrar? / agendar?)
   ▼
[ollama]       modelo local (ex: llama3.2:1b ou phi3-mini)
   │  4. extrai: título, data/hora, aviso, intenção
   ▼
[handler]      se extração OK → salva rascunho no config.rascunho (mesmo slot dos legados)
   │  5. envia mensagem de confirmação (botão/quick-replies ou texto)
   ▼
[Telegram]     usuário responde /confirmar ou /negar
   ▼
(caminho legado) → INSERT na tabela agenda → agendamento
```

### Legenda dos números (fluxo de IA)

| Etapa | Quem | O que faz | Entrada | Saída |
|---|---|---|---|---|
| 1 | Telegram | Envia a mensagem e o `update_id` | — | `update` |
| 2 | `handler.handle()` | Despacha; ignora mensagens de outros usuários/groups | `message` | decisão de rota |
| 3 | `services.nlp.parse()` | Envia ao modelo e extrai intenção/entidades | texto + `system prompt` | `Draft(titulo, evento, aviso)` |
| 4 | `ollama` | Gera o texto com o modelo | prompt | `message.content` |
| 5 | `handler` | Persiste rascunho → chama `/confirmar`-lógica existente | `Draft` | salva `config.rascunho` |
| 6 | usuário | Confirma ou não | `/confirmar` | `INSERT INTO agenda` |

> Nota: o `config.rascunho` é o **elo de compatibilidade**. O IA não escreve uma
> tabela nova; ele preenche o mesmo campo `config(chave='rascunho')` que o
> `/novo` usado antes. Assim, `/confirmar`, `/abandonar` e o `notifications()`
> continuam exatamente como escrito, sem mudanças.

---

## 4. Tratamento de áudio

Fluxo proposto:

```
Telegram  →  getFile  →  download do bytes do áudio →  STT (Ollama)  →  texto
                                        ↓
                              [IA]  inferência de intenção do texto
```

- O áudio vem como `message.voice` / `message.audio` / `document` em `audio/mpeg`,
  `audio/ogg`. O `bot.py`/`api/client.py` hoje só lida com `message.text`; o novo
  código lê o `file_path` devolvido por `getFile` e baixa com `urlopen` (timeout 25s,
  máximo de tamanho configurável, ex.: 10 MB).
- **STT:** o `Ollama` **não embarca transcrição nativa**. Esta é uma decisão
  *aberta* para a equipe. Opções, em ordem de preferência:
  1. Modelo de áudio via Ollama (p. ex. pesos Whisper.cpp registrados no
     registo Ollama, se disponível na versão do Docker); o retorno é texto e
     segue o fluxo abaixo;
  2. Serviço de STT local (p. ex. `whisper` Python, `faster-whisper`, ou um
     `stt-api` container ligado ao bot via `OLLABA_BASE_URL`);
  3. Se não houver STT na fase 1, o áudio é respondido com um comando
     legado explícito (`/novo` + texto) e anotado como *Fase 2*.
- Após STT, o texto passa pelas mesmas funcionalidades de NLP do item acima.

> O áudio é **NÃO** parte da fase 1 por enquanto; ele é planejado como uma
> prioridade explícita de Fase 2, acompanhado da decisão de STT acima.

---

## 5. Comandos legados (compatibilidade)

Os comandos `/novo`, `/confirmar`, `/abandonar`, `/agenda`, `/cancelar` e
`/ajuda` **continuram intactos**. A mudança é: eles são *destinatários* do
caminho legado e o *backstop* do novo.

- O `handler` ainda detecta o `command` no prefixo `/`, desconsiderando `@` e
  maiúsculas (`command.split("@")[0].lower()`), e executa a mesma lógica de
  `services/handler.py` (sem apagar).
- O que muda é o que acontece **quando o usuário digita algo que não é comando**,
  ex.: *“quero lembrar-me de uma consulta amanhã 10h”*. Nesse caso o bot invoca
  o NLP em vez de responder “Comando não reconhecido”.
- O rascunho produzido pelo NLP **reutiliza** o slot `config.rascunho`, então
  `/confirmar`, `/abandonar` e `notifications()` são usados sem modificação.
- Tipagem de estado no banco continua sendo `'pendente' → 'enviado' → 'cancelado'`,
  não se altera.

---

## 6. O que acontece se a IA falhar?

Estratégias de fallback por cenário:

| Cenário | Comportamento |
|---|---|
| Ollama indisponível (rede/out) | O bot **não trava**; desativa o NLP (modo legado). Mensagens livres respondem com um menu de comandos (`/novo | ...`, `/confirmar`, `/agenda`, `/cancelar`) e o usuário continua usando os comandos. Nenhum dado é perdido. |
| Parse falha (IA responde sem extrair entidades) | Não salva rascunho; repete a mensagem com *sugestões* (ex.: `/novo Consulta | 05/11/2026 14:00 | 60`). Após `N` falhas (ex. 3), esvazia `rascunho` e informa o erro. |
| `generate` timeout/erro de rede | Retry com backoff (3 tentativas, máx. ~30s acumulado). Se perpetuado, entra no modo legado. |
| Modelo muito lento (`> timeout` p/ um update) | Não bloqueia o loop de `getUpdates`; a resposta do bot é exibida somente quando pronta, e o `offset` só é avançado após o fallback ser decidido — o que evita *message loss*. |
| STT (fase 2) falhar | Volta ao texto original, se disponível; se só houver áudio, avisa que o áudio não pôde ser processado e sugere `/ajuda`. |

---

## 7. Monitoramento, logs e backup

- **Logs:** o `logging` do bot segue o formato atual; o Docker sai para
  `journald`/`stdout` e é rodo com `docker compose logs -f`. Adiciona-se um
  `logger` específico para chamadas à IA (msec, `OLLAMA_BASE_URL`, status, tempo).
- **Zabbix:** no host `192.168.100.3`, o agente já é configurado. Novos itens:
  - `iamigo.bot.containers_up` — `docker ps --format '{{.Names}}'` que inclui o
    `iamigo-bot` e o `ollama`;
  - `iamigo.ollama.memory_bytes` — `docker stats --no-stream --format`
  - `iamigo.db.size_bytes` — `du -sb /var/lib/iamigo/agenda.db` (via volume);
  - `iamigo.healthcheck` — o `zabbix/healthcheck.py` adaptado para o volume e o
    processo do compose (opcional); o `UserParameter` `iamigo.process.state`
    continua útil para detectar *restart loops*.
- **Backup:** o `zabbix/backup_db.sh` ainda age sobre o arquivo de volume, mas em
  Docker o backup deve ser feito com `docker run --rm -v iamigo-db:/d -w /d
  alpine tar czf /backup/agenda_$(date +%F).sql.gz agenda.db`; ou exportar o
  volume para o host via bind/read-only no backup container. O backup não
  substitui o `.gitignore` (nunca commitar o `.db`).

---

## 8. Teste

### 8.1 Unidade (janela existente, quase não muda)

- `tests/test_service.py` e `test_db.py` continuam passando; o handler legado
  é re-executado. O que muda é *cobertura*:
  - `services/nlp.py`: `parse_natural_language` com casos de texto livre
    (intenção: agenda/cadastro/cancelar) e entradas inválidas;
  - normalização de datas (módulo `services/dates.py`), com `ZoneInfo("America/Sao_Paulo")`;
  - idempotência do `notifications()` (nenhum aviso duplicado).
- O `send` continua mockado nos testes (não entra em API verdadeira).

### 8.2 Contrato da IA (sem modelo real)

- `tests/test_nlp_contract.py` mocka `OLLAMA_BASE_URL` com HTTP estático
  (p. ex. `responses` ou `httpretty`): resposta fixa que retorna um `Draft`.
  Garante que o bot está no caminho correto independente do modelo.
- Testa também o *sequence* `null` do fallocate: **cadastro verdadeiro** via
  `/novo` → `/confirmar` → `/agenda` → `/cancelar` (já existente, mantido).

### 8.3 Integração com compose

- Novo job no GitHub Actions (`test:docker`): `docker compose build && docker
  compose up -d`; script que envia um `update` simulado (token de teste,
  `getUpdates`) e verifica a resposta do bot; `docker compose down -v` no final.
- Uso de `supervisor`/script de espera (`wait-for-ollama.sh`) antes de rodar o
  bot, garantindo que o `ollama` subiu antes da consulta.

---

## 9. Deploy

1. `docker compose build` (imagen do bot) + `docker compose pull ollama` (se
   houver registry privado).
2. `docker compose up -d`; aguardar `healthcheck` do bot e `ollama` pronto
   (`ollama pull <modelo>` via `docker compose exec ollama ollama pull llama3.2:1b`).
3. `docker compose logs -f iamigo-bot` → verificar a primeira requisição `/api/chat`.
4. Atualização (`git pull` + `docker compose up -d --build`) com *zero downtime*
   (Compose recria o contêiner; o SQLite é o volume, não o filesystem da imagem).
5. Monitoramento/lista de check: contêineres up, memória `ollama` < 4G, DB
   acessível, backup executado, `docker image ls` sem imagens orfãs > 3.

---

## 10. Fase 1 — Plano de entrega (porta a porta)

Ordem proposital; cada etapa sai só quando a anterior passa os testes mínimos.
Estimativa de *equipe-de-1*: ~1 semana.

| # | Tarefa | Entregável | Pré-req | Status |
|---|---|---|---|---|
| 1 | Dockerizar o bot: `Dockerfile`, `.dockerignore`, `docker-compose.yml` com `bot`, `ollama`, `redis`(opcional), volume `iamigo-db` | compose + Dockerfile passando `build` | n/a | **A fazer** |
| 2 | Subir Ollama com modelo pequeno (p. ex. `llama3.2:1b` ou `phi3-mini:3.8b`) e verificar `/api/generate` e `/api/chat` | `curl localhost:11434/api/generate` retorna `{"model":...}` | etapa 1 | **A fazer** |
| 3 | Criar `services/nlp.py`: `parse_natural_language(text) -> Draft`, com *system prompt* objetivo e saída JSON; **contrato testado** (mock) | `nlp.py` + `tests/test_nlp_contract.py` | etapas 1–2 | **A fazer** |
| 4 | Adicionar no `handler`: no `else` (comando não reconhecido) chamar o `nlp`; se OK → preencher `config.rascunho` e mandar confirmação com sugestões; se falha → fallback legado | `handler.py` atualizado | etapas 1–3 | **A fazer** |
| 5 | *Retry/Fallback*: backoff em falha da IA; modo legado ativado; `rascunho` esvaziado depois de N falhas | `handler.py` + `nlp.py` | etapas 2–4 | **A fazer** |
| 6 | **Áudio**: *placeholder* imediato (captura, log de "áudio em Fase 2"), sem quebrar o fluxo; decidir STT (Ollama Whisper ou serviço externo) | `handler.py` íntegro para áudio (fase 2) | etapas 2–4 | **Abrir** |
| 7 | Teste: CI extendido (`unittest` existente + `test:docker` compose) | GitHub Actions `test:docker` com build + script de smoke | etapas 1–4 | **A fazer** |
| 8 | Deploy: `DEPLOY.md`/`README.md` atualizados, systemd → compose, alertas Zabbix, backup via volume; testes de smoke no server | `DEPLOY.md` + README | etapas 1–7 | **A fazer** |
| 9 | *Retrospectiva*; decisões de Fase 2: streaming de IA, STT de áudio, suporte a grupos | Roadmap Fase 2 | todas | **Abrir** |

---

## 11. Decisões/incertezas a responder do usuário (antes da execução)

Para fechar o plano sem quebrar o escopo, estes pontos ficam como `ABRIR` até
que o usuário responda:

1. **Modelo IA:** `llama3.2:1b` (rápido, baixo VRAM) ou `phi3-mini:3.8b`
   (melhor rendimento, ~4G)? Há preferência por firmware/Texty?
2. **Streaming vs HTTP síncrono:** confirmado **síncrono `/api/chat` na fase 1**,
   streaming no Fase 2?
3. **Áudio:** STT via modelo Whisper dentro do Ollama, ou servço de STT
   independente (ex.: `faster-whisper` Python)? Incluído na Fase 1 ou só Fase 2?
4. **Redis:** usar `redis` como cache/fila (sim) ou só o SQLite (não)?
5. **Compatibilidade:** manter o `config.rascunho` no SQLite (sim — minimiza
   mudanças) ou migrar para Redis como estado transiente apenas?
6. **Monitoramento:** manter Zabbix 192.168.100.3 com os novos contêineres
   (sim, adaptando `healthcheck.py`)?
7. **Variáveis de ambiente:** `TELEGRAM_BOT_TOKEN` e `TELEGRAM_USER_ID` via
   `.env` + `env_file` no Compose (sim)?

---

## 12. Pontos de atenção

- **Nunca** persistir o `.db` na imagem; sempre no volume.
- O `getUpdates` do bot não deve ser alterado em si; o estado de "aguardando
  confirmação" corresponde ao `config.rascunho`, e o `offset` é avançado após o
  fallback, nunca antes.
- O `notifications()` continua **assíncrono** à roda dos comandos — novo código não
  deve atrapalhar essa verificação de horários.
- A IA é *aditiva* nesta fase, não substituta: o caminho legado é o garantista
  de não perder funcionamento.
