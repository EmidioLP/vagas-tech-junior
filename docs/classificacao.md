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

Cada área tem keywords em três faixas de peso (`peso_alto` = 4.0,
`peso_medio` = 1.0, `peso_generico` = 1.0). Keyword encontrada no **título** vale
3× o que vale na descrição (`title_boost`), porque o título é muito mais
confiável.

Duas regras evitam classificação por evidência frágil:

- **Título dominante** — se alguma área foi sinalizada pelo título, só essas
  áreas disputam. Sem isso, uma descrição longa da Gupy que cita "dados" de
  passagem ("proteção de dados", "dados cadastrais") transformava uma vaga de
  *Governança de TI* em vaga de *Data*.
- **`peso_generico` não sinaliza o título** — é a saída para termos amplos demais
  para definir a área sozinhos ("desenvolvedor junior", "programador"). Eles
  pontuam como `peso_medio`, dando a área de último recurso, mas **não** acionam o
  título dominante. Sem essa faixa, pôr "desenvolvedor junior" em *Engenharia de
  Software* faria todo título genérico de dev calar a descrição: "Desenvolvedor
  Júnior" com descrição de ETL e Airflow deixaria de ser *Data*
  ([ADR 0008](decisoes/0008-taxonomia-de-areas-expandida.md)).
- **`min_score` = 3.0** (o valor de uma keyword `peso_medio` no título) — abaixo
  disso a vaga cai em "Outros/TI Geral". Um único "dados" solto numa descrição
  não basta para definir a área.

O efeito é que "Outros/TI Geral" concentra títulos dos quais realmente **não dá**
para inferir a área — "Estágio em TI", "Jovem Aprendiz - Tecnologia". Preferi
deixá-los explícitos a distribuí-los por chute.

Até 21/09/2026 essa fatia era um terço da coleta, e boa parte dela era
classificável: "Desenvolvedor Júnior" e "Analista de Sistemas Jr" não são vagas
sem área, são vagas de desenvolvimento sem stack declarada. A taxonomia expandida
do [ADR 0008](decisoes/0008-taxonomia-de-areas-expandida.md) deu nome a elas
(*Engenharia de Software*) e derrubou o resto de 267 para 91 vagas na coleta de
15/09. O que sobra depende muito da fonte: um terço sem descrição nenhuma, puxado
pelo LinkedIn, cujo card não traz texto.

As keywords são casadas como palavra/frase inteira sobre o texto normalizado
(minúsculas, sem acento, pontuação virando espaço). Isso evita que "go" case
dentro de "Goiânia" ou "java" dentro de "javascript".

## Modalidade de trabalho

As vagas são classificadas em **Remoto**, **Híbrido**, **Presencial** e
**Não informado**, com origens diferentes por portal:

- **Gupy** expõe a modalidade explicitamente no campo `workplaceType`
  (`remote` / `hybrid` / `on-site`) — é dado afirmado pelo portal.
- **Solides** também afirma as três em `jobType`
  (`presencial` / `hibrido` / `remoto`), preenchido em todas as vagas medidas.
  O campo `showModality`, que o portal usa para esconder a modalidade na tela,
  é ignorado: ele controla a exibição, não a validade do dado
  ([detalhe](fontes.md#sobre-o-solides)).
- As demais fontes leem a modalidade de flags nativas ou do local do card, cada
  uma no seu arquivo em `scraper/sources/`; os casos que mudam a leitura estão em
  [`fontes.md`](fontes.md).
- **Vagas.com** classifica as vagas em três modalidades ("Na empresa",
  "Na empresa e Home Office", "100% Home Office"), mas **o card da listagem só
  mostra "100% Home Office" ou o nome da cidade** — um card híbrido e um
  presencial são indistinguíveis ali. Por isso o card só afirma o remoto; o resto
  passa pela inferência abaixo, em vez de ser adivinhado como presencial.
- **LinkedIn** também só afirma o remoto pelo card, quando o local diz isso. A
  descrição vem da página de detalhe de cada vaga de entrada
  ([detalhe](fontes.md#sobre-o-linkedin-jobs)) e passa pela inferência.

As três modalidades existem como filtro de busca no Vagas.com, mas os resultados
filtrados não reconciliam com a paginação da busca normal (para alguns termos o
filtro "Na empresa" sozinho já devolve a página inteira), então esse caminho foi
descartado.

### Modalidade inferida do texto

Quando a fonte não informa a modalidade, `scraper/modalidade.py` tenta lê-la no
texto, com as regras de `scraper/rules/modalidade.yml`
([ADR 0010](decisoes/0010-detalhe-do-linkedin-e-modalidade-inferida.md)). Roda no
pipeline junto da extração de tecnologias, antes de a exportação truncar a
descrição, e **nunca sobrescreve** a modalidade do portal.

- **Título e local decidem primeiro.** Neles, palavra solta vale ("Estágio em TI
  (Presencial)", "São Paulo, SP (Híbrido)"). A descrição só entra se eles não
  citam nada.
- **Na descrição, só frases de modalidade** ("modelo híbrido", "100% remoto",
  "regime presencial", "contrato efetivo presencial"; "dias presenciais" conta
  como híbrido, porque há dias que não são). Palavra solta ali cai em armadilhas: "suporte **remoto**" e
  "atendimento **presencial**" são atividades, "auxílio **home office**" é
  benefício de vaga híbrida, e "cloud, on premises e **híbrido**" é
  infraestrutura. As armadilhas conhecidas ficam em `excecoes` e são apagadas do
  texto antes da busca.
- **Duas modalidades citadas não viram chute.** Híbrido com presencial é híbrido
  ("1 dia por semana presencial"). Híbrido com remoto, ou remoto com presencial, é
  ambíguo ("tecnologia 100% remoto, demais times híbrido") e fica "Não informado".
- **Cidade não é modalidade.** Nas fontes que informam a modalidade, das 168 vagas
  com cidade cujo texto não diz o regime, 75% eram presenciais, 21% híbridas e 4%
  remotas (22/09/2026). Assumir Presencial pela cidade erraria 1 em 4, quase sempre
  em vaga híbrida. Como os cards do LinkedIn e do Vagas.com quase sempre trazem
  cidade, essa regra transformaria todo "Não informado" em Presencial. Por isso
  ela não existe.

Medido em 22/09/2026 contra as vagas cuja modalidade o portal informa: **85
acertos em 97 palpites**. Dos 12 erros, 8 são rótulos do Quero Vagas Tech
contraditos pelo próprio título ("Estágio (Presencial)" marcado como remoto). Os
outros vêm de descrições que falam da modalidade da empresa ou do processo
seletivo, não da vaga.

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

Cada gráfico tem a forma da pergunta que responde; o método, a bibliografia e a
decisão de cada gráfico do dashboard e dos PNGs estão em [`graficos.md`](graficos.md).
Três decisões visíveis em `scraper/charts.py`:

- **Uma cor só, não um degradê por valor.** Áreas de tecnologia são categorias
  *nominais* (não têm ordem natural). Pintar a barra maior mais escura gastaria
  o canal de cor repetindo o que o comprimento da barra já diz.
- **Small multiples para as tecnologias** — um painel por área, em vez de 8 cores
  disputando a mesma figura. A pergunta é "quais techs nesta área?", e cada
  painel responde isso sozinho.
- **Modalidade em barra 100% empilhada**, não em ranking: é parte-todo com
  poucas partes. "Não informado" fica em cinza, por último, porque é falta do dado.

O raio do canto arredondado é calculado em **pixels** e convertido para unidades
de dado de cada painel. O caminho óbvio no matplotlib (raio fixo em unidades de
dado) deforma o canto quando os eixos têm escalas diferentes: num painel cujo
eixo x vai só até 3, o raio vira uma "pílula" horizontal.

## Editando as regras

Toda a lógica de negócio está em quatro YAMLs comentados — **você não precisa
mexer em Python para ajustar**:

- **`scraper/rules/areas.yml`** — áreas, keywords, pesos e o portão de relevância.
- **`scraper/rules/seniority.yml`** — o que conta como nível de entrada e o que
  é nível acima.
- **`scraper/rules/skills.yml`** — tecnologias procuradas e seus apelidos.
- **`scraper/rules/modalidade.yml`** — frases de modalidade e armadilhas, usadas
  só quando o portal não informa.

Duas armadilhas já documentadas lá dentro, aprendidas rodando com dados reais:

- não coloque `data` como keyword de Data: em português casa com "**data** de
  admissão";
- não coloque `seguranca` sozinho na área Segurança: casa com "normas de
  **segurança**" no boilerplate de qualquer vaga de suporte, e com "**Segurança**
  do Trabalho". Isso inflou a área de 4 para 45 vagas na primeira execução.
