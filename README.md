# lgpd-rag

Pergunte à LGPD e receba a resposta com o dispositivo de onde ela saiu, conferido pelo código contra o texto oficial da lei.

> **Em construção.** Etapa 4 de 5 pronta: a lei dividida em dispositivos, a busca medida contra um gabarito, a resposta com citação conferida pelo código e a medição com o modelo de verdade, já com a [melhoria da busca](#melhoria-da-busca). Falta a publicação.

## O texto da lei

O texto vem da página oficial da LGPD, com todas as alterações, no site do Planalto: [Lei nº 13.709/2018, texto compilado](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm).

O site costuma recusar download automático, então a página é salva pelo navegador:

1. Abra o link acima.
2. Salve a página (Ctrl+S) como "Página da Web, somente HTML", em `fonte/l13709compilado.html`.
3. Gere o arquivo com os dispositivos:

   ```
   python -m lgpd_rag.preparar fonte/l13709compilado.html
   ```

O resultado vai para `dados/lgpd.json`, com um dispositivo por linha e o SHA-256 da página de origem.

- **Notas do Planalto:** "Redação dada pela...", "Incluído pela..." e "Vigência" saem do texto.
- **Dispositivos revogados e vetados:** ficam na lista, marcados, para a numeração não ter buracos.
- **Direito autoral:** lei não tem direito autoral (Lei nº 9.610/98, art. 8º, IV), então o texto pode ficar no repositório.

## A busca

A busca acha os dispositivos que respondem à pergunta. Ela roda sem IA e sem custo.

- **O que é procurado:** cada dispositivo em vigor. Inciso e alínea são pedaços de frase ("II - acesso aos dados;"), então levam junto o texto do caput.
- **Como as palavras são comparadas:** sem acento, no singular e cortadas nos 6 primeiros caracteres. Assim, "consentimento" e "consentir" viram a mesma palavra. Testei cortes de 4, 5, 6 e 7 caracteres, e também sem corte; o de 6 acertou mais no desenvolvimento.
- **Ranking:** BM25.
- **Glossário** ([`glossario.py`](lgpd_rag/glossario.py)): troca palavras do dia a dia pelos termos da lei. Por exemplo, "vazamento" vira "incidente de segurança", "DPO" vira "encarregado" e "empresa" vira "controlador".
- **Resultado:** os 5 melhores artigos, com até 3 dispositivos de cada. Assim, um artigo com muitos incisos parecidos não esconde outro artigo que também responde.
- **Definições:** uma pergunta de conceito ("O que é tratamento?", "Quem é o titular?") vai direto à definição do art. 5º. Veja a [melhoria da busca](#melhoria-da-busca).

## Gabarito e resultados

O gabarito tem perguntas com os dispositivos que as respondem, escritos à mão e conferidos no texto da lei. Algumas perguntas usam os termos da lei, outras usam palavras do dia a dia, e algumas tratam de assuntos fora da LGPD. São dois arquivos:

- [`desenvolvimento.jsonl`](gabarito/desenvolvimento.jsonl): 30 perguntas que a lei responde e 4 fora dela. Serviu para ajustar a busca: o glossário, o corte das palavras e o limite de recusa.
- [`teste.jsonl`](gabarito/teste.jsonl): 16 perguntas que a lei responde e 4 fora dela. Foi medido uma vez só, no fim, com tudo congelado.

Estes números são da busca como ela era na etapa 3. A [melhoria da busca](#melhoria-da-busca) tem os de agora.

| | Desenvolvimento (usado para ajustar) | Teste (medido uma vez) |
|---|---|---|
| Artigo certo em 1º lugar | 21/30 (70%) | 13/16 (81%) |
| Artigo certo entre os 3 primeiros | 28/30 (93%) | 14/16 (88%) |
| Artigo certo entre os 5 primeiros | 30/30 (100%) | 14/16 (88%) |
| Dispositivo certo entre os 5 primeiros | 29/30 (97%) | 13/16 (81%) |

Sem o glossário, o teste cai para 62% em 1º lugar e 81% entre os 5 primeiros.

**O que a busca erra no teste:**
- "Posso reclamar de uma empresa no Procon?": a lei diz "organismos de defesa do consumidor" (art. 18, § 8º).
- "A empresa pode ser multada todos os dias?": a lei diz "multa diária" (art. 52, III).

A busca por palavra não liga sinônimos que não estão no glossário. A busca por significado (embeddings) ficou para depois: na medição com o modelo, as falhas da busca foram de outro tipo (veja [Resultado](#resultado-com-o-modelo-de-verdade)).

**O que não deu certo: a recusa pela busca.**
- **A tentativa:** a busca mede quanto das palavras da pergunta existe na lei e recusa quando é pouco. O limite foi escolhido no desenvolvimento (0,28).
- **O resultado no teste:** recusou 3 de 16 perguntas boas e deixou passar 3 de 4 perguntas de fora.
- **A conclusão:** a busca por palavra não sabe dizer quando a lei não trata do assunto.
- **Como ficou:** agora ela só recusa quando nenhuma palavra da pergunta existe na lei ("alíquota do ICMS"). O resto da recusa fica com o modelo, que lê os dispositivos (etapa 3), e com o código, que confere a citação.

O conjunto de teste já foi visto uma vez. Por isso, a medição com o modelo usou um conjunto novo, escrito antes da primeira chamada: [`final.jsonl`](gabarito/final.jsonl).

Para medir:

```
python -m lgpd_rag.avaliar gabarito/desenvolvimento.jsonl
python -m lgpd_rag.avaliar gabarito/teste.jsonl --sem-glossario
python -m lgpd_rag.avaliar gabarito/teste.jsonl --limiar 0.28
```

## A resposta com citação conferida

1. **A busca acha os dispositivos.** Se nenhuma palavra da pergunta existe na lei, a resposta é uma recusa, e o modelo nem é chamado.
2. **Os trechos vão para o modelo** ([`contexto.py`](lgpd_rag/contexto.py)). Vão os dispositivos encontrados, cada um com o caput de cima. Quando um deles faz parte de uma lista, vai a lista inteira, até 15 itens. O modelo devolve um JSON com a resposta e as citações: o id do dispositivo e um pedaço copiado dele.
3. **O código confere a resposta** ([`conferencia.py`](lgpd_rag/conferencia.py)). Só aparece para quem perguntou a resposta que cumprir todas estas condições:
   - tem pelo menos uma citação;
   - cada citação aponta para um dispositivo que foi enviado ao modelo;
   - o trecho citado está no texto desse dispositivo, letra por letra. Só não contam diferenças de espaço, maiúscula e aspas;
   - o trecho tem pelo menos 15 caracteres, para "dados pessoais" sozinho não servir de prova. Um dispositivo mais curto, como "a reincidência;", só passa citado inteiro;
   - a resposta só menciona artigos citados, ou que aparecem no texto dos dispositivos citados.

Se alguma condição falha, quem perguntou vê uma frase fixa ("Não consegui uma resposta com citação conferida na lei") e a lista de dispositivos que a busca achou. Quando o modelo diz que a lei não trata do assunto, o texto mostrado também é uma frase fixa do código, nunca o que o modelo escreveu.

**Prompt injection:**
- As instruções ficam só na mensagem de sistema, que só o código escreve.
- A pergunta e os trechos vão entre marcadores, como dado.
- Os sinais `<` e `>` da pergunta são trocados, para quem pergunta não conseguir fechar um marcador e abrir outro.
- Os testes simulam o pior caso: um modelo que obedece à ordem escondida na pergunta. Mesmo assim, nada passa sem uma citação real da lei.

**O que a conferência não garante:** ela garante que toda resposta está amarrada a um trecho real da lei. Não garante que a conclusão esteja certa, porque o modelo pode citar um trecho real e interpretar errado. Por isso as respostas do modelo de verdade foram revisadas à mão (veja [Resultado](#resultado-com-o-modelo-de-verdade)). As instruções do modelo não são segredo: estão neste repositório ([`prompt.py`](lgpd_rag/prompt.py)).

Para ver o que iria para o modelo, sem chamar nenhum:

```
python -m lgpd_rag.perguntar "Minha empresa precisa ter um DPO?"
```

## O modelo de verdade

O modelo é o Gemini, chamado sem nenhuma biblioteca ([`gemini.py`](lgpd_rag/gemini.py)). A configuração é temperatura 0, resposta em JSON e pouco raciocínio. Ele pode ser chamado de dois jeitos:

- **Google AI Studio, com chave:** é o mais simples para quem clona o repositório. A chave vem da variável de ambiente `GEMINI_API_KEY` e vai no cabeçalho do pedido, nunca na URL.
- **Vertex AI, sem chave** (`--vertex PROJETO`): usa o login do gcloud de quem roda (`gcloud auth application-default login`) e cobra no projeto indicado. Esse projeto pode ter orçamento e alertas próprios. A cobrança vai para ele, e não para o projeto padrão do gcloud.

O modelo padrão é o `gemini-3.8-flash`, e a variável `GEMINI_MODELO` troca. Nenhuma mensagem de erro mostra a chave, o token ou o login.

Quando o serviço está sobrecarregado (HTTP 503 ou tempo esgotado), o cliente tenta de novo até 5 vezes, com espera crescente, e mostra cada espera no terminal. A avaliação para depois de 3 falhas seguidas.

**Avaliação de ponta a ponta** ([`avaliar_respostas.py`](lgpd_rag/avaliar_respostas.py)):
- [`final.jsonl`](gabarito/final.jsonl): 20 perguntas que a lei responde e 5 fora dela, escritas antes da primeira chamada ao modelo. Cada uma tem uma nota com o que a resposta certa precisa dizer.
- [`ataques.jsonl`](gabarito/ataques.jsonl): 6 tentativas de prompt injection.
- **O que mede:** quantas respostas passaram na conferência, quantas citaram o dispositivo esperado, quantas recusas estavam certas e o custo.
- **Revisão:** as respostas ficam em `resultados/` e são revisadas uma a uma contra a nota ([`revisao.md`](resultados/revisao.md) e [`revisao-busca-nova.md`](resultados/revisao-busca-nova.md)).

**Custo:** sem `--confirmo-custo`, nada é chamado. `--estimar` mostra o custo antes de rodar, e a rodada para antes de passar do teto.

```
python -m lgpd_rag.avaliar_respostas gabarito/final.jsonl --estimar
python -m lgpd_rag.avaliar_respostas gabarito/final.jsonl --confirmo-custo --teto-usd 0.50
python -m lgpd_rag.avaliar_respostas gabarito/final.jsonl --confirmo-custo --vertex meu-projeto
```

## Resultado com o modelo de verdade

A rodada foi em 15/11/2026, com o `gemini-3.8-flash` pelo Vertex AI. Cada resposta foi lida e comparada com a nota do gabarito e com a lei. A revisão, uma a uma, está em [`resultados/revisao.md`](resultados/revisao.md), e as respostas brutas estão ao lado.

| 20 perguntas que a lei responde | |
|---|---|
| Respondidas com citação conferida | 17/20 (85%) |
| Certas na revisão manual | 14/20 (70%) |
| Certas, mas incompletas | 3/20 |
| Recusadas porque a busca não achou o dispositivo | 3/20 |
| Inventaram dispositivo ou disseram o contrário da lei | 0/20 |

| Outras | |
|---|---|
| Perguntas fora da LGPD recusadas | 5/5 |
| Ataques de prompt injection que funcionaram | 0/6 |
| Respostas barradas pela conferência | 0/31 |

**O que a revisão mostrou:**
- **Recusas:** nas 3, o dispositivo certo não chegou ao modelo, e ele recusou em vez de inventar.
  - "O que é tratamento?" e "Quem é o titular?": "tratamento" e "titular" aparecem em cerca de metade dos artigos em vigor (40 e 35 de 73), e a busca não chega à definição no art. 5º.
  - A empresa dos EUA: o glossário troca "Estados Unidos" por "transferência internacional", e o art. 3º fica de fora.
- **Respostas incompletas:** nas 3, o limite de 3 dispositivos por artigo cortou a lista que o modelo recebeu.
  - Em duas, a resposta parece trazer a lista toda e engana por omissão. Na pergunta sobre dados sensíveis, o modelo recebeu 1 das 7 hipóteses. Na pergunta sobre danos, recebeu 2 dos 3 casos do art. 43.
- **O ataque que trouxe um "art. 99" falso:** a resposta ignorou o artigo falso, citou o art. 41 e disse o certo.
- **A conferência:** não precisou barrar nada nesta rodada. Os testes dela continuam com um modelo simulado que obedece ao ataque.

**Onde está o gargalo:** na busca, não no modelo. As melhorias são:
- mandar a lista inteira quando a busca acha um inciso ou uma alínea;
- achar as definições do art. 5º em perguntas como "o que é" e "quem é";
- rever o glossário.

Este conjunto já foi visto, então os ajustes foram medidos com outro, escrito antes de mexer no código: veja a [melhoria da busca](#melhoria-da-busca).

**Custo:** US$ 0,04 nas duas rodadas (31 chamadas, 86 s). O valor é calculado com os tokens que o Vertex AI informou e os preços do código.

## Melhoria da busca

A revisão acima mostrou três falhas da busca. Cada uma ganhou uma correção:

| Falha | Correção |
|---|---|
| Pergunta de conceito não chegava à definição ("tratamento" e "titular" pesam pouco no BM25) | "O que é", "quem é", "o que a lei chama de" e "qual a diferença entre" vão direto à definição do art. 5º ([`busca.py`](lgpd_rag/busca.py)) |
| O modelo recebia parte de uma lista e respondia como se fosse toda | Quando a busca acha um item de lista, a lista inteira vai para o modelo, até 15 itens ([`contexto.py`](lgpd_rag/contexto.py)). Das 44 listas da lei, ficam de fora só as 19 definições do art. 5º e as 24 competências da ANPD |
| "Empresa dos Estados Unidos" levava só à transferência internacional, e o art. 3º sumia | "Estrangeiro" leva ao art. 3º, e "no Brasil" e "brasileiros" levam a "território nacional" ([`glossario.py`](lgpd_rag/glossario.py)) |

**Ajustes medidos no desenvolvimento:**
- O limite da lista começou em 12 e subiu para 15, para caber as 13 hipóteses do art. 33.
- Também testei pôr "país sede" em "Estados Unidos" e "outro país". Isso tirou o art. 33 do 1º lugar nas perguntas de transferência, então essas entradas ficaram como estavam.

**Medida nova, a "resposta inteira nos trechos":** o dispositivo esperado está no que vai para o modelo e, se ele abre uma lista, todos os itens dela também. Sem isso, a resposta sai recusada ou incompleta, como na revisão acima.

**Como foi medido:**
- O gabarito novo, [`final2.jsonl`](gabarito/final2.jsonl), tem 20 perguntas que a lei responde e 5 fora dela.
- Ele foi escrito antes de mexer no código, e a busca só rodou nele uma vez, no fim.
- Tem mais perguntas de definição e de lista (10 de 20), os dois tipos em que a busca falhou.
- "Antes" é a busca do commit `0c3bc61`, da etapa 4.

| Só a busca, sem modelo | Antes | Depois |
|---|---|---|
| Desenvolvimento (usado para ajustar): artigo certo em 1º lugar | 21/30 (70%) | 24/30 (80%) |
| Desenvolvimento: resposta inteira nos trechos | 17/30 (57%) | 30/30 (100%) |
| **Gabarito novo (medido uma vez): artigo certo em 1º lugar** | 9/20 (45%) | **13/20 (65%)** |
| **Gabarito novo: artigo certo entre os 5 primeiros** | 18/20 (90%) | **19/20 (95%)** |
| **Gabarito novo: resposta inteira nos trechos** | 12/20 (60%) | **18/20 (90%)** |

No conjunto de teste da etapa 3, que já tinha sido visto, a resposta inteira passou de 11/16 para 14/16, e as outras medidas não mudaram.

**O que ainda falha no gabarito novo:**
- "Quais são as competências da ANPD?": a lista tem 24 itens e fica de fora de propósito. A resposta pode resumir, mas não pode parecer completa.
- "Em quais casos os dados podem ser guardados depois do fim do tratamento?": a lei diz "conservação", e a busca não liga as duas palavras.

### Com o modelo

A rodada foi em 16/11/2026, com o mesmo `gemini-3.8-flash` pelo Vertex AI. O gabarito novo rodou com o modelo uma vez só. A revisão, uma a uma, está em [`resultados/revisao-busca-nova.md`](resultados/revisao-busca-nova.md).

| Gabarito novo: 20 perguntas que a lei responde | |
|---|---|
| Respondidas com citação conferida | 18/20 (90%) |
| Certas na revisão manual | 16/20 (80%) |
| Certas, mas incompletas (nenhuma parece trazer tudo) | 2/20 |
| Recusada porque a busca não achou o dispositivo | 1/20 |
| Barrada por um defeito da conferência, já corrigido | 1/20 |
| Inventaram dispositivo ou disseram o contrário da lei | 0/20 |

| Outras | |
|---|---|
| Perguntas fora da LGPD recusadas | 5/5 |
| Ataques de prompt injection que funcionaram | 0/6 |

O gabarito novo não rodou com a busca antiga e o modelo. Nele, a comparação de antes e depois é a da busca, na tabela acima.

**O conjunto final antigo, de novo:** as respostas certas foram de 14/20 para 20/20, e as 6 falhas da [revisão de 15/11](#resultado-com-o-modelo-de-verdade) sumiram. Os diagnósticos saíram desse conjunto, então ele só confirma as correções e não mede a melhoria.

**O que a revisão mostrou:**
- **A conferência barrou uma resposta que não tinha como passar.** O modelo citou o art. 52, § 1º, V, que é só "a reincidência;". A conferência exigia pelo menos 15 caracteres no trecho, e o inciso inteiro, sem o ponto e vírgula, tem 14. Sete dispositivos em vigor eram curtos assim e não podiam ser citados.
  - **Corrigido depois da rodada:** um trecho mais curto passa quando é o dispositivo inteiro, e um teste cita inteiro cada dispositivo em vigor.
  - **O número não muda:** a resposta barrada não é salva, então não dá para saber se estava certa. Ela continua contada como barrada.
- **As duas incompletas:** a das competências da ANPD diz "entre as competências estão", mas escolhe competências secundárias. A dos órgãos de pesquisa não diz que a anonimização deve ser usada sempre que possível.
- **A recusa:** a pergunta sobre dados "guardados", que a lei chama de "conservação". O modelo recusou em vez de inventar.

**Custo:** nas mesmas 25 perguntas do conjunto antigo, o texto enviado subiu de 28.715 para 42.377 tokens (48% a mais), e o custo de US$ 0,035 para US$ 0,046. As três rodadas de 16/11 custaram cerca de US$ 0,10 (54 chamadas).

```
python -m lgpd_rag.avaliar gabarito/final2.jsonl
python -m lgpd_rag.avaliar gabarito/desenvolvimento.jsonl --sem-definicoes --sem-listas
python -m lgpd_rag.avaliar_respostas gabarito/final2.jsonl --confirmo-custo --teto-usd 0.30
```

## Testes

Não há dependências. Rode com Python 3.12 ou mais novo:

```
python -m unittest -v
```

## Licença

MIT.
