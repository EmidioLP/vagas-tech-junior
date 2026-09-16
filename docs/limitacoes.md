# Limitações

O que este projeto **não** mede bem, e por quê. Vale ler antes de citar um número
do dashboard, da API ou de um relatório datado. Fontes em [`fontes.md`](fontes.md);
classificação em [`classificacao.md`](classificacao.md).

## Éticas e de uso dos dados

- **Coleta de páginas e APIs públicas, sem login.** Os endpoints de Gupy, Trampos.co,
  LinkedIn e Quero Vagas Tech são os que o próprio front de cada site chama; não
  são APIs oficiais nem têm contrato de uso para terceiros.
- **`robots.txt` respeitado onde muda o caminho.** Na GeekHunter, `/api/` e
  `/feeds/` são proibidos, então a coleta vai pelo sitemap e pela página de cada
  vaga ([detalhe](fontes.md#sobre-a-geekhunter)).
- **Carga pequena de propósito.** User-Agent identificável, 1,5 s entre
  requisições com jitter, backoff em 429/5xx respeitando `Retry-After`, e nada de
  buscar uma página por vaga quando isso multiplicaria a carga (LinkedIn, e as
  773 páginas da GeekHunter) ([Educação com o servidor](fontes.md#educação-com-o-servidor)).
- **Termos de uso não são alterados pela licença.** A licença MIT cobre o código.
  As vagas pertencem aos portais e às empresas, e raspá-las continua sujeito aos
  termos de cada site. Nenhum dado raspado é versionado além de `seed/vagas.csv`.
- **Dados pessoais.** As vagas trazem nome de empresa e texto do anúncio, não
  dados de candidatos. A API e o dashboard expõem o que o portal já publicou, com
  link para a origem.

## Fontes bloqueadas ou fora da coleta

- **Catho e Indeed BR estão bloqueados** para cliente HTTP (página "Operação
  Inválida!" e desafio do Cloudflare). Foram avaliados e deixados de fora.
  **Nenhum dado é simulado** no lugar deles.
- **ProgramaThor responde HTTP 403 para IPs de nuvem**, então está fora da coleta
  agendada desde 15/09/2026. Continua funcionando da máquina local
  (`--sources programathor`), e as vagas antigas dela continuam no histórico.
- Qualquer fonte pode passar a bloquear, e o LinkedIn é a mais provável. Isso
  aparece como fonte `failed` ou alerta de qualidade, não como "0 vagas" silencioso
  ([`data-quality.md`](data-quality.md)).

## Técnicas

- **Os portais mudam.** Se um endpoint ou uma classe de HTML mudar, o coletor
  correspondente para de trazer resultados. As checagens de qualidade avisam
  (fonte zerada, queda brusca), mas não consertam.
- **Classificação por keyword erra em casos ambíguos.** A coluna `area_matches`
  (no CSV e no snapshot) mostra o que disparou cada classificação, para auditar e
  ajustar o YAML.
- **O LinkedIn não traz descrição** no card, então é classificado só pelo título e
  cai muito mais em "Outros/TI Geral".
- **Nível de entrada vem do título** em várias fontes. Na GeekHunter, o pré-filtro
  usa o slug. Uma vaga júnior sem marca de nível no título passa batido. O nível
  declarado pela Quero Vagas Tech é ignorado de propósito, porque marca gerentes
  como `Intern`.
- **Modalidade incompleta.** LinkedIn e Vagas.com não distinguem presencial de
  híbrido no card. Na coleta de 15/09/2026, o LinkedIn inteiro e 19 vagas do
  Vagas.com ficaram "Não informado" ([relatório](resultados-2026-09-15.md#remoto-híbrido-ou-presencial)).
  Para ler só o dado afirmado, filtre por fonte no dashboard.
- **Restam ~5 duplicatas cruzadas (≈1%)** que a deduplicação não pega, e isso é
  deliberado. Ela exige título idêntico e nomes de empresa compatíveis; sobram
  os casos em que o título também muda ("Analista de Testes Júnior" na Gupy vira
  "Analista de Testes Júnior (QA) - JBS") ou em que o portal grafa a cidade sem
  espaço ("Governador Valadares" → "Governadorvaladares").

  Medi a alternativa antes de descartá-la: casar títulos com 85% de similaridade
  resolveria 4 duplicatas e criaria **60 fusões falsas** — juntaria "VOLANTE C4 -
  ABAETÉ" com "VOLANTE C4 - GOVERNADOR VALADARES", que são vagas distintas em
  cidades distintas. Numa proporção de 15 erros para cada acerto, contar 5 vagas
  a mais é o problema menor.
- **A extração de tecnologias mede menção, não exigência.** Uma vaga que diz
  "diferencial: Python" conta igual a uma que exige Python.
- **Áreas pequenas dão contagens de tecnologia instáveis.** Com 9 vagas em
  DevOps, uma tecnologia citada em 2 delas já entra no top 8. Por isso o dashboard
  esconde o ranking geral abaixo de 30 vagas com tecnologia e os painéis por área
  abaixo de 15, e marca de 15 a 29 como indicativo.

## Frequência

- **Uma coleta a cada 2 dias**, disparada por um cron diário que o GitHub não
  garante no horário. Uma execução perdida adia a coleta em um dia
  ([`automation.md`](automation.md#frequência-cron-diário--guarda-de-intervalo)).
- **Vagas que abrem e fecham entre duas coletas** podem nunca aparecer.
- **`closed_at` sai atrasado:** a vaga só é encerrada depois de faltar em duas
  coletas confiáveis de dias diferentes, então a data de encerramento é a da
  segunda ausência, não a do fim real do anúncio.
- **Dias perdidos não são recuperáveis.** Os portais não mostram o passado, e o
  histórico só tem o que foi coletado.

## Viés das fontes grandes

- **É uma amostra, não o mercado inteiro.** O resultado depende dos 13 termos de
  busca em `scraper/config.py` e dos portais consultados. Termos diferentes mudam o
  ranking.
- **Poucas fontes pesam muito.** Na coleta de 15/09/2026, LinkedIn e Quero Vagas
  Tech foram dois terços do resultado final. O LinkedIn puxa a fatia de "Outros/TI
  Geral" (sem descrição), e a Quero Vagas Tech concentrou 64 das 96 vagas remotas.
  Uma variação no volume de uma dessas fontes muda os percentuais sem que o mercado
  mude ([relatório](resultados-2026-09-15.md)).
- **Perfis de empresa diferentes por portal.** Cada portal atrai um perfil de
  empresa (a Gupy, por exemplo, é um sistema de recrutamento usado pelas próprias
  empresas; a Quero Vagas Tech é um agregador com curadoria), e nenhum representa
  o mercado brasileiro todo.
- **Vagas replicadas por cidade** (uma mesma posição anunciada em 20 comarcas)
  contam como 20 vagas, porque são de fato 20 posições abertas, mas isso pesa no
  ranking. Olhe a empresa na lista de vagas se um número parecer estranho.

## Mudança de regras ao longo do histórico

- **Cada snapshot guarda a classificação do dia em que foi gravado.** Área,
  pontuação, `area_matches` e tecnologias são calculadas na coleta com os YAMLs
  daquele momento.
- **Mudar `scraper/rules/*.yml` não reclassifica o passado.** Como área e
  tecnologias entram no `content_hash`, a coleta seguinte grava snapshot novo para
  as vagas ainda vistas cuja classificação mudou. Vagas já encerradas e snapshots
  antigos ficam como estavam.
- **A série histórica mistura versões de regra.** Um salto de uma área no
  Histórico do dashboard pode ser mudança de regra, não de mercado. O snapshot não
  guarda qual versão das regras o gerou; o git log de `scraper/rules/` é a
  referência.
- **Não há como reprocessar**, porque o dado bruto dos portais não é guardado
  ([ADR 0004](decisoes/0004-sem-medalhao-nem-dbt.md)).
