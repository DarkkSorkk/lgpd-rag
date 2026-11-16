"""O que vai para o modelo: os dispositivos que a busca achou, mais o que é preciso para lê-los.

- **Quem está acima.** Inciso e alínea são pedaços de frase ("II - acesso aos dados;"),
  então vão com o caput ou o parágrafo de onde saem.
- **A lista inteira.** Quando a busca acha um item de lista (inciso ou alínea), ou o
  texto que abre a lista (o caput que termina em ":"), vão todos os itens dela. Sem
  isso, o modelo recebia parte da lista e respondia como se fosse toda. Na rodada de
  15/11/2026, recebeu 2 dos 3 casos do art. 43 e 1 das 7 hipóteses do art. 11, II.
- **Listas longas ficam como a busca achou.** Das 44 listas da lei, só duas passam
  de 15 itens: as 19 definições do art. 5º e as 24 competências da ANPD (art. 55-J).
  Mandá-las inteiras encareceria cada pergunta que toca nesses artigos, e uma
  definição chega sozinha pela busca. O limite começou em 12. No desenvolvimento,
  ele deixou de fora as 13 hipóteses de transferência internacional (art. 33), uma
  lista de regras como as outras, e por isso subiu para 15.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .lei import Dispositivo

LISTA_MAXIMA = 15
ITENS = ("inciso", "alinea")


class Contexto:
    def __init__(self, lei: Sequence[Dispositivo], lista_maxima: int = LISTA_MAXIMA) -> None:
        self.por_id = {d.id: d for d in lei}
        self._ordem = {d.id: i for i, d in enumerate(lei)}
        self._filhos: dict[str, list[Dispositivo]] = {}
        for d in lei:
            if d.pai:
                self._filhos.setdefault(d.pai, []).append(d)
        self.lista_maxima = lista_maxima  # 0: só quem está acima, sem completar listas

    def itens(self, ident: str) -> list[Dispositivo]:
        """Os itens em vigor da lista que `ident` abre, com as alíneas dos incisos, na ordem da lei."""
        saida: list[Dispositivo] = []
        for filho in self._filhos.get(ident, []):
            if filho.tipo in ITENS:
                if filho.situacao == "vigente":
                    saida.append(filho)
                saida.extend(self.itens(filho.id))
        return saida

    def lista_de(self, d: Dispositivo) -> str | None:
        """O dispositivo que abre a lista de que `d` faz parte, ou que `d` mesmo abre."""
        if d.tipo in ITENS and d.pai:
            return d.pai
        if d.id in self._filhos and self.itens(d.id):
            return d.id
        return None

    def trechos(self, achados: Iterable[Dispositivo]) -> list[Dispositivo]:
        ids: set[str] = set()
        for d in achados:
            ids.add(d.id)
            lista = self.lista_de(d) if self.lista_maxima else None
            if lista:
                itens = self.itens(lista)
                if len(itens) <= self.lista_maxima:
                    ids.update(i.id for i in itens)
        for ident in list(ids):
            acima = self.por_id[ident].pai
            while acima:
                ids.add(acima)
                acima = self.por_id[acima].pai
        return sorted((self.por_id[i] for i in ids), key=lambda d: self._ordem[d.id])
