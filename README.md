# lgpd-rag

Pergunte à LGPD e receba a resposta com o dispositivo de onde ela saiu, conferido pelo código contra o texto oficial da lei.

> **Em construção.** Etapa 1 de 5: a lei dividida em dispositivos (artigos, parágrafos, incisos e alíneas).

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

## Testes

Não há dependências. Rode com Python 3.12 ou mais novo:

```
python -m unittest -v
```

## Licença

MIT.
