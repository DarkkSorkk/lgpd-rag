"""Junta as peças: busca, prompt, modelo e conferência.

Uso (por enquanto, só mostra o que iria para o modelo):
    python -m lgpd_rag.perguntar "Preciso de um DPO?"
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .avaliar import LIMIAR_PADRAO
from .busca import Busca, Resposta
from .conferencia import RespostaConferida, conferir, recusada, rejeitada
from .glossario import GLOSSARIO
from .lei import Dispositivo, carregar
from .modelo import Modelo
from .prompt import SISTEMA, montar_mensagem

TAMANHO_MAXIMO_PERGUNTA = 500  # pergunta maior não chega ao modelo: custo e abuso


class Assistente:
    def __init__(
        self,
        lei: Sequence[Dispositivo],
        modelo: Modelo,
        busca: Busca | None = None,
        limiar: float = LIMIAR_PADRAO,
    ) -> None:
        self.por_id = {d.id: d for d in lei}
        self._ordem = {d.id: i for i, d in enumerate(lei)}
        self.busca = busca or Busca(lei, glossario=GLOSSARIO)
        self.modelo = modelo
        self.limiar = limiar

    def trechos(self, pergunta: str) -> tuple[Resposta, list[Dispositivo]]:
        """O que a busca achou, mais quem está acima (o caput de um inciso), na ordem da lei."""
        achado = self.busca.buscar(pergunta)
        ids: set[str] = set()
        for r in achado.resultados:
            atual: str | None = r.dispositivo.id
            while atual:
                ids.add(atual)
                atual = self.por_id[atual].pai
        return achado, sorted((self.por_id[i] for i in ids), key=lambda d: self._ordem[d.id])

    def perguntar(self, pergunta: str) -> RespostaConferida:
        pergunta = pergunta.strip()
        if not pergunta:
            return rejeitada("pergunta vazia")
        if len(pergunta) > TAMANHO_MAXIMO_PERGUNTA:
            return rejeitada(f"pergunta com mais de {TAMANHO_MAXIMO_PERGUNTA} caracteres")

        achado, trechos = self.trechos(pergunta)
        encontrados = [d.rotulo for d in trechos]
        if not trechos or achado.cobertura < self.limiar:
            return recusada("nenhuma palavra da pergunta aparece na lei")  # sem chamar o modelo

        try:
            saida = self.modelo.responder(SISTEMA, montar_mensagem(pergunta, trechos))
        except Exception as erro:  # rede, cota, chave: quem pergunta vê só que falhou
            return replace(rejeitada(f"erro ao chamar o modelo ({type(erro).__name__})"), encontrados=encontrados)
        return replace(conferir(saida, {d.id: d for d in trechos}), encontrados=encontrados)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mostra o que iria para o modelo para uma pergunta.")
    parser.add_argument("pergunta")
    parser.add_argument("--dados", type=Path, default=Path("dados/lgpd.json"))
    args = parser.parse_args(argv)

    assistente = Assistente(carregar(args.dados), modelo=None)  # type: ignore[arg-type]
    achado, trechos = assistente.trechos(args.pergunta)
    print(f"Cobertura da pergunta pela lei: {achado.cobertura:.2f}\n")
    print("=== mensagem de sistema ===")
    print(SISTEMA)
    print("\n=== mensagem do usuário ===")
    print(montar_mensagem(args.pergunta, trechos))
    print("\nO modelo de verdade entra na etapa 4.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
