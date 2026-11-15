"""O modelo de linguagem, visto pelo resto do código: recebe a mensagem de sistema
e a do usuário e devolve texto. O modelo de verdade entra na etapa 4; os testes
usam o simulado, que não custa nada e não precisa de chave."""

from __future__ import annotations

from typing import Callable, Protocol

Saida = str | Callable[[str, str], str]


class Modelo(Protocol):
    def responder(self, sistema: str, mensagem: str) -> str: ...


class ModeloSimulado:
    """Devolve saídas prontas, na ordem (a última se repete), e guarda o que recebeu.

    Uma saída pode ser uma função (sistema, mensagem) -> texto, para simular um
    modelo que reage ao que leu, inclusive um que obedece a instrução escondida.
    """

    def __init__(self, *saidas: Saida) -> None:
        if not saidas:
            raise ValueError("passe pelo menos uma saída")
        self._saidas = list(saidas)
        self.chamadas: list[tuple[str, str]] = []

    def responder(self, sistema: str, mensagem: str) -> str:
        self.chamadas.append((sistema, mensagem))
        saida = self._saidas.pop(0) if len(self._saidas) > 1 else self._saidas[0]
        if isinstance(saida, Exception):
            raise saida
        return saida(sistema, mensagem) if callable(saida) else saida
