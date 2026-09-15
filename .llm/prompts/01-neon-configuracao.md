# Prompt 01 — Neon e configuração segura

**Entrega:** o projeto sabe ler uma única `DATABASE_URL` compatível com Neon, sem que senha ou URL real entre no Git.

> **Por que importa:** o banco deixa de ser “o Postgres da minha máquina” e passa a ser uma dependência explícita, reproduzível e segura para desenvolvimento, automação e deploy.

---

## O que mostrar antes

Mostre onde a aplicação hoje assume `localhost`, como a URL é lida e o `.env.example`. A mudança deve substituir suposições espalhadas por uma configuração central.

## Roteiro Neon — execute antes de alterar a aplicação

Execute a partir da raiz do repositório e confirme primeiro que a branch Git ativa é `feature/data-platform` (criada no Prompt 00). Esta branch Git e a branch Neon são coisas diferentes, mas devem usar o mesmo nome para facilitar a rastreabilidade.

```powershell
# Instalação e autenticação local; execute uma vez por máquina quando necessário
npm i -g neon@latest
neon login

# Skills do Neon para o Claude Code, somente neon e neon-postgres.
# O MCP (`neon mcp`) fica de fora: com -y ele instala globalmente e grava token.
neon skills -s neon -s neon-postgres -y

# Liga este diretório ao projeto Neon existente. O id do projeto NÃO é
# versionado: obtenha-o com `neon projects list`; o valor real fica só no
# arquivo `.neon` local, ignorado pelo git.
# A branch production é apenas o ponto inicial do projeto; não aplique
# migrations de desenvolvimento nela. `--no-env-pull` impede que o link grave
# em disco a DATABASE_URL da production.
neon link --project-id <NEON_PROJECT_ID> --branch production --no-env-pull -y

# Cria (se preciso) e seleciona uma branch Neon isolada para esta feature e
# puxa as variáveis dela para o .env.local.
neon checkout feature-data-platform --create

# Gera a configuração declarativa Neon para este repositório.
neon config init --services none
```

Revise `neon.ts` e deixe-o exatamente assim nesta etapa, pois ainda não há serviços Neon adicionais a declarar:

```ts
import { defineConfig } from "@neon/config/v1";

export default defineConfig({});
```

Antes de aplicar, revise o plano/status. Em seguida, aplique a configuração declarativa e sincronize somente as variáveis PostgreSQL:

```powershell
# Sem --branch, status e deploy usam a branch padrão do projeto (production).
neon config status --branch feature-data-platform
neon deploy --branch feature-data-platform
neon env pull --service postgres
```

`neon deploy` nesta configuração vazia **não cria tabelas, migrations, schema `jobs` ou snapshots**. Ele apenas aplica a configuração Neon e mantém o ambiente local alinhado à branch Neon. Isso será feito nas próximas etapas com Alembic.

## Contexto e objetivo

O diagnóstico já foi concluído. O projeto deixará de depender de PostgreSQL local: o banco de produção será Neon PostgreSQL. Esta etapa prepara uma configuração única, segura e testável; ainda não cria tabelas nem muda a persistência do pipeline.

## Analise exatamente isto

- `docs/baseline.md`, `.env.example`, configurações atuais de SQLAlchemy e Docker.
- Onde `DATABASE_URL` é lida, montada ou assumida como localhost.
- Dependências necessárias para conexão PostgreSQL com SQLAlchemy.

## Implemente somente isto

1. Centralize a leitura de configuração em um módulo já compatível com a convenção do projeto (por exemplo `config.py`/`settings.py`), com validação clara de `DATABASE_URL`.
2. Faça a aplicação aceitar a URL fornecida pelo Neon sem expor segredo, inclusive variante SQLAlchemy adequada ao driver existente. A precedência deve ser: variável de ambiente já definida pelo sistema, depois `.env.local` gerado pelo Neon, depois `.env` local legado quando existir. Nunca copie a URL de `.env.local` para o código.
3. Atualize `.env.example` com `DATABASE_URL=postgresql+...://USER:PASSWORD@HOST/DB?sslmode=require` como exemplo fictício e inclua `COLLECTION_INTERVAL_DAYS` apenas como placeholder, sem implementar sua lógica.
4. Atualize `.gitignore` para proteger `.env`, `.env.local` e `.neon`, preservando `.env.example` e `neon.ts`.
5. Documente em `docs/neon-setup.md` os comandos acima, a diferença entre branch Git e branch Neon, como executar `neon checkout feature-data-platform`, como renovar a URL com `neon env pull --service postgres` e como cadastrar `DATABASE_URL` como GitHub Secret. Não inclua uma URL real.

## Arquivos/áreas esperados para revisão

Configuração de banco/API, `.env.example`, `.gitignore`, requirements e documentação.

## Tecnologias envolvidas

Neon PostgreSQL, PostgreSQL, SQLAlchemy, driver PostgreSQL usado pelo projeto e variáveis de ambiente.

## Como verificar a entrega

1. Sem `DATABASE_URL`, o projeto falha cedo com mensagem clara e sem imprimir segredos.
2. Com uma URL fictícia válida em `.env.local`, o carregamento de settings funciona em teste sem conexão de rede.
3. `neon config status` confirma o contexto Neon e `neon env pull --service postgres` conclui sem imprimir a URL.
4. `.env`, `.env.local`, `.neon`, tokens e arquivos de segredo são ignorados pelo Git; `.env.example` e `neon.ts` continuam versionados.
5. `docs/neon-setup.md` permite que o operador configure Neon, branch de desenvolvimento e GitHub Secrets manualmente.

## Armadilha importante

Não “teste” Neon colando uma connection string real no código, workflow ou log. A conexão real é configurada pelo operador no ambiente; o código só conhece o nome da variável. Não aplique migrations na branch Neon `production` durante esta etapa.

## Restrições

- Não criar tabelas ou migrations.
- Não colocar credenciais no código, logs, testes ou documentação.
- Não apontar automaticamente ambientes de desenvolvimento para produção; falhe com mensagem clara quando a configuração exigida estiver ausente.

## Testes

Adicione testes unitários para carregamento/validação de configurações, sem conexão de rede. Execute a suíte existente.

## Critérios de conclusão

- Uma única variável `DATABASE_URL` configura o banco remoto.
- Há exemplo seguro e instruções manuais de Neon/GitHub Secrets.
- Testes passam sem exigir credenciais reais.

## Encerramento obrigatório

Relate os arquivos alterados e testes. **PARE. Não configure Alembic, não crie schema e não altere o pipeline nesta etapa.**
