"""Busca por palavra (BM25) nos dispositivos da LGPD.

Cada dispositivo vigente é um documento. Inciso e alínea são pedaços de frase
("II - acesso aos dados;"), então levam junto o texto de quem está acima deles
(o caput diz do que se trata a lista).

Além do ranking, a busca mede quanto da pergunta a lei cobre: a soma do peso
(IDF) das palavras da pergunta que existem em algum dispositivo da lei, dividida
pela soma do peso de todas as palavras da pergunta. Palavra que a lei não tem
("IPVA", "ICMS") conta com o peso máximo. Cobertura baixa quer dizer que a lei
provavelmente não trata do assunto, e a pergunta nem chega ao modelo.

No gabarito de desenvolvimento, esse sinal separou melhor as perguntas fora da
LGPD do que a cobertura do melhor dispositivo: perguntas com palavras do dia a
dia ("teve um vazamento na minha empresa") têm muitas palavras soltas e cobrem
pouco do melhor dispositivo, mas quase todas as palavras delas existem na lei.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

from .lei import Dispositivo
from .texto import CORTE_PADRAO, palavras, sem_acento


@dataclass(frozen=True)
class Resultado:
    dispositivo: Dispositivo
    pontuacao: float


@dataclass(frozen=True)
class Resposta:
    resultados: list[Resultado]  # agrupados por artigo, na ordem do melhor artigo para o pior
    cobertura: float  # de 0 a 1: quanto do peso das palavras da pergunta existe na lei
    termos: list[str]  # radicais usados na busca, depois do glossário

    @property
    def artigos(self) -> list[str]:
        return list(dict.fromkeys(r.dispositivo.artigo for r in self.resultados))


class Busca:
    def __init__(
        self,
        dispositivos: Sequence[Dispositivo],
        glossario: Mapping[str, str] | None = None,
        corte: int | None = CORTE_PADRAO,
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        self.corte, self.k1, self.b = corte, k1, b
        # Expressões mais longas primeiro: "outro pais" antes de "pais".
        self.glossario = sorted(
            ((sem_acento(chave.lower()), valor) for chave, valor in (glossario or {}).items()),
            key=lambda par: -len(par[0]),
        )
        por_id = {d.id: d for d in dispositivos}
        self.vigentes = [d for d in dispositivos if d.situacao == "vigente"]
        self._docs: list[Counter[str]] = []
        for d in self.vigentes:
            partes = [d.texto]
            if d.tipo in ("inciso", "alinea"):
                pai = d.pai
                while pai:
                    partes.append(por_id[pai].texto)
                    pai = por_id[pai].pai
            self._docs.append(Counter(palavras(" ".join(partes), corte)))
        self._tamanhos = [sum(doc.values()) for doc in self._docs]
        self._media = sum(self._tamanhos) / len(self._tamanhos)
        frequencia = Counter(termo for doc in self._docs for termo in doc)
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in frequencia.items()}
        self._idf_maximo = math.log(1 + (n + 0.5) / 0.5)  # palavra que nenhum dispositivo tem

    def termos(self, pergunta: str) -> list[str]:
        """Radicais da pergunta, com as expressões do dia a dia trocadas pelas da lei."""
        texto = f" {sem_acento(pergunta.lower())} "
        for expressao, termo_da_lei in self.glossario:
            texto = texto.replace(f" {expressao} ", f" {termo_da_lei} ")
        # Pontuação colada ("DPO?") também conta como fim de palavra.
        for expressao, termo_da_lei in self.glossario:
            for sinal in "?.,;:!":
                texto = texto.replace(f" {expressao}{sinal}", f" {termo_da_lei}{sinal}")
        return list(dict.fromkeys(palavras(texto, self.corte)))

    def buscar(self, pergunta: str, artigos: int = 5, por_artigo: int = 3) -> Resposta:
        """Os `artigos` melhores artigos, com até `por_artigo` dispositivos de cada.

        Agrupar por artigo evita que um artigo com muitos incisos parecidos ocupe
        todas as posições e esconda o segundo artigo que também responde.
        """
        termos = self.termos(pergunta)
        pontos: list[tuple[float, int]] = []
        for i, doc in enumerate(self._docs):
            soma = 0.0
            normalizacao = self.k1 * (1 - self.b + self.b * self._tamanhos[i] / self._media)
            for termo in termos:
                f = doc.get(termo)
                if f:
                    soma += self._idf[termo] * f * (self.k1 + 1) / (f + normalizacao)
            if soma > 0:
                pontos.append((soma, i))
        pontos.sort(key=lambda par: (-par[0], par[1]))
        grupos: dict[str, list[Resultado]] = {}
        for p, i in pontos:
            d = self.vigentes[i]
            if d.artigo not in grupos and len(grupos) == artigos:
                continue
            grupo = grupos.setdefault(d.artigo, [])
            if len(grupo) < por_artigo:
                grupo.append(Resultado(d, p))
        resultados = [r for grupo in grupos.values() for r in grupo]
        return Resposta(resultados, self._cobertura(termos), termos)

    def _cobertura(self, termos: list[str]) -> float:
        if not termos:
            return 0.0
        peso = {t: self._idf.get(t, self._idf_maximo) for t in termos}
        return sum(p for t, p in peso.items() if t in self._idf) / sum(peso.values())
