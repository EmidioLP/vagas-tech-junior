# Deploy do dashboard

O dashboard (`dashboard/app.py`) é publicado no **Streamlit Community Cloud**
(gratuito). Ele lê a branch Neon `dados-main` com um **papel Postgres só de
leitura**. A API continua no Render (`render.yaml`); esta página cobre só o
dashboard.

Nada aqui é automático. O repositório só guarda a configuração, e os passos com
conta (Neon e Streamlit) são manuais e estão descritos abaixo.

## Resumo

| Item | Valor |
|---|---|
| URL | <https://vagas-tech-junior.streamlit.app/> |
| Plataforma | Streamlit Community Cloud, plano gratuito |
| Repositório / branch | `EmidioLP/vagas-tech-junior`, `main` |
| Entrypoint | `dashboard/app.py` |
| Dependências | `dashboard/requirements.txt` → `requirements-dashboard.txt` |
| Python | 3.13 (a mesma versão testada no CI) |
| Banco | Neon, branch `dados-main`, URL **pooled**, papel `dashboard_leitura` |
| Secret | `DATABASE_URL` (só no painel do Streamlit) |
| Custo | zero; o app hiberna depois de alguns dias sem acesso e acorda no primeiro acesso |

## Como a configuração chega no app

- O Streamlit Cloud grava os *Secrets* do painel num `secrets.toml`. **Chaves na
  raiz do TOML viram variáveis de ambiente** quando o servidor sobe.
- `scraper.config.obter_database_url` lê `DATABASE_URL` do ambiente antes de
  `.env.local` e `.env`, que não existem no servidor. Por isso o código não usa
  `st.secrets` e roda igual localmente e na nuvem.
- **Nenhum segredo no git.**
  - `.env*` e `.streamlit/secrets.toml` estão no `.gitignore`.
  - A URL só existe no painel do Streamlit e no Neon.
- **Somente leitura em três camadas:**
  - o papel `dashboard_leitura` só tem `SELECT`;
  - o papel abre toda transação como `READ ONLY` por padrão;
  - o engine do dashboard pede `READ ONLY` por transação (`dashboard/config.py`).

## 1. Criar o papel só de leitura (Neon, uma vez)

Crie o papel **por SQL**, nunca pelo console nem pelo CLI do Neon: papéis criados
por lá entram no `neon_superuser` e ganham permissão de escrita.

1. Gere uma senha forte na sua máquina (o Neon exige pelo menos 60 bits de
   entropia para papéis criados por SQL):

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. No console do Neon, abra o **SQL Editor** na branch **`dados-main`**, database
   `neondb`, e rode, trocando `<SENHA>` pela senha gerada:

   ```sql
   CREATE ROLE dashboard_leitura WITH LOGIN PASSWORD '<SENHA>';
   GRANT CONNECT ON DATABASE neondb TO dashboard_leitura;
   GRANT USAGE ON SCHEMA public TO dashboard_leitura;
   GRANT SELECT ON jobs, job_snapshots, job_snapshot_tecnologias, tecnologias, collection_runs
       TO dashboard_leitura;
   ALTER ROLE dashboard_leitura SET default_transaction_read_only = on;
   ```

   As cinco tabelas são exatamente as que `dashboard/consultas.py` lê. Se uma
   etapa futura fizer o dashboard ler outra tabela, ela precisa de um `GRANT
   SELECT` novo. Sem ele, a página mostra "Dados indisponíveis", nunca um erro
   com detalhes.

3. Monte a URL **pooled**. Pegue a connection string pooled da `dados-main` no
   Neon (*Connect* → *Connection pooling* ligado) e troque só o usuário e a senha:

   ```
   postgresql://dashboard_leitura:<SENHA>@<host>-pooler.<região>.aws.neon.tech/neondb?sslmode=require&channel_binding=require
   ```

   A senha gerada pelo `token_urlsafe` só usa letras, números, `-` e `_`, então não
   precisa ser escapada na URL.

4. Confira, da raiz do repositório, que o papel **lê mas não grava**. A variável
   vale só para esta sessão do terminal:

   ```powershell
   $env:DATABASE_URL = "<URL do passo 3>"
   python -c "from sqlalchemy import create_engine, text; from api.database import database_url; c = create_engine(database_url()).connect(); print('vagas:', c.execute(text('SELECT count(*) FROM jobs')).scalar()); c.execute(text('UPDATE jobs SET url = url WHERE false'))"
   Remove-Item Env:DATABASE_URL
   ```

   Primeiro aparece `vagas: <número>`. Depois o `UPDATE` precisa falhar com
   `ReadOnlySqlTransaction` (`cannot execute UPDATE in a read-only transaction`)
   ou `InsufficientPrivilege` (`permission denied for table jobs`). Se o `UPDATE`
   passar sem erro, **não publique**: revise o passo 2.

## 2. Publicar no Streamlit Community Cloud

**Antes de publicar:** o código do dashboard precisa estar na `main`.

1. Entre em <https://share.streamlit.io> com a conta do GitHub dona do repositório.
2. Clique em **Create app** → **Deploy a public app from GitHub** e preencha:
   - **Repository:** `EmidioLP/vagas-tech-junior`
   - **Branch:** `main`
   - **Main file path:** `dashboard/app.py`
   - **App URL:** um subdomínio, por exemplo `vagas-tech-junior`
3. Em **Advanced settings**:
   - **Python version:** 3.13
   - **Secrets:** a URL do passo 1 na raiz do TOML, sem seção:

     ```toml
     DATABASE_URL = "postgresql://dashboard_leitura:<SENHA>@<host>-pooler.<região>.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
     ```

4. Clique em **Deploy**. O build instala `dashboard/requirements.txt` (Streamlit,
   SQLAlchemy, psycopg e python-dotenv) e sobe o app.

O app é redeployado sozinho a cada push na `main`.

## 3. Verificação pós-deploy

1. **Overview abre sem o aviso "Dados indisponíveis".** A "Última coleta" precisa
   bater com a última execução completa da `dados-main`:

   ```sql
   SELECT started_at, status FROM collection_runs
   WHERE full_scope AND status IN ('success', 'partial')
   ORDER BY started_at DESC LIMIT 1;
   ```

   A tela mostra o horário de Brasília (UTC-3).
2. **As quatro páginas abrem** e um filtro de área muda os números.
3. **Nada sensível na tela.** Nenhuma URL, host ou usuário, nem nos avisos.
4. **Nos logs do app** (*Manage app* no canto inferior direito), sem traceback.

Se aparecer "Dados indisponíveis (…)":

| Tipo do erro | Causa provável |
|---|---|
| `ConfiguracaoError` | secret ausente, com nome diferente de `DATABASE_URL` ou dentro de uma seção `[...]` |
| `OperationalError` | senha errada, host errado ou papel sem `CONNECT` |
| `InsufficientPrivilege` / `ProgrammingError` | faltou `GRANT SELECT` em alguma tabela |

## Rollback

| Situação | O que fazer |
|---|---|
| Uma mudança quebrou o dashboard | `git revert <commit>` na `main` e push. O app redeploya sozinho com o código anterior |
| Precisa tirar do ar já | *Manage app* → **Delete app** (ou *Reboot* se for só travamento). Publicar de novo é repetir o passo 2 |
| Credencial vazou | No SQL Editor da `dados-main`: `ALTER ROLE dashboard_leitura NOLOGIN;` corta o acesso na hora. Depois `ALTER ROLE dashboard_leitura LOGIN PASSWORD '<nova>';` e atualize o secret no painel |
| Remover o papel de vez | `DROP OWNED BY dashboard_leitura; DROP ROLE dashboard_leitura;` (ele não é dono de nada; o `DROP OWNED` só revoga os grants) |

O dashboard não grava nada. Nenhum rollback envolve os dados.

## Limites do plano gratuito

- **Hibernação.** O app hiberna depois de alguns dias sem acesso. O primeiro
  visitante vê um botão para acordá-lo, e a subida leva cerca de 1 minuto.
- **Recursos.** Os recursos são limitados (cerca de 1 GB de memória). As
  consultas trazem só agregados e páginas de 50 vagas; a série histórica carrega
  `jobs` e snapshots do período em memória, o que cabe folgado no volume atual
  (centenas de vagas por coleta).
- **Neon.** O compute da `dados-main` também dorme sem uso. A primeira consulta
  depois disso demora alguns segundos, e o cache de 10 minutos do dashboard
  reduz as idas ao banco.
