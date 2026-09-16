# Classificação: relevância, área, modalidade e tecnologias

Como uma vaga de nível de entrada vira uma linha classificada. Esta etapa roda
dentro de `scraper/pipeline.py`, depois do filtro de senioridade e da deduplicação
e antes da gravação no banco (fluxo completo em [`architecture.md`](architecture.md)).
As regras ficam em `scraper/rules/*.yml`; o código em `scraper/classifier.py` e
`scraper/skills.py`.

## Portão de relevância ("é vaga de tech?")

A busca dos portais é solta e devolve muita coisa que não é tecnologia
(`Analista Contábil Jr`, `Analista Fiscal Jr`, `Analista de Ouvidoria Junior`).
Se essas vagas ficassem no dataset, o ranking mediria a população errada — na
primeira execução deste projeto elas representavam **48%** do total.

O **título** é o sinal confiável; a descrição nem sempre é (o Vagas.com só
devolve um trecho de marketing, cheio de palavra genérica como "sistemas" ou
"aplicação", que apareceria até numa vaga administrativa). Por isso o portão tem
listas com rigor diferente, em `tech_gate` no `areas.yml`:

1. título casa `tech_gate.titulo` (sinais amplos), **ou**
2. título casa uma keyword `peso_alto` de qualquer área, **ou**
3. descrição casa `tech_gate.descricao` (sinais estritos) ou uma `peso_alto`.

E `tech_gate.excluir` derruba contextos onde as palavras acima não significam
tecnologia: "Pesquisa e Desenvolvimento" (P&D industrial), "Odontologia Digital",
"Segurança do Trabalho", "Tecnologia Educacional".

## Classificação por área

Cada área tem keywords em duas faixas de peso (`peso_alto` = 4.0,
`peso_medio` = 1.0). Keyword encontrada no **título** vale 3× o que vale na
descrição (`title_boost`), porque o título é muito mais confiável.

Duas regras evitam classificação por evidência frágil:

- **Título dominante** — se alguma área foi sinalizada pelo título, só essas
  áreas disputam. Sem isso, uma descrição longa da Gupy que cita "dados" de
  passagem ("proteção de dados", "dados cadastrais") transformava uma vaga de
  *Governança de TI* em vaga de *Data*.
- **`min_score` = 3.0** (o valor de uma keyword `peso_medio` no título) — abaixo
  disso a vaga cai em "Outros/TI Geral". Um único "dados" solto numa descrição
  não basta para definir a área.

O efeito é que "Outros/TI Geral" concentra títulos como "Estágio em TI",
"Estágio em Desenvolvimento" ou "Desenvolvedor de Software Jr", dos quais
realmente **não dá** para inferir a área. Preferi deixá-los explícitos a
distribuí-los por chute. O tamanho dessa fatia depende da coleta e das fontes (na
de 15/09/2026 foi um terço, puxado pelo LinkedIn, que não traz descrição): veja
[`resultados-2026-09-15.md`](resultados-2026-09-15.md) e o dashboard.

As keywords são casadas como palavra/frase inteira sobre o texto normalizado
(minúsculas, sem acento, pontuação virando espaço). Isso evita que "go" case
dentro de "Goiânia" ou "java" dentro de "javascript".

## Modalidade de trabalho

As vagas são classificadas em **Remoto**, **Híbrido**, **Presencial** e
**Não informado**, com origens diferentes por portal:

- **Gupy** expõe a modalidade explicitamente no campo `workplaceType`
  (`remote` / `hybrid` / `on-site`) — é dado afirmado pelo portal.
- As demais fontes leem a modalidade de flags nativas ou do local do card, cada
  uma no seu arquivo em `scraper/sources/`; os casos que mudam a leitura estão em
  [`fontes.md`](fontes.md).
- **Vagas.com** classifica as vagas em três modalidades ("Na empresa",
  "Na empresa e Home Office", "100% Home Office"), mas **o card da listagem só
  mostra "100% Home Office" ou o nome da cidade** — um card híbrido e um
  presencial são indistinguíveis ali. Por isso só o remoto é afirmado; o resto
  fica como "Não informado" em vez de ser adivinhado como presencial.

As três modalidades existem como filtro de busca no Vagas.com, mas os resultados
filtrados não reconciliam com a paginação da busca normal (para alguns termos o
filtro "Na empresa" sozinho já devolve a página inteira), então esse caminho foi
descartado.

## Extração de tecnologias

Cada vaga é varrida atrás das tecnologias listadas em
`scraper/rules/skills.yml` (linguagens, frameworks, bancos, cloud, ferramentas
de dados/QA/suporte e práticas como Scrum e Inglês). O resultado é gravado no snapshot
(`job_snapshot_tecnologias`), alimenta a coluna `skills` do CSV e o gráfico de
tecnologias por área.

A extração roda **antes** da exportação de propósito: o CSV trunca a descrição
em 500 caracteres, e a Gupy devolve descrições longas onde a maior parte das
tecnologias é citada.

Aqui o texto passa por uma normalização própria que **preserva `#` e `+`** — com
a normalização padrão do projeto, `C#` viraria `c` e casaria com qualquer letra
"c" solta no texto.

## Gráficos

Duas decisões de forma, ambas visíveis em `scraper/charts.py`:

- **Uma cor só, não um degradê por valor.** Áreas de tecnologia são categorias
  *nominais* (não têm ordem natural). Pintar a barra maior mais escura gastaria
  o canal de cor repetindo o que o comprimento da barra já diz.
- **Small multiples para as tecnologias** — um painel por área, em vez de 8 cores
  disputando a mesma figura. A pergunta é "quais techs nesta área?", e cada
  painel responde isso sozinho.

O raio do canto arredondado é calculado em **pixels** e convertido para unidades
de dado de cada painel. O caminho óbvio no matplotlib (raio fixo em unidades de
dado) deforma o canto quando os eixos têm escalas diferentes: num painel cujo
eixo x vai só até 3, o raio vira uma "pílula" horizontal.

## Editando as regras

Toda a lógica de negócio está em três YAMLs comentados — **você não precisa
mexer em Python para ajustar**:

- **`scraper/rules/areas.yml`** — áreas, keywords, pesos e o portão de relevância.
- **`scraper/rules/seniority.yml`** — o que conta como nível de entrada e o que
  é nível acima.
- **`scraper/rules/skills.yml`** — tecnologias procuradas e seus apelidos.

Duas armadilhas já documentadas lá dentro, aprendidas rodando com dados reais:

- não coloque `data` como keyword de Data: em português casa com "**data** de
  admissão";
- não coloque `seguranca` sozinho na área Segurança: casa com "normas de
  **segurança**" no boilerplate de qualquer vaga de suporte, e com "**Segurança**
  do Trabalho". Isso inflou a área de 4 para 45 vagas na primeira execução.
