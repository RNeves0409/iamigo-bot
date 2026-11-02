# Guia de Uso do iAmigo

Bem-vindo ao iAmigo, o seu assistente de lembretes via Telegram.

## Como começar

1. Inicie uma conversa privada com o seu bot
2. Mande `/start` ou `/ajuda` para ver os comandos disponíveis

## Criar compromissos

Para criar um novo compromisso, use o comando `/novo` seguido do título, data,
horário e antecedência do aviso:

```
/novo Consulta odontológica | 05/11/2026 14:00 | 60
```

### Formato do comando

```text
/novo TÍTULO | DIA/MÊS/ANO HORA:MINUTO | ANTECEDÊNCIA_MINUTOS
```

### Exemplos

```text
/novo Reunião de equipe | 12/11/2026 10:00 | 30
/novo Retorno ao médico | 06/11/2026 15:30 | 120
/novo Comprar presentes | 24/12/2026 09:00 | 15
```

### Validações

- O título não pode estar vazio e não pode ter mais de 200 caracteres
- A antecedência (`aviso`) deve ser um número inteiro e positivo
- O aviso deve ser enviado no futuro

## Gerenciar compromissos

### Confirmar um compromisso

Após enviar `/novo`, o bot confirma o cadastro. Envie `/confirmar` para salvar:

```
/confirmar
```

### Descartar um compromisso

Se mudou de idéia, envie `/abandonar`:

```
/abandonar
```

### Ver sua agenda

Liste todos os compromissos futuros:

```
/agenda
```

### Cancelar um compromisso

Para cancelar, envie o número do compromisso:

```
/cancelar 3
```

## Registrar lembretes

O bot envia lembretes automáticos no horário configurado. Se o envio falhar, ele
tentará novamente com intervalos crescentes (máximo de 1 hora). Se o compromisso
for cancelado manualmente, os lembretes param.

## Dúvidas

Enviar mensagem para o bot ou usar `/ajuda` a qualquer momento.
