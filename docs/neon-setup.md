# Neon — configuração do banco

O projeto usa **Neon PostgreSQL** e lê o banco de uma única variável,
`DATABASE_URL`. Este guia configura o Neon numa máquina de desenvolvimento **sem
colocar nenhuma URL, senha, token ou id real no git**.

## Como a aplicação encontra a URL

`scraper/config.py` (`obter_database_url`) procura `DATABASE_URL` nesta ordem:

1. variável já definida no ambiente (shell, CI, docker-compose);
2. `.env.local`, gerado por `neon env pull`;
3. `.env`, legado.

Sem a variável, a API e o `scripts/import_csv.py` **falham na inicialização**
com uma mensagem que explica o que fazer, e nunca imprimem o valor. Os arquivos
são lidos sem alterar `os.environ`. `postgres://` e `postgresql://` são
convertidos para o driver `psycopg`, e `sslmode`/`channel_binding` são mantidos.

## Branch Git × branch Neon

São coisas diferentes. A branch Neon de desenvolvimento nasceu com o nome da
branch Git da plataforma de dados (`feature/data-platform`, já mesclada e
apagada), e continua sendo o banco de desenvolvimento local:

| | Branch Git | Branch Neon |
|---|---|---|
| Nome | branches curtas a partir da `main` | `feature-data-platform` |
| O que isola | código | dados e schema do banco |
| Onde fica | repositório | projeto Neon |

A branch Neon `production` é só o ponto de partida do projeto. **Nada de
desenvolvimento é aplicado nela.**

## Roteiro

Execute na raiz do repositório, em qualquer branch Git.

```powershell
# Uma vez por máquina
npm i -g neon@latest
neon login

# Skills do Neon para o Claude Code (opcional). O MCP fica de fora: `neon mcp -y`
# faz instalação global e grava token.
neon skills -s neon -s neon-postgres -y

# Liga o diretório ao projeto. O id vem de `neon projects list` e fica só no
# arquivo .neon, que é ignorado pelo git.
neon link --project-id <NEON_PROJECT_ID> --branch production --no-env-pull -y

# Cria (se preciso) e seleciona a branch da feature; grava as variáveis dela
# no .env.local.
neon checkout feature-data-platform --create

# Configuração declarativa
neon config init --services none
```

Deixe o `neon.ts` exatamente assim:

```ts
import { defineConfig } from "@neon/config/v1";

export default defineConfig({});
```

Revise e aplique, **sempre na branch da feature**:

```powershell
neon config status --branch feature-data-platform
neon deploy --branch feature-data-platform
neon env pull --service postgres
```

Com a configuração vazia, `neon deploy` não cria tabelas nem migrations: só
alinha a branch ao `neon.ts`.

### Por que esses flags

- **`--no-env-pull` no `link`:** com uma branch fixada, `link` roda `env pull`
  sozinho. Apontado para `production`, ele gravaria em disco a URL de produção.
- **`--branch feature-data-platform` em `status` e `deploy`:** sem ele, os dois
  comandos usam a branch padrão do projeto, que é a `production`.
- **`--create` no `checkout`:** fora de um terminal interativo, o `checkout` não
  cria a branch sem esse flag.
- **Sem `.env` na raiz:** `env pull` grava num `.env` que já exista e só usa
  `.env.local` quando não há `.env`.

## Renovar a URL

Se a senha for trocada ou a branch recriada:

```powershell
neon env pull --service postgres
```

O comando atualiza `DATABASE_URL`, `DATABASE_URL_UNPOOLED` e `NEON_BRANCH` no
`.env.local`, preservando as outras linhas. A aplicação só lê `DATABASE_URL`.
Não cole a saída de `neon` em issues, logs ou documentação: criação de projeto e
de branch pode imprimir credenciais (use `--no-secrets` quando existir).

## GitHub Secret

Para os workflows, cadastre `DATABASE_URL` como secret do repositório, sem que a
URL passe pela linha de comando nem pelo histórico do shell:

- **Interface web:** *Settings → Secrets and variables → Actions → New repository
  secret*, nome `DATABASE_URL`, e cole o valor.
- **GitHub CLI:** `gh secret set DATABASE_URL` sem `--body`. O `gh` pede o valor
  de forma interativa.

Prefira a URL de uma branch Neon própria para CI, nunca a da `production`. Como
disparar a coleta e o que cada workflow faz: `docs/automation.md`.

## O que fica fora do git

| Arquivo | Conteúdo | Git |
|---|---|---|
| `.env.local`, `.env` | URL real com senha | ignorado |
| `.neon` | `orgId`, `projectId`, branch | ignorado |
| `node_modules/` | pacotes `@neon/*` | ignorado |
| `.env.example` | valores fictícios | versionado |
| `neon.ts` | configuração declarativa, sem segredo | versionado |

## Branches Neon e onde fica cada URL

| Branch Neon | Para quê | Quem usa | Onde a `DATABASE_URL` fica |
|---|---|---|---|
| `production` | ponto de partida do projeto; **nada é aplicado nela** | ninguém | — |
| `feature-data-platform` | desenvolvimento e testes manuais | máquina local | `.env.local` (`neon env pull`) |
| `dados-main` | dados reais da `main` | API no Render e coleta no GitHub Actions | painel do Render e GitHub Secret `DATABASE_URL` (URL **pooled** nos dois) |

- **Migrations na `dados-main`** rodam da máquina local, com a URL **direta**
  carregada só no ambiente do comando, como em `docs/migrations.md`
  ("Testar numa branch Neon temporária"):

  ```powershell
  neon env pull --branch dados-main --service postgres --file <fora-do-repo>/dados-main.env
  # carregue DATABASE_URL_UNPOOLED desse arquivo só no ambiente do comando
  alembic upgrade head
  ```

  Aplique sempre **antes** do merge que traz a migration: a coleta e a API param
  com "schema atual" se o banco estiver atrasado.
- **Reimportar o seed.** A tabela legada `vagas`, que a API lê, foi importada uma
  vez de `seed/vagas.csv`. O Render não importa nada no boot. Se o seed mudar,
  carregue a `DATABASE_URL` da `dados-main` só no ambiente do comando e rode:

  ```powershell
  python scripts/import_csv.py --csv seed/vagas.csv --referencia 2026-09-15
  ```

  Sem `--recriar`, a importação só cria o que falta e atualiza as vagas
  existentes. **Nunca use `--recriar` na `dados-main`.**
- **Variável no Render.** Pegue a URL pooled no seu terminal com
  `neon connection-string dados-main --pooled` e cadastre em *Render →
  vagas-tech-junior-api → Environment*. O `render.yaml` só declara a variável
  (`sync: false`), sem valor.

  Na primeira vez, cadastrada antes do merge, o Render redeploya o código antigo
  da `main`, que lê `DATABASE_URL` e roda `import_csv.py --recriar`. Esse deploy
  **falha** com `InternalError` sem apagar nada: o PostgreSQL recusa derrubar
  `tecnologias`, que o histórico referencia, e desfaz a transação. O Render mantém
  o deploy anterior no ar. Faça o merge logo depois.

Rollback do merge e do deploy: `docs/rollback-merge.md`.
