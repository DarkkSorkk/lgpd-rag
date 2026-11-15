"""Conferências do dados/lgpd.json gerado a partir da página oficial.

Pegam erro do leitor que o recorte de test_lei.py não mostra: artigo faltando,
dispositivo repetido, nota do Planalto que sobrou no texto.
"""

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

from lgpd_rag.lei import carregar, decodificar

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "dados" / "lgpd.json"
# A página salva do Planalto não vai para o repositório (veja o README).
PAGINA = next(iter(sorted((RAIZ / "fonte").glob("l13709compilado.htm*"))), None)


@unittest.skipUnless(ARQUIVO.exists(), "dados/lgpd.json ainda não foi gerado")
class DadosDaLgpd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cabecalho = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        cls.lista = carregar(ARQUIVO)
        cls.por_id = {d.id: d for d in cls.lista}

    def test_todos_os_artigos_de_1_a_65(self):
        numeros = {int(d.artigo.split("-")[0]) for d in self.lista}
        self.assertEqual(numeros, set(range(1, 66)))

    def test_artigos_da_anpd(self):
        for letra in "ABCDEFGHIJKL":
            self.assertIn(f"art55-{letra}", self.por_id)

    def test_ids_unicos(self):
        self.assertEqual(len(self.por_id), len(self.lista))

    def test_sem_notas_do_planalto(self):
        for d in self.lista:
            for nota in ("Redação dada", "Incluído pela", "Incluída pela", "Vigência", "(NR)"):
                self.assertNotIn(nota, d.texto, d.id)

    def test_hipoteses_de_tratamento_do_art_7(self):
        for inciso in ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]:
            self.assertIn(f"art7.{inciso}", self.por_id)

    def test_direitos_do_titular_do_art_18(self):
        for inciso in ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"]:
            self.assertIn(f"art18.{inciso}", self.por_id)

    def test_art_57_vetado(self):
        self.assertEqual(self.por_id["art57"].situacao, "vetado")

    def test_texto_do_marco_civil_fica_de_fora(self):
        self.assertFalse(any("exclusão definitiva" in d.texto for d in self.lista))

    def test_pais_existem_e_combinam(self):
        tipos_do_pai = {"paragrafo": {"caput"}, "inciso": {"caput", "paragrafo"}, "alinea": {"inciso"}}
        for d in self.lista:
            if d.tipo == "caput":
                self.assertIsNone(d.pai)
            else:
                self.assertIn(self.por_id[d.pai].tipo, tipos_do_pai[d.tipo], d.id)

    def test_vigentes_tem_texto(self):
        for d in self.lista:
            if d.situacao == "vigente":
                self.assertGreater(len(d.texto), 3, d.id)

    def test_cabecalho(self):
        self.assertEqual(len(self.cabecalho["sha256_da_pagina"]), 64)
        self.assertTrue(self.cabecalho["fonte"].startswith("https://www.planalto.gov.br/"))


class _TextoCorrido(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []

    def handle_data(self, data):
        self.partes.append(data)


def _normalizar(texto):
    texto = re.sub(r"\s+", " ", texto.replace(" ", " "))
    return re.sub(r"\s+([,.;:])", r"\1", texto).strip()


@unittest.skipUnless(ARQUIVO.exists() and PAGINA, "precisa do dados/lgpd.json e da página salva em fonte/")
class TextoIgualAoDaPagina(unittest.TestCase):
    def test_cada_dispositivo_aparece_igual_na_pagina(self):
        # Lê a página de outro jeito (todo o texto, sem olhar <p> nem links) e procura
        # cada dispositivo nela: o leitor não pode ter perdido nem trocado palavra.
        leitor = _TextoCorrido()
        leitor.feed(decodificar(PAGINA.read_bytes()))
        leitor.close()
        pagina = _normalizar(" ".join(leitor.partes))
        for d in carregar(ARQUIVO):
            self.assertIn(_normalizar(d.texto), pagina, d.rotulo)


if __name__ == "__main__":
    unittest.main()
