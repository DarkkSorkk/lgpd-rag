"""Normalização de texto para a busca.

Tira acento e maiúscula, descarta palavras vazias ("de", "que", "posso"), passa a
palavra para o singular e corta no começo dela. O corte é um radical simples: junta
"consentimento" e "consentir", "eliminação" e "eliminar".
"""

from __future__ import annotations

import re
import unicodedata

CORTE_PADRAO = 6

PALAVRAS_VAZIAS = frozenset(
    """
    a ao aos aquela aquelas aquele aqueles aquilo as ate cada com como contra da das de dela delas
    dele deles depois desde do dos e ela elas ele eles em entre essa essas esse esses esta estao
    estas este estes eu foi ha isso isto ja la lhe lhes mais mas me mesmo meu meus minha minhas
    muito na nao nas nem no nos nossa nossas nosso nossos num numa o os ou para pela pelas pelo
    pelos por pode podem posso preciso precisa qual quais quando que quem sao se sem ser seu seus
    so sobre sua suas tambem te tem ter teu tua um uma umas uns voce voces vos deve devem
    """.split()
)


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def singular(palavra: str) -> str:
    """Plural regular do português para o singular. Não precisa acertar sempre: só
    precisa levar "sanção" e "sanções" para o mesmo lugar."""
    if len(palavra) <= 3 or not palavra.endswith("s"):
        return palavra
    for fim, troca in (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("ns", "m")):
        if palavra.endswith(fim):
            return palavra[: -len(fim)] + troca
    if palavra.endswith(("res", "zes", "ses")):
        return palavra[:-2]
    return palavra[:-1]


def palavras(texto: str, corte: int | None = CORTE_PADRAO) -> list[str]:
    """Texto -> lista de radicais, na ordem em que aparecem."""
    brutas = re.findall(r"[a-z0-9]+", sem_acento(texto.lower()))
    saida = []
    for palavra in brutas:
        if palavra in PALAVRAS_VAZIAS or len(palavra) < 2:
            continue
        palavra = singular(palavra)
        saida.append(palavra[:corte] if corte else palavra)
    return saida
