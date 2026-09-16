# Rollback de um merge na `main`

O que fazer se um merge na `main` quebrar a API, o dashboard ou a coleta. O caso
que motivou este guia foi o merge da `feature/data-platform` (PR #1).

Do dashboard no Streamlit, o rollback está em `docs/deploy.md`. Os passos são independentes: aplique só o que resolve o sintoma.

| Sintoma | Primeiro passo |
|---|---|
| A coleta agendada falha todo dia | pausar a coleta |
| A API caiu depois do deploy | voltar o deploy no Render |
| O problema está no código da `main` | reverter o merge |

## 1. Pausar a coleta

```powershell
gh workflow disable collect.yml
```

Nada é apagado: o workflow só deixa de rodar, inclusive o `schedule`. Para
voltar: `gh workflow enable collect.yml`.

## 2. Voltar o deploy da API

*Render → vagas-tech-junior-api → Events*: escolha o último deploy que estava
saudável e use **Rollback**. A API volta a servir aquela versão enquanto a causa
é investigada.

Se o problema for só a variável `DATABASE_URL` (removida ou errada), corrija em
*Environment*. Salvar dispara um redeploy.

## 3. Reverter o merge

A `main` é protegida: o revert só entra **por pull request**, com o CI verde.

```powershell
git switch main
git pull
git switch -c revert-<nome-do-pr>
git revert -m 1 <hash-do-merge-commit>
git push -u origin revert-<nome-do-pr>
gh pr create --base main --title "Reverte o PR #<número>" --body "..."
```

`-m 1` mantém o lado da `main` como base. O GitHub apaga a branch do PR depois
do merge, mas os commits dela continuam na história da `main`. Para corrigir,
recrie a branch pelo último commit dela (`git branch <nome> <hash>`) ou crie uma
nova a partir da `main`, e abra um novo PR.

**Atenção ao reverter o PR #1 (`feature/data-platform`):** o código anterior a ele usa `render.yaml` com
`import_csv.py --recriar`. Com a `DATABASE_URL` da `dados-main` cadastrada no
Render, esse boot **apagaria as tabelas da `dados-main`**. Antes de mesclar o
revert, **remova a `DATABASE_URL` do painel do Render**. Sem ela, o código antigo
volta a usar o SQLite do seed, como antes.

## O que não fazer

- **Não rode `alembic downgrade` na `dados-main`.** As migrations de histórico
  apagam `jobs`, `job_snapshots` e `collection_runs` no downgrade, e com elas
  todas as coletas acumuladas.
- **Não apague a branch Neon `dados-main`.** É ela que guarda o histórico real.
- **Não use `import_csv.py --recriar` contra a `dados-main`.**
