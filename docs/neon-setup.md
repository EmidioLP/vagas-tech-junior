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

São coisas diferentes com o **mesmo nome**, para facilitar a rastreabilidade:

| | Branch Git | Branch Neon |
|---|---|---|
| Nome | `feature/data-platform` | `feature-data-platform` |
| O que isola | código | dados e schema do banco |
| Onde fica | repositório | projeto Neon |

A branch Neon `production` é só o ponto de partida do projeto. **Nada de
desenvolvimento é aplicado nela.**

## Roteiro

Execute na raiz do repositório, com a branch Git `feature/data-platform` ativa.

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

## Deploy no Render: atenção

O `render.yaml` ainda não define `DATABASE_URL`. Quando esta branch chegar à
`main`, o serviço deixa de subir até a variável ser configurada, e isso fica para
a etapa 15.

**Não aponte o Render para o Neon com o `startCommand` atual:** ele roda
`import_csv.py --recriar`, que faz `drop_all` a cada boot.
