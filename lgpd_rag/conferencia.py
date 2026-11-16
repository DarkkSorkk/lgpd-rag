"""Confere a saída do modelo antes de mostrar qualquer coisa.

Uma resposta só passa se:
- a saída for um objeto JSON no formato pedido;
- tiver pelo menos uma citação;
- cada citação apontar para um dispositivo que foi enviado ao modelo;
- o trecho citado aparecer, letra por letra, no texto desse dispositivo;
- o trecho tiver pelo menos 15 caracteres, ou for o dispositivo inteiro
  (há incisos mais curtos, como "a reincidência;");
- a resposta só mencionar artigos que foram citados (ou que aparecem no texto
  dos dispositivos citados, como "exceto nas hipóteses previstas no art. 16").

Se o modelo disser que a lei não trata do assunto, o texto mostrado é uma frase
fixa do código, não o que o modelo escreveu. Nada que o modelo produza chega a
quem perguntou sem passar por aqui.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Mapping

from .lei import Dispositivo

RECUSA = "A LGPD não trata disso, pelo menos nos trechos que a busca encontrou."
REJEICAO = "Não consegui uma resposta com citação conferida na lei."
TAMANHO_MAXIMO_RESPOSTA = 1500
TRECHO_MINIMO = 15  # caracteres; "dados pessoais" sozinho não prova nada


@dataclass(frozen=True)
class Citacao:
    id: str
    rotulo: str
    trecho: str


@dataclass(frozen=True)
class RespostaConferida:
    situacao: str  # "respondida", "recusada" ou "rejeitada"
    texto: str
    citacoes: list[Citacao] = field(default_factory=list)
    motivo: str | None = None  # por que foi recusada ou rejeitada
    encontrados: list[str] = field(default_factory=list)  # rótulos que a busca achou


def recusada(motivo: str) -> RespostaConferida:
    return RespostaConferida("recusada", RECUSA, motivo=motivo)


def rejeitada(motivo: str) -> RespostaConferida:
    return RespostaConferida("rejeitada", REJEICAO, motivo=motivo)


def normalizar(texto: str) -> str:
    """Compara sem ligar para espaço, maiúscula, aspas curvas e pontuação nas pontas."""
    for de, para in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"), ("–", "-"), ("—", "-")):
        texto = texto.replace(de, para)
    return re.sub(r"\s+", " ", texto).strip().lower().strip(" .;:,")


_MENCAO = re.compile(
    r"\b(?:arts?\.|artigos?)\s*((?:\d+(?:-[A-Z])?\s*[º°]?\s*(?:,|\be\b)?\s*)*\d+(?:-[A-Z])?)",
    re.IGNORECASE,
)


def artigos_mencionados(texto: str) -> set[str]:
    """{"7", "11"} para "conforme os arts. 7º e 11"."""
    numeros: set[str] = set()
    for m in _MENCAO.finditer(texto):
        numeros.update(n.upper() for n in re.findall(r"\d+(?:-[A-Za-z])?", m.group(1)))
    return numeros


def _ler_json(saida: str) -> dict | None:
    texto = saida.strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fim < inicio:
        return None
    try:
        dados = json.loads(texto[inicio : fim + 1])
    except json.JSONDecodeError:
        return None
    return dados if isinstance(dados, dict) else None


def conferir(saida: str, enviados: Mapping[str, Dispositivo]) -> RespostaConferida:
    """`enviados`: os dispositivos que foram ao modelo, por id."""
    dados = _ler_json(saida)
    if dados is None:
        return rejeitada("a saída do modelo não é um objeto JSON")

    fora = dados.get("fora_da_lei", False)
    if not isinstance(fora, bool):
        return rejeitada("fora_da_lei não é verdadeiro nem falso")
    if fora:
        return recusada("o modelo disse que os trechos não respondem à pergunta")

    resposta = dados.get("resposta")
    if not isinstance(resposta, str) or not resposta.strip():
        return rejeitada("resposta vazia")
    if len(resposta) > TAMANHO_MAXIMO_RESPOSTA:
        return rejeitada("resposta longa demais")

    brutas = dados.get("citacoes")
    if not isinstance(brutas, list):
        return rejeitada("citacoes não é uma lista")
    if not brutas:
        return rejeitada("resposta sem citação")

    citacoes: list[Citacao] = []
    for item in brutas:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("trecho"), str):
            return rejeitada("citação sem id ou sem trecho")
        ident, trecho = item["id"].strip(), item["trecho"].strip()
        dispositivo = enviados.get(ident)
        if dispositivo is None:
            return rejeitada(f"citou {ident}, que não estava nos trechos enviados")
        if "..." in trecho or "…" in trecho:
            return rejeitada(f"o trecho citado do {dispositivo.rotulo} tem reticências")
        # Dispositivo mais curto que o mínimo só passa citado inteiro.
        if len(normalizar(trecho)) < min(TRECHO_MINIMO, len(normalizar(dispositivo.texto))):
            return rejeitada(f"o trecho citado do {dispositivo.rotulo} é curto demais")
        if normalizar(trecho) not in normalizar(dispositivo.texto):
            return rejeitada(f"o trecho citado não está no {dispositivo.rotulo}")
        if all(c.id != ident or normalizar(c.trecho) != normalizar(trecho) for c in citacoes):
            citacoes.append(Citacao(ident, dispositivo.rotulo, trecho))

    permitidos = {enviados[c.id].artigo.upper() for c in citacoes}
    for c in citacoes:
        permitidos |= artigos_mencionados(enviados[c.id].texto)
    sobrando = sorted(artigos_mencionados(resposta) - permitidos)
    if sobrando:
        return rejeitada(f"a resposta menciona o art. {sobrando[0]}, que não foi citado")

    return RespostaConferida("respondida", resposta.strip(), citacoes)
