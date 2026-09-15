# Prompt 07a — Preparação segura para o merge na main

**Entrega:** `feature/data-platform` chega à `main` sem derrubar a API publicada no Render, sem deixar o cron diário falhando e com a primeira coleta automática observada numa branch Neon dedicada a dados reais.

> **Por que antes da 08:** até aqui tudo roda só na branch da feature. A `main` tem efeitos colaterais que a branch não tem: o Render publica a API a partir dela, e o `schedule` do `collect.yml` só roda nela. Fazer o merge sem preparar esses dois pontos troca uma API no ar por uma API fora do ar e um job vermelho por dia. E o histórico que a etapa 08 analisa só começa a se acumular quando a coleta agendada roda na `main`.

---

## O que mostrar antes

Mostre o estado real que torna o merge arriscado hoje, **sem imprimir nenhuma URL**:

- `render.yaml`: o `startCommand` roda `import_csv.py --recriar`, que faz `drop_all` a cada boot, e não há `DATABASE_URL` declarada;
- `api/database.py`: a API só sobe com `DATABASE_URL` PostgreSQL (não existe mais fallback para SQLite pelo ambiente);
- `gh secret list`: não há `DATABASE_URL`;
- `gh variable list`: `COLLECTION_INTERVAL_DAYS=2` já existe;
- `git rev-list --count main..feature/data-platform`: quantos commits vão entrar;
- última execução da CI da branch: verde nas duas versões de Python;
- o log da última coleta real: as falhas da GeekHunter com `external_id com mais de 40 caracteres`.

## Contexto e objetivo

As etapas 00 a 07 foram feitas na `feature/data-platform`: Neon como fonte de verdade, migrations, histórico, persistência idempotente, CI, coleta agendada a cada 2 dias com guarda, encerramento de vagas e dashboard local. Nada disso está na `main`.

A `main` alimenta dois consumidores automáticos:

1. **Render**: a API `vagas-tech-junior-api.onrender.com` é publicada a partir da `main`.
2. **GitHub Actions**: o `schedule` do `collect.yml` só roda a versão que está na branch padrão.

O objetivo é preparar os dois **antes** do merge, fazer o merge por pull request com a CI verde e observar a primeira coleta. Decisões já tomadas pelo operador:

- **A API passa a ler do Neon.** `DATABASE_URL` é declarada no `render.yaml` com `sync: false` e cadastrada à mão pelo operador no painel do Render.
- **O boot só sobe a API.** O `startCommand` fica só com `uvicorn`, sem `import_csv` e sem `--recriar`. O seed é importado **uma única vez** na branch Neon da `main`: o banco persiste, e o plano free do Render roda o boot a cada vez que o serviço acorda — importar ali custaria minutos a cada despertar, porque o importador faz uma consulta por linha.
- **A `main` usa uma branch Neon nova e dedicada**, chamada `dados-main`. Ela serve à coleta automática e à API. A `production` continua intocada, como manda `docs/neon-setup.md`; a `feature-data-platform` continua sendo só de desenvolvimento.
- **O Secret `DATABASE_URL` do GitHub pode ser cadastrado pelo assistente**, com confirmação do operador naquele passo, lendo a URL de um arquivo fora do repositório e passando por stdin: o valor nunca aparece em linha de comando, histórico ou saída.

Bug bloqueante encontrado na coleta real de 15/09/2026: a GeekHunter passou a publicar o `identifier` do `JobPosting` como hash de **64 caracteres**, e `jobs.external_id`/`vagas.external_id` são `VARCHAR(40)`. As 36 vagas dela não foram gravadas, a execução terminou com exit 1 — na `main`, toda coleta agendada ficaria vermelha — e o `seed/vagas.csv` (35 linhas da GeekHunter com id de 64 caracteres) nem entraria num PostgreSQL, porque o importador grava tudo num commit só.

O deploy completo (plataforma, CORS, dashboard publicado, rollback formal) continua sendo a etapa 15. Esta etapa só impede que o merge quebre o que já funciona.

## Analise exatamente isto

- `render.yaml`: `buildCommand`, `startCommand`, `healthCheckPath` e `envVars`.
- `scripts/import_csv.py`: o que muda com e sem `--recriar`, e o custo de uma consulta por linha contra um banco remoto.
- `api/app.py` e `api/database.py`: lifespan, `init_db`, `/health` e a exigência de `DATABASE_URL` PostgreSQL.
- `scraper/sources/geekhunter.py` (`_identificador`), `api/models.py` e `persistence/repositorio.py` (`_validar_identidade`): tamanho real dos ids por fonte e da coluna.
- `.github/workflows/collect.yml`: o que acontece na primeira execução agendada depois do merge sem Secret ou com schema atrasado (exit 2).
- `docs/neon-setup.md`, `docs/migrations.md` e `docs/automation.md`: como criar branch Neon, puxar variáveis para um arquivo fora do repositório, aplicar migrations e cadastrar o Secret.
- Branch protection e forma de merge da `main` (`gh api repos/{owner}/{repo}/branches/main/protection`, só leitura).

## Implemente somente isto

0. **Corrigir o tamanho do `external_id`.**
   - Alargue `jobs.external_id` e `vagas.external_id` para `VARCHAR(100)` com uma migration (`batch_alter_table` + `alter_column`) e o mesmo tamanho em `api/models.py`. Não corte o id: um id truncado viraria outra vaga.
   - Ajuste o teste que usa um id longo demais (`"x" * 41` passa a `"x" * 101`) e acrescente um teste que grava um id de 64 caracteres da GeekHunter sem falha; `tests/api/test_migrations.py` confere o tamanho 100 nas duas tabelas.
   - Confirme na branch Neon da feature: `alembic upgrade head` e `python main.py --sources geekhunter` terminam com 0 falhas.

1. **Branch Neon `dados-main`.**
   - Crie a branch a partir da `production`, sem expiração e sem imprimir segredos:
     `neon branches create --name dados-main --parent production --no-secrets`.
   - Puxe as variáveis dela para um arquivo **fora do repositório**:
     `neon env pull --branch dados-main --service postgres --file <fora-do-repo>/dados-main.env`.
   - Rode `alembic current` **carregando `DATABASE_URL_UNPOOLED` só no ambiente do comando**, sem alterar o `.env.local` de desenvolvimento. Se houver tabelas sem `alembic_version`, pare e reporte — nada de `stamp` às cegas.
   - Aplique `alembic upgrade head` e confira com `alembic current` (a revisão deve ser a `head`).
   - **Importe o seed uma única vez**, com a URL vinda do arquivo: `scripts.import_csv.importar(seed/vagas.csv, db=<url>, referencia=2026-09-15)`, imprimindo só `criadas`, `atualizadas` e `total` (597 esperado), nunca o campo `db`.
   - Nunca copie o conteúdo desse arquivo para logs, commits, issues ou para a conversa.

2. **API no Render lendo do Neon (`render.yaml`).**
   - Declare `DATABASE_URL` em `envVars` com `sync: false`. É o formato do Blueprint do Render para variável cujo valor é preenchido no painel, nunca no git.
   - O `startCommand` passa a ser só `uvicorn api.app:app --host 0.0.0.0 --port $PORT`: sem `import_csv` e sem `--recriar`.
   - Atualize o comentário do `render.yaml`: o banco é o Neon `dados-main`; o seed foi importado uma vez e se reimporta à mão quando mudar.
   - Crie `tests/test_render_yaml.py`, no estilo de `tests/test_workflows.py`:
     - `DATABASE_URL` declarada com `sync: false` e **sem** `value`, e nenhuma URL de banco no arquivo;
     - nenhum `import_csv` nem `--recriar` no `startCommand`;
     - `healthCheckPath` continua `/health`;
     - o `buildCommand` continua usando `requirements-api.txt`.

3. **Variáveis e segredos, antes do merge.**
   - **Render (operador):** *Dashboard → vagas-tech-junior-api → Environment → Add Environment Variable* `DATABASE_URL` com a URL **pooled** da `dados-main` (`neon connection-string dados-main --pooled` no terminal do operador). Salvar dispara um redeploy do commit **antigo** da `main`, que já lê `DATABASE_URL` e ainda roda `import_csv.py --recriar`. Esse deploy **falha** com `InternalError`: o PostgreSQL recusa apagar `tecnologias`, referenciada por `job_snapshot_tecnologias`, e a transação do `drop_all` é desfeita. É esperado e inofensivo — o Render mantém o deploy anterior no ar e a `dados-main` fica intacta. Confirme `/health` `200` e as contagens da `dados-main` (tabelas, `alembic_version`, `vagas`) e faça o merge logo: até lá, qualquer novo deploy do código antigo falha do mesmo jeito.
   - **GitHub (assistente, com confirmação):** leia a URL **pooled** do arquivo da `dados-main` e passe por stdin para `gh secret set DATABASE_URL`, sem imprimir o valor. Confirme com `gh secret list`, que mostra só o nome.
   - `COLLECTION_INTERVAL_DAYS=2` já está cadastrada; confirme com `gh variable list`.

4. **Merge por pull request.**
   - Abra o PR `feature/data-platform → main` com `gh pr create`. A descrição resume as etapas 00–07, o bug da GeekHunter corrigido, os passos externos já feitos (branch Neon, seed, variável no Render, Secret, Variable) e o que muda para a API e para a automação.
   - Espere a CI do PR ficar verde nas duas versões de Python.
   - **Só faça o merge com autorização explícita do operador**, usando merge commit (preserva o histórico das etapas). Não apague a branch da feature.

5. **Verificação pós-merge, na ordem.**
   1. **Render:** acompanhe o deploy da `main`; `GET /health` responde `200`, e `GET /areas` e `GET /vagas?limit=1` respondem com os dados do seed vindos da `dados-main`.
   2. **Coleta sem banco:** `gh workflow run collect.yml --ref main -f modo=sem-banco -f fontes="gupy" -f max_paginas=1`. Confirme no *Summary* que o portal respondeu a partir do IP do GitHub.
   3. **Coleta com banco:** `gh workflow run collect.yml --ref main` (força a coleta completa, que é o padrão do disparo manual). Confirme no *Summary*: status, vagas por fonte e a frase "Última coleta: dia … e próxima: dia …".
   4. **Registro no banco:** conte as linhas de `collection_runs` e de `jobs` com `is_active` na `dados-main`, imprimindo só números e datas.
   5. **Agendamento:** confirme em *Actions → Coleta de vagas* que o workflow está habilitado e registre a data da próxima execução prevista.

6. **Documentação.**
   - `docs/neon-setup.md`: troque a seção "Deploy no Render: atenção" pelo desenho atual: quais branches Neon existem e para que serve cada uma (`production`, `feature-data-platform`, `dados-main`), onde cada `DATABASE_URL` é cadastrada (Render, GitHub Secret, `.env.local`) e como reimportar o seed.
   - `docs/automation.md`: diga que o Secret aponta para `dados-main` e acrescente o roteiro pós-merge acima.
   - `docs/data-model.md`: `external_id` com 100 caracteres, e o motivo.
   - `README.md` (seção "Deploy") e `CLAUDE.md`: o banco da API deixa de ser reconstruído do seed a cada boot.
   - Crie `docs/rollback-merge.md` curto, com:
     - reverter o merge commit (`git revert -m 1 <merge>` via PR);
     - voltar ao deploy anterior pelo painel do Render;
     - pausar a coleta (`gh workflow disable collect.yml`);
     - o que **não** fazer: `alembic downgrade` ou apagar a branch `dados-main`, que tem o histórico.
   - `docs/roadmap-status.md`: acrescente `07a — Preparação segura para o merge na main` entre 07 e 08.

## Arquivos/áreas esperados para revisão

Migration e `api/models.py` (`external_id`), `render.yaml`, `tests/test_render_yaml.py`, `tests/api/test_persistencia.py`, `tests/api/test_migrations.py`, `docs/neon-setup.md`, `docs/automation.md`, `docs/data-model.md`, `docs/rollback-merge.md`, `docs/roadmap-status.md`, `README.md`, `CLAUDE.md`, descrição do PR.

## Tecnologias envolvidas

Render (Blueprint e variáveis de ambiente), Neon (branches e CLI), Alembic, GitHub Actions, GitHub Secrets/Variables, GitHub CLI.

## Como verificar a entrega

1. A coleta só da GeekHunter termina com 0 falhas depois da migration do `external_id`.
2. A branch Neon `dados-main` existe, `alembic current` mostra a `head` e o seed tem 597 vagas, sem nenhuma URL impressa.
3. `render.yaml` declara `DATABASE_URL` com `sync: false` e o `startCommand` é só `uvicorn`; `tests/test_render_yaml.py` passa.
4. Depois de cadastrar a variável no Render, e ainda antes do merge, `/health` continua `200`.
5. O PR tem CI verde e só é mesclado com autorização explícita.
6. Depois do merge: `/health` responde `200`, a coleta `sem-banco` e a coleta com banco terminam com resumo no *Summary*, e `collection_runs` da `dados-main` tem a execução registrada.

## Armadilha importante

A ordem importa. Se o merge acontecer antes da variável no Render, a API cai no próximo deploy; se acontecer antes do Secret, das migrations e do seed na `dados-main`, a primeira execução agendada termina com exit 2 e a API sobe sem dados. Corrija o `external_id`, cadastre tudo, confira `/health` e **só então** faça o merge.

A segunda armadilha é o boot: com a API apontando para um banco persistente, `--recriar` apagaria o banco a cada boot, e importar o seed a cada boot deixaria cada despertar do plano free minutos mais lento. O `startCommand` só com `uvicorn` precisa entrar no mesmo commit que declara a `DATABASE_URL`.

## Restrições

- Não aplique nada na branch Neon `production`, e não use a `feature-data-platform` para a `main`.
- Nunca imprima, commite ou cole em logs a URL do banco; a variável do Render é cadastrada pelo operador.
- Não faça o merge, não dispare workflows, não crie branch Neon e não cadastre segredos sem autorização explícita do operador em cada passo externo.
- Não corte `external_id` para caber na coluna.
- Não publique o dashboard, não configure CORS, não mexa em Docker nem troque de plataforma: isso é a etapa 15.
- Não apague a branch `feature/data-platform`.

## Testes

Rode `python -m pytest -q` com a migration do `external_id`, `tests/test_render_yaml.py` e o teste do id de 64 caracteres incluídos. Valide o YAML do `render.yaml`. Antes do merge, confira a coleta da GeekHunter na branch da feature e o `/health` da API publicada depois do cadastro da variável. Depois do merge, execute o roteiro de verificação pós-merge completo.

## Critérios de conclusão

- A `main` tem todo o trabalho das etapas 00–07, a GeekHunter grava sem falhas e a API continua no ar lendo do Neon `dados-main`.
- O cron diário roda com Secret e schema corretos, e a primeira coleta pela `main` está registrada em `collection_runs`.
- Rollback e desenho de branches/variáveis estão documentados.

## Encerramento obrigatório

Liste os passos externos executados (com quem os fez), o link do PR, o resultado do `/health` e das duas coletas pós-merge. **PARE. Não inicie a etapa 08, não publique o dashboard nem avance para o deploy da etapa 15.**
