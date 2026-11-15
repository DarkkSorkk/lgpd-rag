"""Gera dados/lgpd.json a partir da página oficial da LGPD, salva do site do Planalto.

Uso:
    python -m lgpd_rag.preparar fonte/l13709compilado.html

O site do Planalto não aceita download automático, então a página é salva pelo
navegador (veja o README). O arquivo gerado guarda o SHA-256 da página, para que
qualquer pessoa confira se partiu da mesma versão do texto.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .lei import decodificar, ler_html

FONTE_OFICIAL = "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Divide o texto oficial da LGPD em dispositivos.")
    parser.add_argument("html", type=Path, help="página da LGPD salva do Planalto")
    parser.add_argument("saida", type=Path, nargs="?", default=Path("dados/lgpd.json"))
    parser.add_argument("--data", default=date.today().isoformat(), help="dia em que a página foi salva (AAAA-MM-DD)")
    args = parser.parse_args(argv)

    bruto = args.html.read_bytes()
    dispositivos = ler_html(decodificar(bruto))
    if not dispositivos:
        print("Nenhum dispositivo encontrado. A página salva é mesmo a da LGPD?", file=sys.stderr)
        return 1

    cabecalho = {
        "lei": "Lei nº 13.709, de 14 de agosto de 2018 (LGPD), texto compilado",
        "fonte": FONTE_OFICIAL,
        "salva_em": args.data,
        "sha256_da_pagina": hashlib.sha256(bruto).hexdigest(),
    }
    # Um dispositivo por linha: o diff de uma mudança na lei mostra só o que mudou.
    linhas = ["{"]
    linhas += [f"  {json.dumps(chave)}: {json.dumps(valor, ensure_ascii=False)}," for chave, valor in cabecalho.items()]
    linhas.append('  "dispositivos": [')
    linhas.append(",\n".join("    " + json.dumps(asdict(d), ensure_ascii=False) for d in dispositivos))
    linhas += ["  ]", "}"]
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")

    situacoes = Counter(d.situacao for d in dispositivos)
    artigos = len({d.artigo for d in dispositivos})
    resumo = ", ".join(f"{n} {s}" for s, n in situacoes.most_common())
    print(f"{args.saida}: {len(dispositivos)} dispositivos em {artigos} artigos ({resumo})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
