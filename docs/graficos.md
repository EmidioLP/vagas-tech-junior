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
   catálogo aparece no *Visual Vocabulary* do Financial Times (2016) e, como
   ação e alvo, em Munzner (2014).
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
| Overview · por modalidade | 3 ordinais + ausência; **parte-todo** | barra horizontal (ranking) | **uma barra 100% empilhada**: Remoto, Híbrido, Presencial em três tons de um azul; "Não informado" em cinza, no fim; % dentro do segmento | a pergunta é "que parte do todo", não "qual é maior"; a ordem da modalidade vira ordem de claridade (Bertin); a ausência não compete com as modalidades |
| Overview · por fonte | 9 nominais; ranking | barra horizontal | igual, com "N (P%)" na ponta | já era a forma certa |
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

## Cor

- **Série única:** `#2a78d6`, o mesmo azul nos PNGs e no dashboard.
- **Modalidade:** rampa ordinal de um azul, `#184f95` (Remoto), `#3987e5`
  (Híbrido), `#86b6ef` (Presencial). Validada com um verificador de paleta
  (monotonia de claridade, passo visível entre vizinhos, contraste mínimo de 2:1
  do tom mais claro com o fundo) contra o fundo claro (`#fcfcfb`) e o escuro do
  Streamlit (`#0e1117`). O tom de 650 falhava no escuro e foi trocado por `#184f95`.
- **"Não informado":** cinza `#898781`, fora da rampa. Na coleta de 15/09/2026
  era 44% das vagas (264 de 597), 244 delas do LinkedIn, que não informa
  modalidade na listagem. Pintá-lo de azul o faria parecer uma quarta modalidade.
- **Modalidade fora do domínio** (a checagem de qualidade já alerta): cinza
  escuro `#52514e`, para não se confundir com "Não informado".
- **Rótulos de valor:** cinza médio `#898781`, legível nos dois temas.
- **Vão entre segmentos:** no dashboard é um espaço de verdade (cada segmento é
  encurtado), não um contorno branco, que viraria uma linha branca no tema escuro.

## Detalhes de eixo

- Eixo de tempo com marca só em dias inteiros e rótulo omitido quando não cabe;
  sem grade vertical.
- Contagens sem rótulo fracionário: nos painéis de 1 ou 2 vagas o Vega-Lite
  punha marcas em 0,5. `tickMinStep` não vale nos small multiples com escala
  independente, então um `labelExpr` apaga o rótulo das marcas não inteiras.
- Vagas novas: no primeiro dia do histórico todas as vagas são novas, e essa
  coluna encolhe as demais. A legenda sugere ajustar o período.

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
- Munzner, T. *Visualization Analysis and Design*. Boca Raton: CRC Press, 2014.
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
3. Cor nova de categoria: valide nos dois temas antes de fixar.
4. Renderize e olhe: sobreposição de rótulos e eixos não aparecem nos testes.
