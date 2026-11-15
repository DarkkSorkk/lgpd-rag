"""Mede a busca contra o gabarito.

Uso:
    python -m lgpd_rag.avaliar gabarito/desenvolvimento.jsonl
    python -m lgpd_rag.avaliar gabarito/teste.jsonl

O gabarito tem dois arquivos. O de desenvolvimento serve para ajustar a busca
(glossário, corte das palavras, limite de recusa). O de teste só é medido no fim,
sem ajuste depois, para mostrar quanto a busca acerta em perguntas que ela nunca viu.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from .busca import Busca
from .glossario import GLOSSARIO
from .lei import carregar

# A busca só recusa quando nenhuma palavra da pergunta existe na lei ("alíquota do
# ICMS"). Um limite mais alto foi testado: 0,28, o meio entre a maior cobertura de
# uma pergunta fora da LGPD (0,24) e a menor de uma que a lei responde (0,32) no
# gabarito de desenvolvimento. No gabarito de teste ele recusou 3 de 16 perguntas
# boas e deixou passar 3 de 4 de fora. Por isso a recusa fica com o modelo, que lê
# os dispositivos (etapa 3). Para repetir a medição: --limiar 0.28.
LIMIAR_PADRAO = 0.01


@dataclass(frozen=True)
class Pergunta:
    pergunta: str
    esperado: list[str]  # vazio: a LGPD não trata do assunto
    tipo: str  # "lei", "cotidiana" ou "fora"


def ler_gabarito(caminho: str | Path) -> list[Pergunta]:
    linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
    return [Pergunta(**json.loads(linha)) for linha in linhas if linha.strip()]


def cobre(esperado: str, obtido: str) -> bool:
    """O dispositivo obtido é o esperado ou está dentro dele (art18.V está dentro de art18)."""
    return obtido == esperado or obtido.startswith(esperado + ".")


def artigo_de(ident: str) -> str:
    return ident.split(".")[0]


@dataclass
class Medida:
    na_lei: int = 0
    artigo_no_1: int = 0
    artigo_nos_3: int = 0
    artigo_nos_5: int = 0
    dispositivo_nos_5: int = 0
    fora: int = 0
    fora_recusadas: int = 0
    na_lei_recusadas: int = 0

    def linhas(self) -> list[str]:
        pct = lambda a, b: f"{a}/{b} ({100 * a / b:.0f}%)" if b else "-"
        return [
            f"Perguntas que a lei responde: {self.na_lei}",
            f"  artigo certo em 1º lugar:          {pct(self.artigo_no_1, self.na_lei)}",
            f"  artigo certo entre os 3 primeiros: {pct(self.artigo_nos_3, self.na_lei)}",
            f"  artigo certo entre os 5 primeiros: {pct(self.artigo_nos_5, self.na_lei)}",
            f"  dispositivo certo entre os 5:      {pct(self.dispositivo_nos_5, self.na_lei)}",
            f"  recusadas por engano:              {pct(self.na_lei_recusadas, self.na_lei)}",
            f"Perguntas fora da LGPD: {self.fora}",
            f"  recusadas, como devia:             {pct(self.fora_recusadas, self.fora)}",
        ]


def avaliar(busca: Busca, perguntas: list[Pergunta], limiar: float = LIMIAR_PADRAO) -> tuple[Medida, list[str]]:
    medida, erros = Medida(), []
    for p in perguntas:
        resposta = busca.buscar(p.pergunta, artigos=5)
        recusou = resposta.cobertura < limiar
        ids = [r.dispositivo.id for r in resposta.resultados]
        artigos = ["art" + a for a in resposta.artigos]
        if not p.esperado:
            medida.fora += 1
            medida.fora_recusadas += recusou
            if not recusou:
                erros.append(f"[não recusou, cobertura {resposta.cobertura:.2f}] {p.pergunta} -> {artigos[:3]}")
            continue
        medida.na_lei += 1
        medida.na_lei_recusadas += recusou
        artigos_esperados = {artigo_de(e) for e in p.esperado}
        medida.artigo_no_1 += bool(artigos[:1] and artigos[0] in artigos_esperados)
        medida.artigo_nos_3 += any(a in artigos_esperados for a in artigos[:3])
        acertou_artigo = any(a in artigos_esperados for a in artigos[:5])
        medida.artigo_nos_5 += acertou_artigo
        medida.dispositivo_nos_5 += any(cobre(e, i) for e in p.esperado for i in ids)
        if not acertou_artigo or recusou:
            motivo = "recusou" if recusou else "errou o artigo"
            erros.append(
                f"[{motivo}, cobertura {resposta.cobertura:.2f}] {p.pergunta} "
                f"(esperado {p.esperado}) -> {artigos}"
            )
    return medida, erros


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mede a busca contra um arquivo do gabarito.")
    parser.add_argument("gabarito", type=Path)
    parser.add_argument("--dados", type=Path, default=Path("dados/lgpd.json"))
    parser.add_argument("--sem-glossario", action="store_true")
    parser.add_argument("--corte", type=int, default=None, help="tamanho do radical (padrão da busca)")
    parser.add_argument("--limiar", type=float, default=LIMIAR_PADRAO)
    args = parser.parse_args(argv)

    opcoes = {"glossario": None if args.sem_glossario else GLOSSARIO}
    if args.corte is not None:
        opcoes["corte"] = args.corte or None
    busca = Busca(carregar(args.dados), **opcoes)
    medida, erros = avaliar(busca, ler_gabarito(args.gabarito), args.limiar)
    print("\n".join(medida.linhas()))
    if erros:
        print("\nErros:")
        print("\n".join(f"  {e}" for e in erros))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
