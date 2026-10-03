# Que gráfico para cada pergunta

Até 26/09/2026 todo gráfico do projeto era uma barra horizontal azul ou a linha
padrão do Streamlit, qualquer que fosse a pergunta. Este estudo define, gráfico a
gráfico, a forma que serve à pergunta, com um método explícito e a bibliografia
que o sustenta. O código segue o resultado: `dashboard/graficos.py` (dashboard) e
`scraper/charts.py` (PNGs do `--csv`).

## Método

Para cada gráfico, quatro perguntas, nesta ordem. A cor vem por último.

1. **Que tipo de dado é cada variável?** Nominal (área, fonte), ordinal
   (Remoto → Híbrido → Presencial, do menos ao mais presencial), quantitativa
   (vagas, %) ou temporal (dia de coleta). O tipo limita os canais que o
   representam sem mentir: a *expressividade* de Mackinlay (1986) e a semiologia
   de Bertin (1967). Cor com degradê numa variável nominal, por exemplo, sugere
   uma ordem que não existe.
2. **Que tarefa o leitor faz?** As relações de Few (2012): ranking, parte-todo,
   série temporal, comparação nominal, distribuição, desvio, correlação. O mesmo
   catálogo aparece no *Visual Vocabulary* do Financial Times (2016), como
   ação e alvo em Munzner (2014) e, como busca por função, no *Data Visualisation
   Catalogue* (Ribecca), conferido gráfico a gráfico mais abaixo.
3. **Qual o canal mais preciso para a variável principal?** A hierarquia de
   Cleveland & McGill (1984), replicada por Heer & Bostock (2010): posição numa
   escala comum > comprimento > ângulo e área > cor. É a *efetividade* de
   Mackinlay: a variável que importa mais recebe o canal mais preciso.
4. **O dado real cabe na forma escolhida?** Quantas categorias, que tamanho de
   rótulo, que base. Categorias distinguíveis só pela cor não passam de 6 a 8
   (Ware, 2012; Harrower & Brewer, 2003); acima disso, *small multiples*
   (Tufte, 2001). Rótulos longos pedem barra horizontal. Ausência de dado não é
   categoria: fica em cinza, fora da escala de cores (Wilke, 2019; ênfase por
   cinza em Knaflic, 2015).

Duas regras transversais, das mesmas fontes:

- **Barra para valor discreto, linha para tendência.** Zacks & Tversky (1999)
  mostraram que leitores descrevem barras como comparações entre itens e linhas
  como mudança contínua. Contagem de eventos num dia é discreta; estoque de vagas
  abertas é contínuo.
- **Rótulo direto antes de grade** (Tufte, razão dado-tinta): o valor escrito na
  ponta da barra dispensa o eixo.

## Decisão por gráfico

| Gráfico | Dado e tarefa | Antes | Agora | Por quê |
|---|---|---|---|---|
| Overview · por área | 17 nominais; ranking | barra horizontal numa coluna de 1/3 | barra horizontal ordenada, largura total, "N (P%)" na ponta | comprimento é o canal mais preciso; 17 nomes longos espremiam as barras |
| Overview · por modalidade | 3 ordinais + ausência; **parte-todo** | barra horizontal (ranking) | **uma barra 100% empilhada**: Remoto, Híbrido, Presencial em três tons de um azul; "Não informado" em cinza, no fim; % dentro do segmento quando cabe | a pergunta é "que parte do todo", não "qual é maior"; a ordem da modalidade vira ordem de claridade (Bertin); a ausência não compete com as modalidades |
| Overview · por fonte | 9 nominais; ranking | barra horizontal | igual, com "N (P%)" na ponta | já era a forma certa |
| Overview · modalidade por fonte | fonte × modalidade; **parte-todo por grupo** ("de onde vem o Não informado") | frase abaixo dos KPIs ("90 de linkedin, 10 de vagas") | **split bars**: um painel por modalidade em grade 2×2, com "Não informado" no primeiro, colado aos nomes; uma barra por fonte com o % escrito depois da ponta; escala comum de 0 a 100%; fontes ordenadas pela fração de "Não informado"; total no rótulo (`n=`) | a frase dava contagens soltas, sem a proporção de cada fonte. A primeira versão (barra 100% empilhada por fonte) foi trocada em 02/10/2026, porque um "Não informado" de 1% tinha 3–5 px e nenhum número cabia (captura do usuário), e o Datawrapper indica split bars para comparar várias partes entre grupos. Só aparece com 2+ fontes |
| Histórico · vagas abertas | temporal × estoque; tendência | linha | linha **com um ponto por dia de coleta** | é estoque, contínuo; o ponto mostra onde há medida, já que dias sem coleta não aparecem e a linha os atravessa |
| Histórico · abertas por área | 17 séries temporais | 17 linhas coloridas no mesmo eixo | **small multiples**: um painel por área, da maior para a menor no último dia, escala vertical própria | 17 cores passam do limite distinguível; com escala comum, as áreas pequenas viram uma reta no chão; o tamanho de cada área já está na Overview, aqui a tarefa é a forma da tendência (a legenda avisa) |
| Histórico · vagas novas | contagem por dia | linha | **colunas** | evento discreto por dia (Zacks & Tversky); a linha sugeria continuidade entre dias |
| Histórico · snapshots | contagem por dia | linha | **colunas** | idem |
| Tecnologias · todas as áreas | % sobre a base; ranking | barra 0–100% | igual, com "P% (n)" na ponta | barra com base zero e eixo fixo já é a forma certa |
| Tecnologias · por área | ranking por grupo | small multiples 0–100% | igual | já seguia Tufte; o eixo fixo permite comparar painéis |
| PNG · áreas | ranking | barra horizontal | igual | — |
| PNG · tecnologias por área | ranking por grupo | small multiples | igual | — |
| PNG · modalidade | parte-todo | barra horizontal | barra 100% empilhada, como no dashboard | coerência entre os dois meios |

## Alternativas descartadas

- **Pizza ou rosca para modalidade.** Ângulo e área ficam abaixo do comprimento
  na hierarquia de Cleveland & McGill; com quatro partes, duas delas perto de
  10–15%, a comparação fica imprecisa. A barra empilhada responde à mesma
  pergunta parte-todo com posição e comprimento.
- **Área empilhada para as áreas no tempo.** Só a camada de baixo tem base comum;
  as outras 16 seriam lidas por diferença de alturas, a leitura menos precisa.
- **Destacar uma área e acinzentar as outras.** Boa forma quando há uma área de
  interesse; aqui não há, e o filtro de área da barra lateral já faz esse papel.
- **Dot plot (Cleveland, 1985) para tecnologias.** Ganha quando a escala não
  começa em zero ou há várias séries por linha; com uma série em % e base zero,
  a barra diz o mesmo e é mais familiar.
- **Mapa de calor área × tecnologia.** Compacto, mas cor é o canal menos preciso
  e as áreas têm bases muito diferentes (algumas só indicativas).
- **Degradê por valor nas barras.** Repetiria na cor o que o comprimento já diz.
- **Marimekko para fonte × modalidade.** Largura = volume da fonte daria as duas
  coisas num gráfico, mas o próprio catálogo aponta que os segmentos não têm base
  comum, e as fontes pequenas virariam frestas ilegíveis. O volume já está no
  ranking "Por fonte"; aqui vai só no rótulo `n=`.
- **Barra 100% empilhada por fonte.** Foi a primeira forma da modalidade por
  fonte. O Datawrapper ("What to consider when creating stacked column charts")
  a recomenda para comparar o total e *uma* parte; para várias partes entre
  grupos, indica split bars ou small multiples, e avisa que rotular dentro da
  pilha piora quanto menores as partes. Foi o que aconteceu: o "Não informado"
  de 1% do querovagastech tinha 3–5 px e o número não cabia em largura nenhuma.
  Nas split bars, o % fica fora da barra e aparece sempre, inclusive 0%.
- **Split bars em linha (1×4).** Dá ~600 px, e o gráfico com facetas tem largura
  própria, não encolhe. A 400 px o Streamlit cortava os painéis da direita,
  justamente o "Não informado". A grade 2×2 dá ~340 px.
- **Parallel Sets (fonte → modalidade).** Mostra o mesmo cruzamento como fluxo,
  mas é pouco familiar e, segundo o catálogo, não dá valores precisos sem anotação.
- **Treemap e Sunburst.** Pedem hierarquia, e área, fonte e modalidade não formam uma.
- **Dot Matrix e Pictograma.** Contam unidades, com precisão menor que a barra.

## Conferência com o Data Viz Catalogue

Em 02/10/2026 cada gráfico foi conferido com o *Data Visualisation Catalogue*
(<https://datavizcatalogue.com/>), que organiza as formas pela função que cumprem.
Para cada um: a função do catálogo, o que a ficha da forma escolhida diz e o
veredito. As frases entre aspas são das fichas, traduzidas.

| Gráfico | Função no catálogo | O que a ficha diz | Veredito |
|---|---|---|---|
| Overview · por área | Comparisons | *Bar Chart*: barras horizontais "acomodam rótulos longos"; eixo começa no zero; muitas barras pedem espaço | mantém; a largura total dá o espaço que 17 nomes pedem |
| Overview · por fonte | Comparisons | *Bar Chart* | mantém |
| Overview · por modalidade | Part-to-a-whole, Proportions | *Stacked Bar Graph* 100%; a legibilidade cai "com muitos segmentos" e os segmentos "não ficam numa base comum" | mantém: são 4 segmentos, com o % escrito em cada um. *Pie* e *Donut* estão na mesma função, mas já foram descartados acima |
| Overview · modalidade por fonte | Part-to-a-whole, Comparisons | *Stacked Bar Graph*: mostra "como uma categoria maior se divide em subcategorias"; *Multi-set Bar Chart* para comparar várias séries por categoria | **novo** como barra empilhada; virou split bars (barras por série, em painéis) quando os segmentos de 1% ficaram sem número |
| Histórico · vagas abertas | Data over time | *Line Graph*: valores "num intervalo contínuo"; supõe intervalos regulares | mantém; o ponto em cada dia de coleta mostra onde há medida quando o intervalo não é regular |
| Histórico · abertas por área | Data over time | *Line Graph*: "evite mais de 3–4 linhas por gráfico"; com muitas séries, gráficos menores separados | mantém os small multiples, que são a recomendação da ficha |
| Histórico · novas e snapshots | Comparisons | *Bar Chart*: comparação discreta entre categorias (aqui, dias) | mantém as colunas |
| Tecnologias · todas e por área | Comparisons, Proportions | *Bar Chart*. O *Heatmap* aparece em Relationships, mas "é difícil distinguir tons e extrair valores" | mantém as barras de 0 a 100%; o mapa de calor segue descartado |

O catálogo não mudou nenhuma escolha anterior. Ele apontou uma pergunta que só
existia em texto, de que fonte vem o "Não informado", e ela virou o gráfico
*Modalidade por fonte*.

## Cor

Em 02/10/2026 as cores foram revistas pelo guia do Datawrapper sobre cores em
guias de estilo (Muth, 2022). O ponto central do guia é que **o fundo limita a
claridade que as cores podem ter**. O exemplo é o fundo rosa do Financial Times.
O dashboard não fixa tema, então cada leitor vê um de dois fundos: o claro do
Streamlit (`#ffffff`) ou o escuro (`#0e1117`). A paleta anterior tinha sido
validada contra `#fcfcfb`, o fundo dos PNGs, com mínimo de 2:1. Medida contra os
fundos reais, ela falhava:

| Cor anterior | Uso | vs claro | vs escuro | Problema |
|---|---|---|---|---|
| `#184f95` | Remoto | 8,1 | **2,3** | some no escuro |
| `#86b6ef` | Presencial | **2,1** | 9,0 | some no claro |
| `#3987e5` × `#898781` | Híbrido × Não informado | — | — | **mesma claridade** (L* 56): iguais em tons de cinza e para quem não distingue o matiz |
| `#898781` | rótulo de valor | **3,6** | 5,3 | texto abaixo de 4,5:1 no claro |
| `#52514e` | modalidade fora do domínio | 7,9 | **2,4** | some no escuro |

Para que uma paleta só servisse aos dois fundos, toda cor teria de ficar entre
L* 41 e 62. É estreito demais para três tons e um cinza. Por isso há **uma
paleta por tema** (`dashboard/graficos.py:PALETAS`).

### Quem troca a paleta é o navegador

A primeira versão (PR #31) escolhia a paleta em Python, lendo
`st.context.theme.type`, e **não funcionou**: ao trocar o tema no menu ⋮ →
Settings, o Streamlit não roda o script de novo, então o gráfico continuava com a
paleta antiga. Além disso, o próprio Streamlit avisa que o valor pode vir errado
na primeira execução da sessão (issue
[#11920](https://github.com/streamlit/streamlit/issues/11920), aberta).

Agora o gráfico não tem cor fixa. Cada marca codifica uma **chave**
(`CHAVES_DE_COR`: Remoto, Híbrido, Presencial, Não informado, Fora do domínio, o
texto dentro do segmento e o rótulo de valor) numa escala com `domain`, mas sem
`range`. O Streamlit preenche o range, no navegador, com a lista
`chartCategoricalColors` do tema em vigor, definida em `[theme.light]` e
`[theme.dark]` de `.streamlit/config.toml` (recurso do Streamlit 1.51, o mínimo
do projeto). A troca de tema redesenha o gráfico com a outra lista, sem rodar o
script. Isso foi conferido por captura de tela, trocando o tema com a página
aberta. Um teste exige que o `config.toml` tenha as cores de `PALETAS` na ordem
das chaves, e outro, que nenhum gráfico de categoria ou de texto use cor fixa.

O azul da série única é igual nos dois temas e continua fixo na marca.

O `config.toml` só é lido quando o app roda da raiz do repositório
(`streamlit run dashboard/app.py`), que é como o Community Cloud o executa.

Regras, todas travadas por `test_paleta_valida_no_fundo_do_tema`:

- **Marca com ≥ 3:1 contra o fundo**, como pede a WCAG 2.1 (1.4.11) e o guia
  recomenda. **Texto com ≥ 4,5:1** (WCAG 1.4.3).
- **A rampa de modalidade vai do maior para o menor contraste com o fundo**:
  Remoto > Híbrido > Presencial, com ao menos 10 L* entre vizinhos. A ordem da
  modalidade vira ordem de claridade (Bertin). No escuro a rampa **se inverte**:
  o Remoto continua o tom de maior contraste e passa a ser o mais claro.
- **"Não informado" é um cinza fora da rampa**, a ≥ 8 L* de cada tom. No gráfico
  por fonte ele pode encostar em qualquer modalidade, porque uma fonte sem
  Presencial põe o cinza ao lado do Híbrido. O guia pede variar a claridade, e
  não só o matiz, para que as cores sobrevivam aos tons de cinza e ao daltonismo.
  Na coleta de 15/09/2026 o "Não informado" era 44% das vagas (264 de 597), 244
  delas do LinkedIn, que não informa modalidade na listagem. Pintado de azul, ele
  pareceria uma quarta modalidade.
- **Modalidade fora do domínio** (a checagem de qualidade já alerta) é um
  segundo cinza, a ≥ 8 L* do primeiro.
- **O % dentro do segmento é escrito na cor do fundo** (branco no claro, `#0e1117`
  no escuro): é uma só cor por tema, e por isso cabe numa posição da lista. Em
  troca, **todo segmento precisa de ≥ 4,5:1 contra o fundo**, o que é mais
  exigente que os 3:1 de marca e escureceu o cinza do tema claro.
- **Vários cinzas para o que não é dado**, como o guia sugere. O rótulo de
  valor é um cinza próprio, mais forte que a grade, que o tema do Streamlit
  desenha.

| Uso | Claro (`#ffffff`) | L* | contraste | Escuro (`#0e1117`) | L* | contraste |
|---|---|---|---|---|---|---|
| Série única | `#2a78d6` | 50 | 4,4 | `#2a78d6` | 50 | 4,3 |
| Remoto | `#0f305a` | 20 | 13,2 | `#c8dcf4` | 87 | 13,5 |
| Híbrido | `#184985` | 31 | 9,0 | `#91b9ea` | 74 | 9,3 |
| Presencial | `#2161ae` | 41 | 6,1 | `#5d99e0` | 62 | 6,4 |
| Não informado | `#787671` | 50 | 4,5 | `#807e78` | 53 | 4,7 |
| Fora do domínio | `#4c4b47` | 32 | 8,7 | `#a7a6a0` | 68 | 7,7 |
| Rótulo de valor | `#605e5a` | 40 | 6,5 | `#a8a6a0` | 68 | 7,8 |

O azul da série única passa nos dois fundos e continua o mesmo nos PNGs. Os PNGs
(`scraper/charts.py`, fundo `#fcfcfb`) usam a paleta clara, copiada porque
`scraper` não importa `dashboard`. `test_pngs_usam_a_paleta_clara` confere a
cópia.

- **Vão entre segmentos:** no dashboard é um espaço de verdade (cada segmento é
  encurtado), não um contorno branco, que viraria uma linha branca no tema escuro.

Do guia, ficaram de fora:

- **Saturação diferente para área grande (barra) e marca pequena (linha).** O
  azul único já passa nos dois fundos. Duas versões de cada cor complicariam
  ferramenta e documentação, custo que o próprio guia aponta.
- **Cor de marca para destaque.** O projeto não tem marca, e a ênfase vem da
  ordem e do cinza.

## Detalhes de eixo

- Eixo de tempo com marca só em dias inteiros e rótulo omitido quando não cabe;
  sem grade vertical.
- **% no segmento só quando cabe, medido em pixels.** Até 02/10/2026 o segmento
  só ganhava rótulo com 6% ou mais da barra, e a regra errava nos dois
  sentidos:
  - numa barra de ~1800 px, "4%" tinha ~73 px e mesmo assim ficava sem número
    (captura do usuário na "Modalidade por fonte": vagas, linkedin e recrutei);
  - numa coluna estreita, um segmento de 7% com ~20 px deixava o texto
    transbordar.

  Agora todo segmento leva o %. A camada de texto fica visível só se
  `(fim - inicio) * width` (`width` é a largura real do gráfico, refeita a cada
  redimensionamento) for maior ou igual à largura estimada do texto
  (`largura_rotulo`: 7 px por caractere + 8 de folga). O texto que não cabe fica
  transparente, mas o tooltip continua mostrando o valor. Conferido por captura
  de tela em 1400 e 400 px, nos dois temas.

  Hoje isso vale só para a barra única da "Por modalidade". Na "Modalidade por
  fonte", mesmo medindo em pixels, o "Não informado" de 1% não cabia, e o gráfico
  virou split bars, com o % fora da barra.
- **Legenda da barra de modalidade:** em linha só, cortava o "Não informado"
  na coluna estreita. Abaixo de 400 px de largura ela quebra em duas colunas
  (`columns` por expressão sobre `width`).
- Contagens sem rótulo fracionário: nos painéis de 1 ou 2 vagas o Vega-Lite
  punha marcas em 0,5. `tickMinStep` não vale nos small multiples com escala
  independente, então um `labelExpr` apaga o rótulo das marcas não inteiras.
- Vagas novas: no primeiro dia do histórico todas as vagas são novas, e essa
  coluna encolhe as demais. A legenda sugere ajustar o período.
- **Altura por passo, nunca altura total.** Com `width="stretch"`, o Streamlit
  encaixa eixos e legenda *dentro* da altura declarada. A primeira versão da barra
  de modalidade tinha `height=48` e, no dashboard publicado, a área da barra ficou
  com ~0 px: só os rótulos de % apareciam, sem segmentos nem legenda, nos dois
  temas. Por isso as barras usam uma banda de `y` com `alt.Step(...)` (px por
  categoria), e um teste exige isso. O renderizador avulso (`vl-convert`) soma eixo
  e legenda por fora e não reproduz o problema.

## Bibliografia

- Bertin, J. *Sémiologie graphique*. Paris: Gauthier-Villars, 1967. Tradução
  inglesa: *Semiology of Graphics*. University of Wisconsin Press, 1983.
- Cleveland, W. S.; McGill, R. "Graphical Perception: Theory, Experimentation,
  and Application to the Development of Graphical Methods". *Journal of the
  American Statistical Association*, 79(387), p. 531–554, 1984.
- Cleveland, W. S. *The Elements of Graphing Data*. Monterey: Wadsworth, 1985.
- Few, S. *Show Me the Numbers: Designing Tables and Graphs to Enlighten*. 2. ed.
  Burlingame: Analytics Press, 2012.
- Financial Times. *Visual Vocabulary*. 2016. Disponível em
  <https://github.com/Financial-Times/chart-doctor/tree/main/visual-vocabulary>.
- Harrower, M.; Brewer, C. A. "ColorBrewer.org: An Online Tool for Selecting
  Colour Schemes for Maps". *The Cartographic Journal*, 40(1), p. 27–37, 2003.
- Heer, J.; Bostock, M. "Crowdsourcing Graphical Perception: Using Mechanical
  Turk to Assess Visualization Design". *Proceedings of CHI 2010*, p. 203–212.
- Knaflic, C. N. *Storytelling with Data*. Hoboken: Wiley, 2015.
- Mackinlay, J. "Automating the Design of Graphical Presentations of Relational
  Information". *ACM Transactions on Graphics*, 5(2), p. 110–141, 1986.
- Datawrapper. "How to create a split bar chart". *Datawrapper Academy*.
  Disponível em <https://www.datawrapper.de/academy/how-to-create-a-split-bar-chart>.
  Acesso em 02/10/2026.
- Datawrapper. "What to consider when creating stacked column charts".
  *Datawrapper Blog*. Disponível em
  <https://www.datawrapper.de/blog/stacked-column-charts>. Acesso em 02/10/2026.
- Muth, L. C. "A detailed guide to colors in data vis style guides". *Datawrapper
  Blog*, 30/03/2022. Disponível em
  <https://www.datawrapper.de/blog/colors-for-data-vis-style-guides>. Acesso em
  02/10/2026.
- Munzner, T. *Visualization Analysis and Design*. Boca Raton: CRC Press, 2014.
- Ribecca, S. *The Data Visualisation Catalogue*. Disponível em
  <https://datavizcatalogue.com/>. Acesso em 02/10/2026.
- Tufte, E. R. *The Visual Display of Quantitative Information*. 2. ed.
  Cheshire: Graphics Press, 2001.
- Ware, C. *Information Visualization: Perception for Design*. 3. ed. Waltham:
  Morgan Kaufmann, 2012.
- Wilke, C. O. *Fundamentals of Data Visualization*. Sebastopol: O'Reilly, 2019.
  Disponível em <https://clauswilke.com/dataviz/>.
- Zacks, J.; Tversky, B. "Bars and Lines: A Study of Graphic Communication".
  *Memory & Cognition*, 27(6), p. 1073–1079, 1999.

## Ao mudar ou criar um gráfico

1. Responda às quatro perguntas do método e registre a linha na tabela acima.
2. Construtor novo em `dashboard/graficos.py` (função pura que devolve o gráfico)
   e teste em `tests/dashboard/test_graficos.py`, que inspeciona `to_dict()`.
3. Cor nova: crie a chave em `CHAVES_DE_COR` (no fim, para não mudar a posição
   das outras), ponha a cor nas duas paletas de `PALETAS` e a mesma lista em
   `.streamlit/config.toml`. Os testes conferem contraste, claridade e a cópia.
   Nunca passe cor fixa para uma marca de categoria ou de texto: ela não troca
   com o tema.
4. Toda camada declara `tooltip`, só com campos legíveis. Camada sem tooltip (um
   rótulo de texto, por exemplo) ganha o padrão do Streamlit, que mostra todos os
   campos internos da marca; um teste cobre isso.
5. Renderize **no próprio Streamlit** e olhe, nos temas claro e escuro
   (`streamlit run ... --theme.base dark|light`): sobreposição de rótulos, eixos e o
   dimensionamento do Streamlit não aparecem nos testes nem num renderizador avulso.
