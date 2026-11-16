"""Testes do que vai para o modelo, com o texto real da lei."""

import unittest
from pathlib import Path

from lgpd_rag.contexto import LISTA_MAXIMA, Contexto
from lgpd_rag.lei import carregar
from lgpd_rag.modelo import ModeloSimulado
from lgpd_rag.perguntar import Assistente

RAIZ = Path(__file__).resolve().parent.parent
LEI = carregar(RAIZ / "dados" / "lgpd.json")
POR_ID = {d.id: d for d in LEI}


def enviados(*achados, **opcoes):
    return [d.id for d in Contexto(LEI, **opcoes).trechos(POR_ID[i] for i in achados)]


class ListaInteira(unittest.TestCase):
    def test_inciso_leva_a_lista_toda(self):
        # Na rodada de 15/11/2026, só o I e o III chegaram ao modelo.
        self.assertEqual(enviados("art43.I", "art43.III"), ["art43", "art43.I", "art43.II", "art43.III"])

    def test_caput_que_abre_lista_leva_os_itens_e_as_alineas(self):
        ids = enviados("art4")
        for i in ("art4.I", "art4.II", "art4.II.a", "art4.II.b", "art4.III", "art4.III.d", "art4.IV"):
            self.assertIn(i, ids)
        self.assertNotIn("art4.p1", ids)  # parágrafo não é item da lista

    def test_alinea_leva_as_alineas_do_inciso(self):
        ids = enviados("art11.II.c")
        self.assertEqual([i for i in ids if i.startswith("art11.II.")], [f"art11.II.{x}" for x in "abcdefg"])
        self.assertIn("art11", ids)  # quem está acima continua indo
        self.assertNotIn("art11.I", ids)  # a lista é a do inciso II, não a do caput

    def test_vetado_fica_de_fora(self):
        ids = enviados("art26.p1.III")
        self.assertEqual([i for i in ids if i.startswith("art26.p1.")], ["art26.p1.I", "art26.p1.III", "art26.p1.IV", "art26.p1.V"])

    def test_lista_longa_fica_como_a_busca_achou(self):
        self.assertEqual(enviados("art5.V"), ["art5", "art5.V"])  # 19 definições
        self.assertEqual(enviados("art55-J.IV"), ["art55-J", "art55-J.IV"])  # 24 competências
        self.assertLess(LISTA_MAXIMA, 19)

    def test_lista_de_transferencia_internacional_cabe(self):
        self.assertEqual(len([i for i in enviados("art33.I") if i.startswith("art33.")]), 13)

    def test_sem_lista_volta_ao_que_era(self):
        self.assertEqual(enviados("art43.I", "art43.III", lista_maxima=0), ["art43", "art43.I", "art43.III"])

    def test_paragrafo_sem_lista(self):
        self.assertEqual(enviados("art8.p2"), ["art8", "art8.p2"])

    def test_ordem_da_lei_sem_repeticao(self):
        ids = enviados("art18.VI", "art7.I", "art18.IV")
        self.assertEqual(len(ids), len(set(ids)))
        ordem = {d.id: n for n, d in enumerate(LEI)}
        self.assertEqual(ids, sorted(ids, key=ordem.get))


class Assistente_(unittest.TestCase):
    def test_pergunta_de_lista_manda_a_lista_toda(self):
        _, trechos = Assistente(LEI, ModeloSimulado("{}")).trechos("Em quais casos os agentes de tratamento não são responsabilizados?")
        self.assertIn("art43.II", [d.id for d in trechos])

    def test_pergunta_de_conceito_manda_a_definicao(self):
        _, trechos = Assistente(LEI, ModeloSimulado("{}")).trechos("Quem é o titular dos dados?")
        self.assertIn("art5.V", [d.id for d in trechos])


if __name__ == "__main__":
    unittest.main()
