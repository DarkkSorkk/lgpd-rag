"""Junta as peças: busca, prompt, modelo e conferência.

Uso (mostra o que iria para o modelo, sem chamar nenhum):
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
from .contexto import Contexto
from .gemini import ErroDoModelo
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
        contexto: Contexto | None = None,
    ) -> None:
        self.busca = busca or Busca(lei, glossario=GLOSSARIO)
        self.contexto = contexto or Contexto(lei)
        self.modelo = modelo
        self.limiar = limiar

    def trechos(self, pergunta: str) -> tuple[Resposta, list[Dispositivo]]:
        """O que a busca achou, com quem está acima e as listas inteiras, na ordem da lei."""
        achado = self.busca.buscar(pergunta)
        return achado, self.contexto.trechos(r.dispositivo for r in achado.resultados)

    def preparar(self, pergunta: str) -> RespostaConferida | tuple[str, list[Dispositivo]]:
        """A recusa ou rejeição que acontece antes do modelo, ou a mensagem que iria para ele."""
        pergunta = pergunta.strip()
        if not pergunta:
            return rejeitada("pergunta vazia")
        if len(pergunta) > TAMANHO_MAXIMO_PERGUNTA:
            return rejeitada(f"pergunta com mais de {TAMANHO_MAXIMO_PERGUNTA} caracteres")
        achado, trechos = self.trechos(pergunta)
        if not trechos or achado.cobertura < self.limiar:
            return recusada("nenhuma palavra da pergunta aparece na lei")  # sem chamar o modelo
        return montar_mensagem(pergunta, trechos), trechos

    def perguntar(self, pergunta: str) -> RespostaConferida:
        """O que quem perguntou pode ver: só o que passou pela conferência."""
        return self.perguntar_para_revisao(pergunta)[0]

    def perguntar_para_revisao(self, pergunta: str) -> tuple[RespostaConferida, str | None]:
        """A resposta conferida e o texto do modelo, quando ele chegou a responder.

        O texto do modelo não passou pela conferência. Ele serve só para a revisão
        manual da avaliação e nunca vai para quem perguntou.
        """
        preparado = self.preparar(pergunta)
        if isinstance(preparado, RespostaConferida):
            return preparado, None
        mensagem, trechos = preparado
        encontrados = [d.rotulo for d in trechos]
        try:
            saida = self.modelo.responder(SISTEMA, mensagem)
        except ErroDoModelo as erro:  # mensagem já sem a chave
            return replace(rejeitada(f"erro ao chamar o modelo ({erro})"), encontrados=encontrados), None
        except Exception as erro:  # outro erro: só o tipo, para não vazar detalhe
            return replace(rejeitada(f"erro ao chamar o modelo ({type(erro).__name__})"), encontrados=encontrados), None
        return replace(conferir(saida, {d.id: d for d in trechos}), encontrados=encontrados), saida


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
    print("\nNenhum modelo foi chamado. A avaliação com o modelo de verdade é o lgpd_rag.avaliar_respostas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
