# Limitações

O que este projeto **não** mede bem, e por quê. Vale ler antes de citar um número
do dashboard, da API ou de um relatório datado. Fontes em [`fontes.md`](fontes.md);
classificação em [`classificacao.md`](classificacao.md).

## Éticas e de uso dos dados

- **Coleta de páginas e APIs públicas, sem login.** Os endpoints de Gupy, Trampos.co,
  LinkedIn, Quero Vagas Tech e Solides são os que o próprio front de cada site
  chama; não são APIs oficiais nem têm contrato de uso para terceiros.
- **`robots.txt` respeitado onde muda o caminho, com uma exceção.** Na
  GeekHunter, `/api/` e `/feeds/` são proibidos, então a coleta vai pelo sitemap
  e pela página de cada vaga ([detalhe](fontes.md#sobre-a-geekhunter)). **O
  LinkedIn é a exceção:** o `robots.txt` dele proíbe `/jobs-guest/` (e `/` para
  qualquer robô), e o projeto usa esse caminho tanto na busca quanto no detalhe de
  cada vaga de entrada. É decisão consciente do mantenedor, com teto e disjuntor
  ([ADR 0010](decisoes/0010-detalhe-do-linkedin-e-modalidade-inferida.md)).
- **Carga pequena de propósito.** User-Agent identificável, 1,5 s entre
  requisições com jitter, backoff em 429/5xx respeitando `Retry-After`, e nada de
  buscar uma página por vaga quando isso multiplicaria a carga (as 773 páginas da
  GeekHunter) ([Educação com o servidor](fontes.md#educação-com-o-servidor)). No
  LinkedIn, o detalhe é buscado só para as vagas de entrada, até 300 por coleta
  (cerca de 250 requisições a mais por dia).
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
- **O LinkedIn só tem descrição quando o detalhe responde.** O card da busca não
  a traz; ela vem da página de detalhe de cada vaga de entrada. Se o detalhe
  falhar ou passar do teto, a vaga fica só com o título e cai muito mais em
  "Outros/TI Geral". As vagas do LinkedIn gravadas antes de 22/09/2026 não têm
  descrição.
- **Nível de entrada vem do título** em várias fontes. Na GeekHunter, o pré-filtro
  usa o slug. Uma vaga júnior sem marca de nível no título passa batido. O nível
  declarado pela Quero Vagas Tech e pelo Solides é ignorado de propósito: a
  primeira marca gerentes como `Intern`, e o segundo deixa o campo vazio na
  maioria das vagas.
- **A busca do Solides olha só o título.** A descrição não entra no filtro de
  texto da API, então vaga de tecnologia cujo título não repita nenhum dos 13
  termos do projeto não é encontrada nessa fonte
  ([detalhe](fontes.md#sobre-o-solides)).
- **O Solides lista vagas antigas como abertas.** Nas 39 vagas finais de
  22/09/2026 a idade mediana era de 235 dias e 14 passavam de um ano, incluindo
  anúncios de "Banco de Talentos" que a empresa nunca encerra. A coleta não
  filtra por idade — grava a data que o portal publica —, então a contagem de
  vagas abertas dessa fonte é inflada por anúncio perene.
- **Modalidade incompleta.** LinkedIn e Vagas.com não distinguem presencial de
  híbrido no card. Na coleta de 15/09/2026, o LinkedIn inteiro e 19 vagas do
  Vagas.com ficaram "Não informado" ([relatório](resultados-2026-09-15.md#remoto-híbrido-ou-presencial)).
  Desde 22/09/2026 a modalidade que falta é inferida do título, do local e da
  descrição ([detalhe](classificacao.md#modalidade-inferida-do-texto)). Numa
  amostra de 39 vagas do LinkedIn, 14 ganharam modalidade; as outras, em geral,
  não citam modalidade em lugar nenhum. A inferência é conservadora e erra pouco,
  mas é inferência: para ler só o dado afirmado pelo portal, filtre Gupy, Solides,
  Quero Vagas Tech e GeekHunter no dashboard.

  O LinkedIn tem a modalidade como campo, mas só para quem está logado, e o filtro
  de modalidade da busca é ignorado sem login ([detalhe](fontes.md#sobre-o-linkedin-jobs)).
  Numa amostra de 50 vagas de entrada com descrição (23/09/2026), 31 seguiram "Não
  informado", e umas 20 delas não citam modalidade em lugar nenhum. É um teto da
  fonte, não da regra. Por isso a Overview do dashboard diz de que fontes vêm as
  vagas sem modalidade e dá o % remoto também só entre as que informam.

  Como referência para ler o "Não informado": nas fontes que informam a
  modalidade, das 168 vagas com cidade cujo texto não diz o regime, 126 eram
  presenciais (75%), 36 híbridas (21%) e 6 remotas (4%) (medido em 22/09/2026). O
  projeto **não** assume Presencial só porque a cidade foi informada: erraria 1 em
  4, quase sempre lendo híbrido como presencial, e o chute ficaria indistinguível
  do dado afirmado ([detalhe](classificacao.md#modalidade-inferida-do-texto)).
- **Restam ~2 duplicatas cruzadas** que a deduplicação não pega, e isso é
  deliberado. As regras de texto exigem título idêntico e nomes de empresa
  compatíveis; sobram os casos em que o título também muda ("Analista de Testes
  Júnior" na Gupy vira "Analista de Testes Júnior (QA) - JBS") ou em que o
  portal grafa a cidade sem espaço ("Governador Valadares" →
  "Governadorvaladares").

  Antes das regras de texto vem o id embutido no link de candidatura, que é
  prova mais dura porque não depende de como cada portal escreveu as coisas.
  Ele resolve justamente os casos em que empresa **e** título mudam — "Estágio
  Aurora" e "Programa de Estágios" anunciam a mesma vaga da Gupy, e nenhuma
  comparação de texto pegaria. Medido sobre as exportações de 15 e 16/09: pega
  3 duplicatas por coleta, sem nenhuma fusão falsa. Link que não carrega id
  (slug de título, `manual://...`, página de carreiras) simplesmente não gera
  chave e cai nas regras de texto.

  Medi a alternativa antes de descartá-la: casar títulos com 85% de similaridade
  resolveria 4 duplicatas e criaria **60 fusões falsas** — juntaria "VOLANTE C4 -
  ABAETÉ" com "VOLANTE C4 - GOVERNADOR VALADARES", que são vagas distintas em
  cidades distintas. Numa proporção de 15 erros para cada acerto, contar 5 vagas
  a mais é o problema menor.
- **A extração de tecnologias mede menção, não exigência.** Uma vaga que diz
  "diferencial: Python" conta igual a uma que exige Python.
- **A taxonomia de 17 áreas agravou isso.** Com mais áreas, cada uma tem menos
  vagas: na coleta de 15/09, os painéis por área passaram a cobrir 77% das vagas
  com tecnologia, contra 92% na taxonomia de 10 áreas
  ([ADR 0008](decisoes/0008-taxonomia-de-areas-expandida.md)).
- **Áreas pequenas dão contagens de tecnologia instáveis.** Com 9 vagas em
  DevOps, uma tecnologia citada em 2 delas já entra no top 8. Por isso o dashboard
  esconde o ranking geral abaixo de 30 vagas com tecnologia e os painéis por área
  abaixo de 15, e marca de 15 a 29 como indicativo.

## Frequência

- **Uma coleta por dia** desde 22/09/2026 (antes eram 2 dias), disparada por um
  cron diário que o GitHub não garante no horário. Uma execução perdida adia a
  coleta em um dia
  ([`automation.md`](automation.md#frequência-cron-diário--guarda-de-intervalo),
  [ADR 0009](decisoes/0009-coleta-diaria.md)).
- **Vagas que abrem e fecham entre duas coletas** podem nunca aparecer. A janela
  encolheu de dois dias para um, mas não fechou: vaga publicada e removida no
  mesmo dia continua invisível.
- **`closed_at` sai atrasado:** a vaga só é encerrada depois de faltar em duas
  coletas confiáveis de dias diferentes, então a data de encerramento é a da
  segunda ausência, não a do fim real do anúncio.
- **A régua do encerramento mudou no meio do histórico.** Com a coleta de 2 em 2
  dias, uma vaga ausente levava ~4 dias para ser encerrada; com a coleta diária,
  leva ~2. As vagas gravadas antes de 22/09/2026 foram encerradas pela régua
  antiga e **não** são recalculadas, então a vida média observada das vagas cai
  a partir dessa data sem que o mercado tenha mudado. Ler a série histórica
  atravessando 22/09/2026 exige esse cuidado.
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
- **Mudar `scraper/rules/*.yml` não reclassifica o passado sozinho.** Como área e
  tecnologias entram no `content_hash`, a coleta seguinte grava snapshot novo para
  as vagas ainda vistas cuja classificação mudou. Vagas já encerradas e snapshots
  antigos ficam como estavam.
- **Para a área, dá para reclassificar.** `scripts/reclassificar_areas.py` refaz a
  classificação de todo o histórico a partir de `title` e `description`, que é tudo
  o que o classificador lê, e recalcula o `content_hash` — sem esse recálculo a
  coleta seguinte gravaria um snapshot por vaga registrando uma mudança que nunca
  houve (medido: 426 de 597). Foi o que a mudança de taxonomia de 21/09 usou
  ([ADR 0008](decisoes/0008-taxonomia-de-areas-expandida.md)). Para tecnologias não
  existe equivalente.
- **A coleta de 22/09/2026 gravou ~270 snapshots sem mudança real.** A
  reclassificação de 21/09 gravou `area_matches` com `"; "` e sem limite de itens,
  enquanto a coleta usa `", "` e no máximo 12 (`classifier.formatar_evidencia`).
  Como a evidência entra no `content_hash`, a coleta seguinte viu assinatura
  diferente em quase toda vaga: das 272 vagas com snapshot em 22/09 que já tinham
  um anterior, 270 mudaram só no separador. Esses snapshots **não foram apagados**
  (o histórico não se apaga), então **22/09 tem uma contagem inflada de mudanças
  de estado** no Histórico. As contagens de vagas não mudam, porque contam `jobs`
  únicos. O script passou a usar o mesmo formato da coleta, e um teste com mais de
  uma keyword passou a pegar a divergência.
- **Para a modalidade que falta, também.** O mesmo script preenche a modalidade
  dos snapshots gravados sem ela, pela regra de `modalidade.yml`, e nunca mexe na
  modalidade informada pelo portal
  ([ADR 0010](decisoes/0010-detalhe-do-linkedin-e-modalidade-inferida.md)). As
  vagas antigas do LinkedIn não têm descrição gravada, então nelas só título e
  local contam. Na primeira coleta com o detalhe do LinkedIn, cada vaga ativa
  dele ganha um snapshot novo: a descrição passou a ser observada.
- **A série histórica mistura versões de regra.** Um salto de uma área no
  Histórico do dashboard pode ser mudança de regra, não de mercado. O snapshot não
  guarda qual versão das regras o gerou; o git log de `scraper/rules/` é a
  referência.
- **Não há como reprocessar o bruto**, porque o JSON/HTML dos portais não é
  guardado ([ADR 0004](decisoes/0004-sem-medalhao-nem-dbt.md)). O que dá para
  refazer é o que se calcula a partir dos campos guardados, como a área.
