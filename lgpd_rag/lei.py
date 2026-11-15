"""Lê o texto compilado da LGPD publicado pelo Planalto e o divide em dispositivos.

Cada dispositivo (caput, parágrafo, inciso ou alínea) vira uma unidade com um
identificador estável e o rótulo usado para citá-lo, como "Art. 7º, IX".

As notas que o Planalto põe no meio do texto ("Redação dada pela Lei nº ...",
"Incluído pela Lei nº ...", "Vigência") não fazem parte da lei e são retiradas.
Dispositivos revogados ou vetados continuam na lista, marcados como tal, para que
a busca os ignore sem perder a numeração.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

__all__ = ["Dispositivo", "carregar", "decodificar", "ler_html", "ler_linhas"]


@dataclass(frozen=True)
class Dispositivo:
    id: str  # "art7.IX", "art11.II.a", "art7.p3", "art1.pu"
    rotulo: str  # "Art. 7º, IX"
    artigo: str  # "7", "55-A"
    tipo: str  # "caput", "paragrafo", "inciso" ou "alinea"
    texto: str
    situacao: str  # "vigente", "revogado" ou "vetado"
    pai: str | None
    capitulo: str
    secao: str


# Texto de link que é nota do Planalto, não texto da lei. Compara o link inteiro:
# o Planalto também põe link em palavras da própria lei ("na forma do regulamento"),
# e essas ficam. "(Revogado)" e "(Revogado pela Lei nº ...)" são conteúdo: dizem que
# o dispositivo caiu. Ficam no texto, mesmo dentro de um link.
_NOTA_LINK = re.compile(
    r"^(?:\((?i:\s*(?:reda[çc][ãa]o dada|inclu[íi]d[oa]s? pel|vide\b|"
    r"promulga[çc][ãa]o|produ[çc][ãa]o de efeito|vig[êe]ncia|convers[ãa]o))[^()]*\)?"
    r"|Vig[êe]ncia|Regulamento|Mensagem de veto|Convers[ãa]o da Medida Provis[óo]ria[^()]*)$"
)
# A mesma nota quando aparece como texto comum, entre parênteses.
_NOTA_TEXTO = re.compile(
    r"\(\s*(?:reda[çc][ãa]o dada|inclu[íi]d[oa]s? pel|vide\b|"
    r"promulga[çc][ãa]o|produ[çc][ãa]o de efeito|vig[êe]ncia)[^()]*\)",
    re.IGNORECASE,
)
# "Vigência" solto no fim da linha (ou sozinho) é o texto de um link do Planalto.
# Maiúsculo de propósito: no texto da lei, "vigência" vem com minúscula.
_VIGENCIA_SOLTA = re.compile(r"(?:(?:^|\s+)Vig[êe]ncia)+\s*$")

_ORDINAL = r"(?:[º°]|o(?![a-zà-ú]))?"
_SUFIXO = r"(?:\s*-\s*([A-Z])(?![a-zà-ú]))?"
_ART = re.compile(rf"^Art\.\s*(\d+(?:\s+\d+)*)\s*{_ORDINAL}{_SUFIXO}\s*\.?\s*(.*)$")
_PARAGRAFO = re.compile(rf"^§\s*(\d+)\s*{_ORDINAL}{_SUFIXO}\s*\.?\s*(.*)$")
_PARAGRAFO_UNICO = re.compile(r"^Par[áa]grafo\s+[úu]nico\s*[.:]?\s*(.*)$", re.IGNORECASE)
_INCISO = re.compile(rf"^([IVXLC]+){_SUFIXO}\s*[-–—]\s*(.*)$")
_ALINEA = re.compile(r"^([a-z])\)\s*(.*)$")
_CAPITULO = re.compile(r"^CAP[ÍI]TULO\s+([IVXLC]+(?:-[A-Z])?)(?![A-Za-z])\s*[-–—]?\s*(.*)$")
_SECAO = re.compile(r"^(?:Se[çc][ãa]o|SE[ÇC][ÃA]O)\s+([IVXLC]+(?:-[A-Z])?)(?![A-Za-z])\s*[-–—]?\s*(.*)$")
_ROMANO = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_FIM = re.compile(r"^Bras[íi]lia\s*,")
_SO_PONTOS = re.compile(r"^[.…\s”\"]*$")
# "(Revogado).", "(revogado);" ou "(Revogado pela Lei nº 14.460, de 2022)", sozinhos
# ou no fim de um texto antigo que o Planalto deixou na página.
_REVOGADO = re.compile(r"(?:^|\s)\(\s*revogad[oa]s?\b[^()]*\)\s*[.;]?$", re.IGNORECASE)
_VETADO = re.compile(r"^\(?\s*vetad[oa]s?\s*\)?\s*[.;]?$", re.IGNORECASE)


def _espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.replace(" ", " ")).strip()


def _limpar(texto: str) -> str:
    texto = _NOTA_TEXTO.sub(" ", texto.replace(" ", " "))
    texto = _VIGENCIA_SOLTA.sub("", _espacos(texto))
    # O Planalto parte frases em vários <span>, o que deixa espaço antes da pontuação.
    return re.sub(r"\s+([,.;:])", r"\1", texto).strip()


class _Paragrafos(HTMLParser):
    """Junta o texto de cada <p>, sem o texto dos links que são notas do Planalto."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.linhas: list[str] = []
        self._p: list[str] | None = None
        self._link: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "p":
            self._fechar_p()
            self._p = []
        elif tag == "a" and self._p is not None:
            self._link = []
        elif tag == "br" and self._p is not None:
            self._p.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._link is not None and self._p is not None:
            texto = "".join(self._link)
            if not _NOTA_LINK.match(_espacos(texto)):
                self._p.append(texto)
            self._link = None
        elif tag == "p":
            self._fechar_p()

    def handle_data(self, data: str) -> None:
        if self._link is not None:
            self._link.append(data)
        elif self._p is not None:
            self._p.append(data)

    def _fechar_p(self) -> None:
        if self._p is not None:
            if self._link is not None:  # <a> sem </a> antes do fim do parágrafo
                self._p.append("".join(self._link))
            linha = _limpar("".join(self._p))
            if linha:
                self.linhas.append(linha)
        self._p = None
        self._link = None

    def close(self) -> None:
        super().close()
        self._fechar_p()


def decodificar(bruto: bytes) -> str:
    """A página do Planalto vem em windows-1252; uma cópia salva pode estar em UTF-8."""
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("cp1252")


def ler_html(html: str) -> list[Dispositivo]:
    leitor = _Paragrafos()
    leitor.feed(html)
    leitor.close()
    return ler_linhas(leitor.linhas)


def _numero(numero: int, sufixo: str | None) -> str:
    # De 1 a 9 o número leva "º" (Art. 7º, § 1º); de 10 em diante, não (Art. 10).
    texto = f"{numero}º" if numero < 10 else str(numero)
    return f"{texto}-{sufixo}" if sufixo else texto


def _situacao(texto: str) -> str:
    if _REVOGADO.search(texto):
        return "revogado"
    if _VETADO.match(texto):
        return "vetado"
    return "vigente"


def ler_linhas(linhas: Iterable[str]) -> list[Dispositivo]:
    """Monta os dispositivos a partir das linhas de texto da página, em ordem."""
    itens: list[dict] = []
    vistos: set[str] = set()
    capitulo = secao = ""
    titulo_pendente: str | None = None  # "capitulo" ou "secao" à espera do nome
    artigo: dict | None = None
    paragrafo: dict | None = None
    inciso: dict | None = None
    em_citacao = False

    def novo(ident: str, rotulo: str, tipo: str, texto: str, pai: str | None) -> dict:
        if ident in vistos:
            raise ValueError(f"Dispositivo repetido: {rotulo} ({ident})")
        vistos.add(ident)
        item = {
            "id": ident,
            "rotulo": rotulo,
            "artigo": artigo_atual,
            "tipo": tipo,
            "texto": texto,
            "situacao": _situacao(texto),
            "pai": pai,
            "capitulo": capitulo,
            "secao": secao,
        }
        itens.append(item)
        return item

    artigo_atual = ""
    for linha in linhas:
        linha = _limpar(linha)
        if not linha:
            continue
        if _FIM.match(linha):
            break

        # Texto de outra lei citado entre aspas (os arts. 60 e 61 alteram o Marco Civil
        # da Internet): não é dispositivo da LGPD e não pode virar um "Art. 7º" repetido.
        if em_citacao:
            if "(NR)" in linha or linha.endswith("”"):
                em_citacao = False
            continue
        if linha[0] in "“\"":
            em_citacao = "(NR)" not in linha and not linha.endswith("”")
            continue

        if m := _CAPITULO.match(linha):
            capitulo = f"CAPÍTULO {m[1]}" + (f" - {m[2]}" if m[2] else "")
            secao = ""
            titulo_pendente = None if m[2] else "capitulo"
            continue
        if m := _SECAO.match(linha):
            secao = f"Seção {m[1]}" + (f" - {m[2]}" if m[2] else "")
            titulo_pendente = None if m[2] else "secao"
            continue

        m_art = _ART.match(linha)
        m_inc = _INCISO.match(linha)
        if m_inc and not _ROMANO.match(m_inc[1]):
            m_inc = None
        e_dispositivo = bool(
            m_art or m_inc or _PARAGRAFO.match(linha) or _PARAGRAFO_UNICO.match(linha) or _ALINEA.match(linha)
        )
        if titulo_pendente and not e_dispositivo:
            nome = linha.strip("’‘'\" ")  # a página tem um apóstrofo perdido no título do Capítulo IX
            if titulo_pendente == "capitulo":
                capitulo = f"{capitulo} - {nome}"
            else:
                secao = f"{secao} - {nome}"
            titulo_pendente = None
            continue
        titulo_pendente = None

        if m_art:
            numero, sufixo, resto = int(m_art[1].replace(" ", "")), m_art[2], m_art[3]
            artigo_atual = f"{numero}-{sufixo}" if sufixo else str(numero)
            artigo = novo(f"art{artigo_atual}", f"Art. {_numero(numero, sufixo)}", "caput", resto, None)
            paragrafo = inciso = None
        elif artigo is None:
            continue  # cabeçalho, ementa e preâmbulo, antes do Art. 1º
        elif m := _PARAGRAFO.match(linha):
            numero, sufixo, resto = int(m[1]), m[2], m[3]
            ident = f"{artigo['id']}.p{numero}" + (f"-{sufixo}" if sufixo else "")
            paragrafo = novo(ident, f"{artigo['rotulo']}, § {_numero(numero, sufixo)}", "paragrafo", resto, artigo["id"])
            inciso = None
        elif m := _PARAGRAFO_UNICO.match(linha):
            paragrafo = novo(f"{artigo['id']}.pu", f"{artigo['rotulo']}, parágrafo único", "paragrafo", m[1], artigo["id"])
            inciso = None
        elif m_inc:
            base = paragrafo or artigo  # incisos depois de um parágrafo pertencem a ele
            nome = m_inc[1] + (f"-{m_inc[2]}" if m_inc[2] else "")
            inciso = novo(f"{base['id']}.{nome}", f"{base['rotulo']}, {nome}", "inciso", m_inc[3], base["id"])
        elif (m := _ALINEA.match(linha)) and inciso is not None:
            novo(f"{inciso['id']}.{m[1]}", f"{inciso['rotulo']}, {m[1]}", "alinea", m[2], inciso["id"])
        elif _SO_PONTOS.match(linha):
            continue
        else:
            # Continuação do dispositivo anterior, quando o Planalto o quebrou em dois <p>.
            ultimo = itens[-1]
            ultimo["texto"] = f"{ultimo['texto']} {linha}".strip()
            ultimo["situacao"] = _situacao(ultimo["texto"])

    return [Dispositivo(**item) for item in itens]


def carregar(caminho: str | Path) -> list[Dispositivo]:
    """Lê o dados/lgpd.json gerado por `python -m lgpd_rag.preparar`."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return [Dispositivo(**item) for item in dados["dispositivos"]]
