# ADR 0010 — Detalhe do LinkedIn e modalidade inferida do texto

- **Status:** aceito
- **Data:** 22/09/2026

## Contexto

A modalidade "Não informado" era a maior fatia do campo por causa de duas fontes
cujo card não separa presencial de híbrido. No seed de 15/09/2026, o LinkedIn tinha
**244 de 264** vagas (92%) sem modalidade, e o Vagas.com, 19. A cidade já era
capturada em todas as fontes; o que faltava era a modalidade.

No LinkedIn, a modalidade só aparece escrita na descrição, e o card da busca não
traz descrição. Até aqui o projeto tinha uma regra explícita contra buscá-la
([`../limitacoes.md`](../limitacoes.md#éticas-e-de-uso-dos-dados)): nada de uma
página por vaga quando isso multiplica a carga no portal. Além disso, o
`robots.txt` do LinkedIn tem `User-agent: *` / `Disallow: /`, com `Disallow:
/jobs-guest/` explícito para cada robô nomeado. Ele pede que quem queira rastrear
peça autorização. Isso já valia para a busca que o projeto usava desde o início,
não só para o detalhe.

## Decisão

1. **Inferir a modalidade do texto** quando o portal não a informa
   (`scraper/modalidade.py` + `scraper/rules/modalidade.yml`), em todas as fontes.
   O valor estruturado do portal nunca é sobrescrito. As regras são conservadoras:
   - frases de modalidade, não palavras soltas ("suporte remoto" e "atendimento
     presencial" são atividades);
   - título e local decidem antes da descrição;
   - duas modalidades citadas ficam "Não informado".
2. **Buscar a descrição do LinkedIn** no endpoint de convidado
   `/jobs-guest/jobs/api/jobPosting/<id>`, só para as vagas cujo título passa no
   filtro de senioridade, com teto (`Settings.linkedin_max_detalhes`, 300) e
   disjuntor (para após 3 falhas seguidas). A falha no detalhe não conta como
   falha da fonte.
3. **Aplicar a inferência ao histórico** com `scripts/reclassificar_areas.py`, que
   passa a recalcular também `workplace_type` (só onde falta) e o `content_hash`.

A decisão 2 foi tomada pelo mantenedor sabendo do `robots.txt`, e fica registrada
aqui e em [`../limitacoes.md`](../limitacoes.md).

## Consequências

- **Ganha:**
  - numa amostra real de 39 vagas de entrada do LinkedIn (22/09/2026), a
    modalidade afirmada passou de **0 para 14**. As outras 25 descrições, em
    geral, não citam modalidade nenhuma, só a cidade;
  - o LinkedIn passa a ter descrição, então a área deixa de depender só do título
    (45% das vagas dele caíam em "Outros/TI Geral") e as tecnologias passam a ser
    extraídas;
  - contra o rótulo dos portais que informam a modalidade, a regra acerta **85 de
    97** palpites. Dos 12 restantes, 8 são rótulo do Quero Vagas Tech contradito
    pelo próprio título ("Estágio (Presencial)" marcado como remoto).
- **Custa:**
  - **cerca de 250 requisições a mais por coleta**, uns 6 minutos com 1,5 s de
    delay;
  - **mais exposição a bloqueio.** Se o LinkedIn bloquear o IP do Actions, a busca
    também para, e a maior fonte zera;
  - **a coleta contraria o `robots.txt` do LinkedIn** numa escala maior que antes;
  - na primeira coleta depois da mudança, **cada vaga ativa do LinkedIn ganha um
    snapshot novo**, porque a descrição passou a ser observada. É uma mudança real
    de estado, não um artefato;
  - o histórico do LinkedIn melhora pouco: as vagas antigas não têm descrição
    gravada, e a reclassificação só usa título e local.

## O que mudaria a decisão

- O LinkedIn passar a bloquear (fonte `failed`, ou o log
  `[linkedin] N falhas seguidas no detalhe`): desligar o detalhe
  (`linkedin_max_detalhes=0`) antes de a busca também cair.
- Um pedido do LinkedIn, ou uma mudança nos termos de uso, para parar a coleta:
  tirar a fonte da coleta padrão (`FORA_DA_COLETA_PADRAO`), como a ProgramaThor.
- O ganho medido ficar abaixo de ~20% das vagas com modalidade: o custo em
  requisições deixa de compensar.
- **Alternativa medida e descartada:** assumir Presencial quando a vaga informa a
  cidade e o texto não diz o regime. Nas fontes que informam a modalidade, essas
  168 vagas eram 75% presenciais, 21% híbridas e 4% remotas. Erraria 1 em 4, e o
  chute ficaria indistinguível do dado afirmado. Voltaria à mesa se o dashboard
  precisar de uma estimativa, e só como categoria separada ("Presencial provável"),
  nunca misturada a "Presencial".
