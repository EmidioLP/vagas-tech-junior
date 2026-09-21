# ADR 0008 — Taxonomia de áreas expandida, com reclassificação do histórico

- **Status:** aceito
- **Data:** 21/09/2026

## Contexto

A taxonomia tinha 9 áreas mais o balde-resto `Outros/TI Geral`. Esse resto era a
**maior fatia da coleta**: 206 dos 603 snapshots de 15/09/2026 (34,2%). Dizer "a
maior área é 'Outros'" não responde a pergunta do projeto.

Todos os números abaixo vêm da **`dados-main`**, com a descrição completa. Não do
`seed/vagas.csv`, que trunca a descrição em 500 caracteres — 327 dos 603 snapshots
de 15/09 têm texto mais longo que isso, e classificar pelo CSV dá outro resultado
(chegou a inverter as duas primeiras colocadas). Validação da fonte: as regras
antigas sobre o texto do banco reproduzem exatamente as 122 vagas de
`Suporte/Infra` publicadas em [`../resultados-2026-09-15.md`](../resultados-2026-09-15.md).

O [tech-skills-br](https://github.com/diasgarcia/tech-skills-br), derivado deste
projeto, usa 17 áreas e tem só 4,2% em `Outros`. Ele roda o **mesmo motor de
classificação** — `title_boost: 3.0`, `min_score: 3.0`, `peso_alto: 4.0`,
`peso_medio: 1.0` são idênticos. A diferença estava no vocabulário, não no
algoritmo.

Rodamos o nosso classificador com as regras deles sobre as nossas 597 vagas, e
depois com as regras novas escritas aqui:

| | Regras antigas | Regras novas | tech-skills-br |
|---|---|---|---|
| `Outros/TI Geral` | 206 (34,2%) | **65 (10,8%)** | 66 |
| Engenharia de Software | — | **156** | 160 |
| Suporte Técnico | 122 (como `Suporte/Infra`) | 126 | 102 |
| Backend | 92 | 54 | 60 |

A discordância vaga a vaga com o tech-skills-br ficou em 11,8%. A maior parte são
desvios deliberados (abaixo); a maior divergência não deliberada é
`Infraestrutura / Redes`, onde eles pegam 24 vagas e nós 9 — o vocabulário de
infra deles é mais largo, e isso é candidato a revisão.

Dois achados da medição mudaram o desenho:

- **Dividir `Suporte/Infra` não fragmenta o suporte.** `Suporte Técnico` sozinho
  fica com praticamente todo o balde antigo; as outras quatro sub-áreas somam ~27
  vagas e vieram do `Outros`, não do suporte.
- **`Backend` estava inflado.** Cai de 92 para 54. A maior parte das saídas são
  títulos como "Desenvolvedor Júnior" e "Analista de Sistemas Jr", que eram
  empurrados para Backend sem nenhuma evidência de serem backend. O "Backend em 2º
  lugar" dos relatórios anteriores era em parte artefato da taxonomia estreita.

## Decisão

- **16 áreas mais `Outros/TI Geral`**, nos nomes do tech-skills-br, para os dois
  conjuntos de dados poderem ser comparados. `Suporte/Infra` vira `Suporte Técnico`,
  `Service Desk / Help Desk`, `Infraestrutura / Redes`, `Field Service / Hardware` e
  `Hardware / Eletrônica`; entram `Engenharia de Software`, `Sistemas / ERP` e
  `Inteligência Artificial`.
- **Faixa `peso_generico` nova no classificador.** Foi o que a medição obrigou a
  criar. `classify()` tem a regra do título dominante: se alguma área casa no
  título, só ela disputa. Pôr "desenvolvedor junior" em `Engenharia de Software`
  fazia **todo** título genérico de dev calar a descrição — "Desenvolvedor Júnior"
  com descrição de ETL e Airflow deixava de ser Data. Keyword em `peso_generico`
  pontua igual a `peso_medio` mas **não marca `title_score`**, então dá a área de
  último recurso sem impedir a descrição de decidir.
- **Reclassificar o histórico** com `scripts/reclassificar_areas.py`, que refaz a
  área a partir de `title` + `description` guardados e **recalcula o
  `content_hash`**. Medido: sem recalcular, a coleta seguinte gravaria 426
  snapshots (71% das vagas) para uma mudança de estado que nunca houve; com
  recálculo, zero.
- **Desvios deliberados em relação ao tech-skills-br**, documentados por serem
  discordância e não descuido: RPA e low-code vão para `Engenharia de Software`, não
  para `Backend`; `Design / UI / UX` não entra (zero vagas na nossa amostra e é
  escopo que o projeto não reivindica); "atendimento" solto fica fora de
  `Suporte Técnico`, pela mesma razão que "seguranca" solto está fora de `Segurança`.
- O `areas.yml` deriva do tech-skills-br, que é MIT. O crédito fica aqui e no
  cabeçalho do arquivo.

## Consequências

- **Ganha:** `Outros/TI Geral` deixa de ser a maior fatia e vira o que o nome diz;
  a resposta do projeto passa a distinguir suporte de service desk e de
  infraestrutura; e os números ficam comparáveis com um segundo conjunto de dados
  independente, de nove portais e nove meses.
- **Custa:**
  - **a manchete do projeto muda.** `Engenharia de Software` (156) passa a ser a
    maior área, à frente de `Suporte Técnico` (126). A família de suporte inteira
    soma 153, praticamente empatada com ela. E `Engenharia de Software` é, por
    construção, um balde para dev sem stack declarada — um catch-all, só que
    nomeado. Se crescer, vira o novo `Outros`;
  - **a comparação com os relatórios datados quebra.** `docs/resultados-2026-09-15.md`
    continua com a taxonomia da época e **não** é reescrito: é registro, não
    número atual. Quem ler os dois lado a lado vê áreas diferentes para a mesma
    coleta;
  - a série histórica só fica coerente porque o histórico foi reclassificado. Isso
    só é possível porque `job_snapshots.description` guarda o texto completo — o
    ADR [0004](0004-sem-medalhao-nem-dbt.md) diz que não dá para reprocessar o
    passado, o que vale para o bruto do portal, mas **não** para a área;
  - **o dashboard perde cobertura nos painéis de tecnologia por área.** Medido na
    coleta de 15/09: antes, 7 de 10 áreas passavam de `BASE_MINIMA_POR_AREA` (15) e
    os painéis cobriam 92% das vagas com tecnologia; agora são 6 de 17 e 77%.
    Frontend e QA perdem o painel (QA a uma vaga do limite). O limite **não** foi
    baixado: ele existe por confiabilidade estatística, e afrouxá-lo para fazer
    painel aparecer seria ajustar a régua ao resultado. A cobertura volta sozinha à
    medida que o histórico cresce;
  - `peso_generico` é mais um conceito para quem edita `areas.yml` entender;
  - **nada disso foi medido contra um conjunto rotulado.** A taxonomia é mais
    específica; se ela *acerta mais* continua sem resposta. É exatamente a
    [issue #15](https://github.com/EmidioLP/vagas-tech-junior/issues/15).

## O que mudaria a decisão

- O conjunto rotulado da issue #15 mostrando que alguma área nova erra mais do que
  o balde-resto errava. Aí ela volta a ser fundida.
- `Engenharia de Software` crescer a ponto de virar o novo `Outros` — sinal de que
  precisa de sub-áreas ou de descrição enriquecida (o tech-skills-br busca a
  descrição completa numa segunda passada; nós classificamos o que a listagem dá, e
  56% do antigo `Outros` não tinha texto nenhum).
- Um portal novo com vocabulário próprio que o `areas.yml` não cubra.
