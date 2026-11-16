"""Avalia as respostas de ponta a ponta, com o modelo de verdade.

Uso:
    python -m lgpd_rag.avaliar_respostas gabarito/final.jsonl --estimar
    python -m lgpd_rag.avaliar_respostas gabarito/final.jsonl --confirmo-custo --teto-usd 0.50
    python -m lgpd_rag.avaliar_respostas gabarito/final.jsonl --confirmo-custo --vertex meu-projeto

Sem --vertex, usa o Google AI Studio e a chave GEMINI_API_KEY. Com --vertex,
usa o Vertex AI no projeto indicado, com o login do gcloud, sem chave nenhuma.

--estimar mostra quantas chamadas e quanto deve custar, sem chamar o modelo.
Para chamar de verdade, é preciso --confirmo-custo; a rodada para antes de
passar do teto. As respostas vão para resultados/<gabarito>.jsonl, para a
revisão manual contra o campo "nota" do gabarito. Quando a conferência barra
uma resposta, o arquivo também guarda o que o modelo escreveu (saida_modelo).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

from .avaliar import Pergunta, cobre, ler_gabarito
from .conferencia import RespostaConferida
from .gemini import ErroDoModelo, Gemini
from .lei import carregar
from .perguntar import Assistente
from .prompt import SISTEMA

# Preços em US$ por milhão de tokens. São os que a demo de contratos usou para o
# gemini-3.8-flash em 09/11/2026. Confira a página de preços do Gemini antes de rodar.
PRECO_ENTRADA = 0.75
PRECO_SAIDA = 3.75
# Para a estimativa: o português dá uns 4 caracteres por token; 3 deixa folga.
CARACTERES_POR_TOKEN = 3
SAIDA_ESTIMADA = 1000  # tokens por chamada, com o raciocínio
ERROS_SEGUIDOS_PARA_PARAR = 3  # chave errada não deve gerar 25 tentativas


@dataclass(frozen=True)
class Registro:
    pergunta: Pergunta
    resposta: RespostaConferida
    # O que o modelo escreveu, só quando a conferência barrou: sem isso, a revisão
    # não tem como saber se a resposta barrada estava certa.
    saida_modelo: str | None = None


def rodar(
    assistente: Assistente,
    perguntas: Sequence[Pergunta],
    custo_atual: Callable[[], float] = lambda: 0.0,
    teto_usd: float | None = None,
    avisar: Callable[[str], None] = print,
    registros: list[Registro] | None = None,
) -> list[Registro]:
    """`registros`: lista para ir guardando as respostas; quem chama a mantém se a rodada for interrompida."""
    registros = [] if registros is None else registros
    erros_seguidos = 0
    for n, p in enumerate(perguntas, 1):
        if teto_usd is not None and custo_atual() >= teto_usd:
            avisar(f"Teto de US$ {teto_usd:.2f} atingido: parando antes da pergunta {n}.")
            break
        resposta, saida = assistente.perguntar_para_revisao(p.pergunta)
        registros.append(Registro(p, resposta, saida if resposta.situacao == "rejeitada" else None))
        detalhe = f" ({resposta.motivo})" if resposta.situacao != "respondida" and resposta.motivo else ""
        avisar(f"[{n}/{len(perguntas)}] {resposta.situacao:10} {p.pergunta[:60]}{detalhe}")
        erros_seguidos = erros_seguidos + 1 if erro_do_modelo(resposta) else 0
        if erros_seguidos >= ERROS_SEGUIDOS_PARA_PARAR:
            avisar(
                f"Parando: {erros_seguidos} erros seguidos ao chamar o modelo. Se for HTTP 400 ou 404, "
                "confira a chave e o nome do modelo; se for 503 ou tempo esgotado, o serviço está "
                "sobrecarregado: tente mais tarde."
            )
            break
    return registros


def erro_do_modelo(resposta: RespostaConferida) -> bool:
    """A chamada falhou (chave, rede, cota): não é a conferência barrando uma resposta."""
    return resposta.situacao == "rejeitada" and (resposta.motivo or "").startswith("erro ao chamar o modelo")


def resumir(registros: Sequence[Registro]) -> list[str]:
    def contar(tipos: set[str]) -> dict[str, int]:
        grupo = [r for r in registros if r.pergunta.tipo in tipos]
        conta = {"total": len(grupo), "respondida": 0, "recusada": 0, "rejeitada": 0, "erro": 0, "citou_esperado": 0}
        for r in grupo:
            conta["erro" if erro_do_modelo(r.resposta) else r.resposta.situacao] += 1
            citados = [c.id for c in r.resposta.citacoes]
            if r.resposta.situacao == "respondida" and any(cobre(e, c) for e in r.pergunta.esperado for c in citados):
                conta["citou_esperado"] += 1
        return conta

    pct = lambda a, b: f"{a}/{b} ({100 * a / b:.0f}%)" if b else "-"
    linhas = []
    lei = contar({"lei", "cotidiana"})
    if lei["total"]:
        linhas += [
            f"Perguntas que a lei responde: {lei['total']}",
            f"  respondidas com citação conferida:  {pct(lei['respondida'], lei['total'])}",
            f"  citaram o dispositivo esperado:     {pct(lei['citou_esperado'], lei['total'])}",
            f"  recusadas (\"a lei não trata\"):      {pct(lei['recusada'], lei['total'])}",
            f"  barradas pela conferência:          {pct(lei['rejeitada'], lei['total'])}",
        ]
    fora = contar({"fora"})
    if fora["total"]:
        linhas += [
            f"Perguntas fora da LGPD: {fora['total']}",
            f"  recusadas, como devia:              {pct(fora['recusada'], fora['total'])}",
            f"  respondidas mesmo assim:            {pct(fora['respondida'], fora['total'])}",
            f"  barradas pela conferência:          {pct(fora['rejeitada'], fora['total'])}",
        ]
    ataques = contar({"ataque"})
    if ataques["total"]:
        linhas += [
            f"Ataques de prompt injection: {ataques['total']}",
            f"  recusados:                          {pct(ataques['recusada'], ataques['total'])}",
            f"  barrados pela conferência:          {pct(ataques['rejeitada'], ataques['total'])}",
            f"  respondidos com citação conferida:  {pct(ataques['respondida'], ataques['total'])} (revisar um a um)",
        ]
    erros = sum(1 for r in registros if erro_do_modelo(r.resposta))
    if erros:
        linhas.append(f"Falhas ao chamar o modelo (não contam como resposta): {erros}/{len(registros)}")
    return linhas


def estimar(assistente: Assistente, perguntas: Sequence[Pergunta], preco_entrada: float, preco_saida: float) -> dict:
    """Quantas chamadas e quanto deve custar, sem chamar o modelo."""
    chamadas = entrada = 0
    for p in perguntas:
        preparado = assistente.preparar(p.pergunta)
        if isinstance(preparado, RespostaConferida):
            continue  # recusada ou rejeitada antes do modelo
        chamadas += 1
        entrada += math.ceil((len(SISTEMA) + len(preparado[0])) / CARACTERES_POR_TOKEN)
    saida = chamadas * SAIDA_ESTIMADA
    return {
        "chamadas": chamadas,
        "tokens_entrada": entrada,
        "tokens_saida": saida,
        "custo_usd": (entrada * preco_entrada + saida * preco_saida) / 1e6,
    }


def salvar(registros: Sequence[Registro], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linhas = []
    for r in registros:
        dados = {**asdict(r.pergunta), **asdict(r.resposta)}
        if r.saida_modelo is not None:
            dados["saida_modelo"] = r.saida_modelo
        linhas.append(json.dumps(dados, ensure_ascii=False))
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avalia as respostas com o modelo de verdade.")
    parser.add_argument("gabarito", type=Path)
    parser.add_argument("--dados", type=Path, default=Path("dados/lgpd.json"))
    parser.add_argument("--estimar", action="store_true", help="só estima chamadas e custo, sem chamar o modelo")
    parser.add_argument("--confirmo-custo", action="store_true", help="chama o modelo de verdade (custa dinheiro)")
    parser.add_argument("--teto-usd", type=float, default=0.50, help="para antes de passar deste custo")
    parser.add_argument("--preco-entrada", type=float, default=PRECO_ENTRADA, help="US$ por milhão de tokens")
    parser.add_argument("--preco-saida", type=float, default=PRECO_SAIDA, help="US$ por milhão de tokens")
    parser.add_argument("--saida", type=Path, default=None, help="padrão: resultados/<gabarito>.jsonl")
    parser.add_argument("--vertex", metavar="PROJETO", help="usa o Vertex AI neste projeto, com o login do gcloud")
    parser.add_argument("--regiao", default="us", help="região do Vertex AI (padrão: us)")
    args = parser.parse_args(argv)

    lei = carregar(args.dados)
    perguntas = ler_gabarito(args.gabarito)

    if args.estimar:
        e = estimar(Assistente(lei, modelo=None), perguntas, args.preco_entrada, args.preco_saida)  # type: ignore[arg-type]
        print(
            f"{len(perguntas)} perguntas, {e['chamadas']} chamadas ao modelo. "
            f"Cerca de {e['tokens_entrada']} tokens de entrada e {e['tokens_saida']} de saída: "
            f"uns US$ {e['custo_usd']:.3f}, com preços de US$ {args.preco_entrada}/{args.preco_saida} por milhão."
        )
        return 0

    if not args.confirmo_custo:
        print("Esta avaliação chama o modelo e custa dinheiro. Rode antes com --estimar; "
              "para valer, acrescente --confirmo-custo.", file=sys.stderr)
        return 2
    try:
        gemini = Gemini(
            vertex_projeto=args.vertex, vertex_regiao=args.regiao, avisar=lambda texto: print(texto, flush=True)
        )
    except ErroDoModelo as erro:
        print(erro, file=sys.stderr)
        return 2
    print(f"Modelo: {gemini.descricao}", flush=True)

    def custo() -> float:
        return (gemini.uso.tokens_entrada * args.preco_entrada + gemini.uso.tokens_saida * args.preco_saida) / 1e6

    inicio = time.monotonic()
    registros: list[Registro] = []
    try:
        rodar(Assistente(lei, gemini), perguntas, custo, args.teto_usd, registros=registros)
    except KeyboardInterrupt:
        print("\nInterrompida: salvando o que já foi respondido.")
    saida = args.saida or Path("resultados") / f"{args.gabarito.stem}.jsonl"
    salvar(registros, saida)

    print()
    print("\n".join(resumir(registros)))
    print(
        f"\n{gemini.descricao}: {gemini.uso.chamadas} chamadas, {gemini.uso.tokens_entrada} tokens de entrada "
        f"e {gemini.uso.tokens_saida} de saída, US$ {custo():.4f}, {time.monotonic() - inicio:.0f} s."
    )
    print(f"Respostas salvas em {saida}, para a revisão manual.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
