# Fontes de dados

Como cada portal é acessado e o que foi descoberto testando cada um ao vivo. A
coleta padrão usa sete portais (`DEFAULT_SOURCES` em `scraper/sources/__init__.py`);
a ProgramaThor continua registrada, mas fica fora dela. Visão geral do fluxo em
[`architecture.md`](architecture.md); limites da coleta em
[`limitacoes.md`](limitacoes.md).

| Portal | Como é acessado | Status |
|--------|-----------------|--------|
| **Gupy** (`portal.gupy.io`) | Endpoint JSON público que o front do portal usa: `GET https://employability-portal.gupy.io/api/v1/jobs?jobName=<termo>&limit=<n>&offset=<n>` | Funcionando, sem autenticação |
| **Vagas.com.br** | HTML da busca (`/vagas-de-<termo>?pagina=<n>`), renderizado no servidor | Funcionando, sem Selenium |
| **ProgramaThor** | HTML da listagem (`/jobs?expertise=<nível>&page=<n>`), renderizado no servidor | **Fora da coleta automática** (HTTP 403 para IPs de nuvem); funciona localmente com `--sources programathor` |
| **Trampos.co** | API JSON pública que a SPA consome: `GET https://trampos.co/api/v2/opportunities?tr=<termo>&page=<n>` | Funcionando, volume pequeno |
| **LinkedIn Jobs** | API de convidado, sem login: `GET .../jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=<termo>&geoId=106057199` | Funcionando, maior volume |
| **Quero Vagas Tech** | API JSON pública que o front consome: `GET https://querovagastech.com.br/api/jobs?page=<n>&pageSize=100` | Funcionando, sem autenticação |
| **GeekHunter** | Sitemap + página HTML de cada vaga, com dados estruturados JobPosting | Funcionando, volume pequeno |
| **Solides** (`vagas.solides.com.br`) | API JSON pública que o front consome: `GET https://apigw.solides.com.br/jobs/v3/portal-vacancies?title=<termo>&page=<n>&take=<n>` | Funcionando, sem autenticação |
| **Catho** | — | **Bloqueado** (ver abaixo) |
| **Indeed BR** | — | **Bloqueado** (ver abaixo) |

## Sobre a Gupy

O endpoint acima **não** é a API oficial `api.gupy.io` (essa exige token de
empresa). É o mesmo JSON que o navegador chama ao usar a busca do portal,
descoberto inspecionando a aba Network em `portal.gupy.io/job-search/term=...`.
É público e não pede login.

Dois detalhes descobertos testando o endpoint ao vivo, e que o código trata:

- `limit` máximo é **100** — acima disso a API responde `HTTP 400`.
- `pagination.total` **não é confiável**: vem limitado ao tamanho da página
  (com `limit=100` ele responde `total=100` mesmo havendo centenas de vagas).
  Por isso a paginação vai até receber uma página vazia, e não até bater o `total`.

## Sobre o Vagas.com.br

Ao contrário do que se costuma supor, a listagem de busca do Vagas.com é
renderizada no servidor — os cards já vêm no HTML. **Não é preciso
Selenium/Playwright**; `requests` + BeautifulSoup bastam. Isso foi verificado
ao vivo antes de escrever o parser.

Ponto de atenção: o Vagas.com devolve apenas um *trecho* da descrição (texto de
marketing), enquanto a Gupy devolve a descrição completa. O classificador leva
isso em conta (veja [Portão de relevância](classificacao.md#portão-de-relevância-é-vaga-de-tech)).

## Sobre a ProgramaThor

> **Fora da coleta padrão desde 15/09/2026.** A primeira coleta pelo GitHub
> Actions recebeu `HTTP 403` nas duas consultas: o portal bloqueia IPs de nuvem.
> Da máquina local continua funcionando. A fonte segue no código e nos testes, e
> as vagas antigas dela continuam na API; para coletar, rode
> `python main.py --sources programathor`.

Portal 100% de tecnologia, com listagem renderizada no servidor. Duas
particularidades mudam a forma de integrar:

- **O parâmetro `?search=` é ignorado.** Buscar `?search=python` devolve
  exatamente o mesmo conjunto de vagas que a listagem sem filtro — conferido
  comparando os ids retornados. Já `?expertise=` e `?page=` funcionam. Por isso
  esta fonte não percorre os 13 termos de busca do projeto: usa os filtros
  nativos de nível de entrada (`expertise=Júnior`, `contract_type=Estágio`) e
  faz duas consultas em vez de treze inúteis.
- **Vagas expiradas continuam na listagem**, marcadas com um selo "Vencida". São
  descartadas, e são a maioria: das 75 vagas "Júnior" nas 5 primeiras páginas,
  **68 estavam vencidas (91%)**, e as de estágio estavam 100% expiradas. As
  ativas ficam nas primeiras páginas — da página 6 em diante não há nenhuma.

O volume real é pequeno (**6 vagas júnior abertas** na coleta de 15/09/2026),
mas o card traz **senioridade e tecnologias declaradas pelo próprio portal**, o
que serve para conferir a classificação por keywords do projeto contra uma
categorização nativa. A senioridade declarada é respeitada em vez do regex de
título: "Programador(a) PHP" não tem marca de nível nenhuma, mas o portal a
classifica como Júnior.

## Sobre o Trampos.co

O site é uma SPA em Ember: o HTML entregue traz só um `<noscript>` de fallback,
sem link nem id por vaga. O que serve é a API JSON que o app consome, pública e
sem autenticação, descoberta na aba Network.

Os nomes dos parâmetros não são óbvios e foram mapeados por tentativa contra a
API: **`tr` é a busca textual** (cobre título e descrição) e `lc` é localização.
`q`, `s`, `category` e afins são silenciosamente ignorados.

Dois pontos que o código trata:

- O portal é **misto** — publica vagas de Comunicação e de TI no mesmo lugar. A
  categoria nativa entra na descrição para o portão de relevância decidir. Numa
  coleta real, das 12 vagas de nível de entrada encontradas, **11 eram de
  Administrativo, Comercial, Mídia e Publicidade** e só 1 era de tecnologia.
- A listagem **não traz a descrição da vaga**. Existe uma `company.description`,
  mas ela descreve a *empresa* — usá-la para classificar faria qualquer vaga de
  uma empresa de tecnologia parecer vaga de tecnologia. Só entram fatos da
  própria vaga.

A modalidade vem de flags nativas (`home_office`, `hybrid`). Vale registrar que
a fama de portal remoto **não se confirmou no recorte júnior**: das 12 vagas de
entrada, 3 remotas, 3 híbridas e 6 presenciais.

## Sobre o LinkedIn Jobs

É o endpoint que o próprio site chama para carregar mais resultados na busca
pública. Devolve um fragmento HTML com 10 cards por chamada e responde `200` até
com o User-Agent do projeto — não exige navegador nem sessão. É a fonte de maior
volume: **647 vagas brutas** na coleta de 15/09/2026, 244 no resultado final.

**A localização precisa ser o `geoId`.** Passar `location=Brasil` em português
falha em silêncio: a API responde `200` e devolve vagas dos Estados Unidos
("Brooklyn, NY", "San Francisco Bay Area"). `location=Brazil` em inglês filtra
quase tudo; `geoId=106057199` acertou 10 de 10 nos testes, e é o que o código
usa. Das 244 vagas da coleta de 15/09/2026, nenhuma veio de fora do Brasil.

O card da busca **não traz a descrição da vaga**. Até 21/09/2026 a classificação
desta fonte se apoiava só no título, e o efeito era visível: **45% das vagas do
LinkedIn caíam em "Outros/TI Geral"**, contra 25% nas demais fontes, porque
títulos como "ANALISTA DE SISTEMAS JR" ou "Analista de Desenvolvimento Júnior"
realmente não dizem a área. A modalidade também só aparece na descrição: 92% das
vagas ficavam "Não informado".

Desde 22/09/2026, depois da busca o coletor pede a página de detalhe de cada vaga
([ADR 0010](decisoes/0010-detalhe-do-linkedin-e-modalidade-inferida.md)):

    GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<id>

A descrição está em `div.show-more-less-html__markup`. Os limites do detalhe:

- **Só vagas de entrada.** O título precisa passar no filtro de senioridade; as
  outras o pipeline descartaria de qualquer jeito.
- **Um detalhe por id.** A mesma vaga volta em vários termos.
- **Teto por coleta:** `Settings.linkedin_max_detalhes` (300); `0` desliga.
- **Disjuntor:** para depois de 3 falhas seguidas, sinal de bloqueio.
- **A falha no detalhe não conta como falha da fonte**
  (`PoliteSession.get(..., conta_falha=False)`). A vaga já foi listada e segue sem
  descrição; se contasse, o LinkedIn viraria `partial` e deixaria de encerrar
  vagas ausentes.

São cerca de 250 requisições a mais por coleta (uns 6 minutos).

**O `robots.txt` do LinkedIn proíbe `/jobs-guest/`**: tem `Disallow: /` para
qualquer robô e o caminho explícito para cada robô nomeado. Vale para a busca e
para o detalhe ([`limitacoes.md`](limitacoes.md#éticas-e-de-uso-dos-dados)).

É também a fonte com maior chance de passar a bloquear. Se isso acontecer, a
sessão devolve `None`, o coletor entrega o que tiver e as outras fontes seguem
normalmente.

## Sobre o Quero Vagas Tech

Agregador brasileiro de vagas tech. O `robots.txt` libera tudo (`Allow: /`, sem
uma linha de `Disallow`) e a API que o front consome é pública, então a coleta
é direta: listagem paginada e, para cada vaga, um endpoint com a descrição. A
API não tem busca textual, então esta fonte lista o acervo inteiro em vez de
percorrer os termos do projeto.

A listagem não traz descrição, e o portão de relevância e o extrator de
tecnologias dependem dela. Antes de buscar descrições há um pré-filtro de nível
de entrada que chama a **mesma** função do pipeline — é economia de requisição,
não regra própria. Medido em 15/09/2026: **686 vagas listadas, 192 com nível de
entrada no título** (192 buscas de descrição, uns 6 minutos), 170 de tecnologia
no fim.

**A senioridade que o portal declara não é aproveitada, e isso é deliberado.**
Numa medição de 741 vagas, 292 vinham marcadas como `Intern` — entre elas
"Gerente de Infraestrutura de TI - LATAM" e "Analista de Produtos de TI Pleno".
Na de 15/09, das 192 com nível de entrada no título, o portal chamava 4 de
`Lead` e 4 de `Mid`. O filtro de nível deste projeto **respeita** nível
declarado pela fonte e nem consulta o título, então aceitar esse campo faria
passar gerente e pleno. A fonte deixa o campo vazio e quem decide é o título.

Parte do acervo vem do mesmo portal da Gupy que este projeto já raspa direto
(65 das 192), e a deduplicação colapsa essas quando as duas fontes rodam juntas
— por título+empresa quando os dois portais escrevem igual, e pelo id do link
da Gupy quando não escrevem (o agregador reescreve título e nome da empresa). O ganho real é a curadoria manual do site, mais InfoJobs e
Solides.

Algumas vagas da curadoria manual não têm link navegável — vêm como
`manual://jobs/<id>` ou com um e-mail de candidatura. Para essas, o link passa a
ser a página da vaga no próprio portal, que existe para toda vaga e mostra como
se candidatar.

O envelope da listagem traz `isLimited` e `requiresAuthForMore`. Hoje os dois
vêm `false` para cliente anônimo, mas os campos existem: se um dia começarem a
morder, a coleta avisa em log em vez de silenciosamente trazer dez vagas.

## Sobre a GeekHunter

Coletada de um jeito diferente das outras, e a diferença vem do `robots.txt`:

```
Disallow: /api/
Disallow: /feeds/
```

As superfícies de máquina são proibidas em texto explícito — a técnica usada na
Gupy e no Quero Vagas Tech, de consumir a API que o front chama, está fora de
questão aqui. O mesmo arquivo aponta o sitemap, que lista a página HTML de cada
vaga com dados estruturados `JobPosting`. Então o caminho é sitemap → filtro
pelo slug → página da vaga.

O arquivo também tem `Disallow: /jobs`, e vale ser preciso: regra de
`robots.txt` casa prefixo a partir da raiz, então cobre `/jobs...` e não
`/pt/<empresa>/jobs/<vaga>`, que é exatamente o formato que o sitemap lista. Há
ainda um bloco que proíbe tudo para crawlers de treinamento de IA (GPTBot,
ClaudeBot e afins); este scraper se identifica com User-Agent próprio e segue
as regras gerais.

O pré-filtro pelo slug usa o **mesmo** `seniority.yml` que filtra títulos mais
adiante — o slug é o título com hífens. Medido em 15/09/2026: 773 vagas em
`/pt/`, 44 com nível de entrada no slug, **35 de tecnologia** depois do portão
de relevância. A página traz um campo `skills` com as tecnologias declaradas,
que entra na descrição como as tags da ProgramaThor: 34 das 35 vagas saíram com
tecnologia extraída, e todas vieram com modalidade informada.

As 9 descartadas pelo portão: 4 claramente fora de tecnologia (estágio em
Pedagogia, administrativo, designer) e 5 de telecom, UX e operação de
plataforma — áreas que as 10 categorias do projeto não cobrem.

A limitação é conhecida: o slug só mostra o título. Vaga júnior anunciada como
"Desenvolvedor Front-end", sem marca de nível no título, passa batido. Buscar as
773 páginas resolveria e custaria uns 20 minutos de requisição.

## Sobre o Solides

O Solides é um SaaS de RH; o portal público dele agrega as vagas de todas as
empresas clientes. O endpoint acima é o mesmo JSON que o navegador chama ao usar
a busca, descoberto inspecionando a aba Network. É público, não pede login, e o
User-Agent identificável do projeto é aceito — não é preciso fingir navegador. O
`robots.txt` de `vagas.solides.com.br` e de `solides.jobs` libera tudo
(`User-agent: * / Allow: /`); o `apigw` não serve `robots.txt`.

Detalhes descobertos testando o endpoint ao vivo, e que o código trata:

- **`title` é o único filtro de texto que funciona.** `search`, `q`, `keyword`,
  `term` e `name` são aceitos e silenciosamente ignorados — devolvem o acervo
  inteiro (~73 mil vagas de todas as áreas). O `title` casa por palavra, sem
  acento e com abreviação (`title=devops junior` traz "Analista DevOps Jr"), mas
  olha **só o título**: a descrição não entra na busca. Vaga júnior de tecnologia
  cujo título não repita nenhum dos 13 termos do projeto passa batido.
- **`take` é no máximo 25** — acima disso a API responde `HTTP 400`
  (`"take deve ser menos ou igual a 25"`). Sem `take`, o default é 10.
  `limit`, `perPage` e `pageSize` são ignorados.
- **O `id` vem inteiro ou alfanumérico curto** (`"vgV6ou5UrL"`): 5 de 40 medidas
  não eram numéricas. Por isso vira texto antes de virar `external_id`. Na
  deduplicação, o link com id numérico rende a chave `solides.jobs:<id>`; o
  alfanumérico não casa nenhuma regra e a vaga cai no critério título+empresa.
- **`showModality` é ignorado de propósito.** Veio `false` em 7 de 40 vagas,
  sempre com `jobType` preenchido: o campo controla a exibição no portal, não a
  validade do dado. A modalidade é gravada nas duas situações — o Solides afirma
  `presencial`/`hibrido`/`remoto` explicitamente, como a Gupy. `homeOffice` é uma
  flag separada e legada (veio `true` em 2 de 200, enquanto 18 tinham
  `jobType=remoto`) e só serve de reserva.
- **A senioridade declarada pelo portal é ignorada**, pela mesma razão do Quero
  Vagas Tech: numa medição de 6 vagas de "desenvolvedor junior", 3 vinham com
  `seniority` vazio, uma chamada "vaga testre" vinha como `Junior` e outra,
  "Analista Full Stack Júnior / Pleno", como `['Pleno', 'Junior']`. Quem decide
  o nível aqui é o regex sobre o título.
- **Muita vaga antiga continua listada como aberta.** `currentState` veio
  `em_andamento` em 200 de 200, mas nas 39 vagas finais de 22/09/2026 a idade
  mediana era de **235 dias** e 14 passavam de um ano (a mais velha, de
  16/05/2019); 4 traziam "Banco de Talentos" no título. A coleta não filtra por
  idade — grava a `createdAt` que o portal publica e o viés fica registrado em
  [`limitacoes.md`](limitacoes.md).

Medido em 22/09/2026 com os 13 termos do projeto: **13 requisições, 41 vagas
brutas, 39 finais** depois de dedupe e portão de relevância — todo termo coube em
uma página de 25. Todas vieram com descrição, empresa, link e data; a modalidade
saiu 24 presencial, 10 híbrido e 5 remoto.

Parte deste acervo já chegava ao projeto de forma indireta, pela curadoria do
Quero Vagas Tech; a deduplicação por título+empresa colapsa a sobreposição.

## Sobre a Catho — bloqueada

A Catho não é acessível por cliente HTTP simples: qualquer requisição sem
navegador real recebe `HTTP 404` com a página "Operação Inválida!" — inclusive
a home do site, não só a busca. Não é uma questão de renderização de JavaScript
que Selenium resolveria sozinho.

**Nenhum dado da Catho é simulado neste projeto.** Por isso a fonte ficou de
fora. A estrutura de `scraper/sources/` foi feita para receber uma fonte nova
em um arquivo só — **Remotar** e **Gupy Vagas** são candidatos ainda não
avaliados.

## Sobre o Indeed BR — bloqueado

O Indeed responde **HTTP 403 do Cloudflare** com o cabeçalho
`Cf-Mitigated: challenge`, tanto com o User-Agent do projeto quanto com um de
navegador. É um desafio de bot no edge, não uma questão de renderização.

Assim como na Catho, **nenhum dado do Indeed é simulado**: a fonte foi avaliada,
documentada e deixada de fora.

## Educação com o servidor

- User-Agent identificável (não finge ser navegador).
- Delay de 1.5 s entre requests, com jitter, configurável via `--delay`.
- Retry com backoff exponencial em 429/5xx e erros de conexão, respeitando
  `Retry-After`.
- Falha em um termo ou portal não derruba a coleta inteira — o erro é registrado
  e reportado no fim.
- Paginação para assim que uma página vem vazia ou repetida.

## Adicionando um portal novo

1. Crie `scraper/sources/meu_portal.py` com uma classe que herda de `JobSource`
   e implementa `fetch_term(term) -> list[Job]`.
2. Registre em `scraper/sources/__init__.py`, no `SOURCE_REGISTRY`.

Pronto — ele passa a aceitar `--sources meu_portal` e reaproveita filtro,
classificação, dedupe, gravação no banco e exportação. Para entrar na coleta
agendada, ele também precisa estar em `DEFAULT_SOURCES` (fica fora se for listado em
`FORA_DA_COLETA_PADRAO`), e as checagens de qualidade podem precisar de isenções
por fonte ([`data-quality.md`](data-quality.md#vazios-esperados-por-fonte)).
