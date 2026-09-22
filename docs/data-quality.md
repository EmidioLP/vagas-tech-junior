# Qualidade da coleta

Testes de software (`tests/`) respondem "o código funciona?". As checagens desta
página respondem "o dado **desta execução** é confiável?". Elas rodam dentro do
pipeline, a cada coleta, em `scraper/qualidade.py`.

**O que elas não fazem:** não corrigem, não apagam e não deixam de gravar nada. Só
sinalizam. As vagas são gravadas antes das checagens, e o histórico fica intacto.

## O incidente que motivou

Um portal muda o HTML, o parser deixa de achar cards e nenhuma requisição falha.
Sem as checagens, a fonte saía como `ok` com 0 vagas e a execução como `success`:
o dashboard mostraria um mercado encolhendo que não existe. Pior, duas coletas
assim encerrariam vagas que continuam abertas.

## Regras

Os limites foram calibrados com a coleta completa de 15/09/2026 (1.733 vagas brutas,
603 finais, a mesma do `seed/vagas.csv`), a única completa quando as regras foram
escritas. Um teste garante que essa coleta **não gera nenhum alerta**.

| Regra | Severidade | Dispara quando | Não avalia quando | Ação recomendada |
|---|---|---|---|---|
| `fonte_zerada` | alta | fonte da coleta padrão lista 0 vagas **sem** requisição falha nem erro | escopo parcial; fonte com erro (já é `failed`) | abrir o portal no navegador, comparar com a resposta capturada em `tests/test_sources.py` e ajustar o parser |
| `queda_brusca` | alta | vagas brutas < 30% da mediana das coletas completas anteriores | escopo parcial; menos de 3 coletas no histórico; mediana < 30 | verificar se o portal mudou a paginação ou a busca; se a queda for real, recalibrar |
| `area_fora_do_dominio` | alta | área que não está em `scraper/rules/areas.yml` | — | conferir se alguém renomeou uma área no YAML sem migrar o dado |
| `modalidade_fora_do_dominio` | alta | modalidade fora de Remoto, Híbrido, Presencial, Não informado ou vazio | — | corrigir o mapeamento de modalidade da fonte |
| `campo_vazio` | alta ou baixa | fatia de vagas da fonte com o campo vazio acima do limite (tabela abaixo) | fonte com menos de 20 vagas finais; fonte isenta do campo | ver se o seletor/campo do portal mudou |
| `url_invalida` | baixa | URL presente que não começa com `http://` ou `https://` | — | ver como a fonte monta a URL; o dashboard já não transforma essas URLs em link |
| `data_no_futuro` | baixa | data de publicação depois do dia da coleta | — | revisar o formato de data da fonte (`api/dates.py`) |
| `classificacao_degenerada` | baixa | "Outros/TI Geral" acima de 55% das vagas finais (15/09: 33%) | menos de 50 vagas finais | revisar mudanças recentes em `areas.yml` ou numa fonte que perdeu a descrição |

### Vazios esperados por fonte

Campo opcional **nunca** vira obrigatório para todas as fontes. Quem nunca informa
um campo fica isento dele:

| Campo | Limite | Severidade | Isentas | Observado em 15/09 |
|---|---|---|---|---|
| descrição | 20% | alta | LinkedIn (o card não tem descrição; vem do detalhe, que pode ser bloqueado sem a fonte falhar) | 0–1%; LinkedIn 100% |
| empresa | 20% | alta | — | 0% |
| modalidade "Não informado" | 40% | baixa | LinkedIn, Vagas.com.br (a listagem não informa; a inferência pelo texto cobre só parte) | 0–1%; LinkedIn e Vagas.com 100% |
| data de publicação | 40% | baixa | ProgramaThor (não informa) | 0–13%; ProgramaThor 100% |
| tecnologias | 50% | baixa | LinkedIn, Vagas.com.br (pouco texto) | 3–13%; LinkedIn 88%, Vagas.com 74% |

## Efeito no status

| Situação | Fonte | Execução | Exit | Encerra vagas da fonte? |
|---|---|---|---|---|
| só alertas baixos | inalterada | inalterada | inalterado | como antes |
| alerta alto de uma fonte | `ok` → `partial` (`failed` continua `failed`) | `partial` | **1** | **não** |
| alerta alto global (sem fonte) | inalterada | `partial` | **1** | como antes |

Exit 1 deixa o job do GitHub Actions vermelho, e o GitHub avisa por e-mail. A
execução **continua contando** para a guarda de intervalo (`partial`): o dado foi
gravado, e um alerta não faz a coleta rodar fora da cadência combinada. Como a
fonte com alerta alto não fica `ok`, ela não encerra vagas. Isso impede que uma
queda brusca feche metade das vagas abertas.

## Onde os alertas aparecem

- **Resumo do Actions** (`--resumo`): seção *Qualidade*, com as altas em negrito e
  primeiro.
- **Terminal:** bloco "Qualidade (N alerta(s))".
- **`collection_runs.summary.qualidade`:** uma lista de
  `{regra, severidade, fonte, valor, limite, mensagem}`. Nunca entra URL, título nem
  texto de vaga, só contagens.
- **`collection_runs.reason`:** "alertas de qualidade: regra (fonte), ...".

```sql
SELECT started_at, status, summary->'qualidade' AS alertas
FROM collection_runs
WHERE jsonb_array_length(summary::jsonb->'qualidade') > 0
ORDER BY started_at DESC;
```

## Recalibrar

O histórico da regra de queda sai de `persistence/execucoes.historico_vagas_brutas`:
as últimas 5 coletas completas `success`/`partial`, ignorando os dias em que a fonte
falhou ou veio zerada. Com mais coletas acumuladas:

1. Tire as vagas brutas por fonte de `collection_runs.summary` e os vazios por fonte
   do banco.
2. Ajuste as constantes no topo de `scraper/qualidade.py`, citando no comentário o
   dado que justifica o novo valor.
3. Atualize as tabelas desta página e o teste de calibragem em
   `tests/test_qualidade.py`.
