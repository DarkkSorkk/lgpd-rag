import json
import unittest
from pathlib import Path

from lgpd_rag.avaliar import avaliar, cobre, ler_gabarito
from lgpd_rag.busca import Busca
from lgpd_rag.glossario import GLOSSARIO
from lgpd_rag.lei import Dispositivo, carregar
from lgpd_rag.texto import palavras, sem_acento, singular

RAIZ = Path(__file__).resolve().parent.parent


def disp(ident, texto, tipo="caput", pai=None, situacao="vigente"):
    artigo = ident.split(".")[0].removeprefix("art")
    return Dispositivo(ident, ident, artigo, tipo, texto, situacao, pai, "", "")


class Texto(unittest.TestCase):
    def test_sem_acento(self):
        self.assertEqual(sem_acento("eliminação, sanções e órgão"), "eliminacao, sancoes e orgao")

    def test_singular(self):
        casos = {"sancoes": "sancao", "dados": "dado", "direitos": "direito", "jornais": "jornal",
                 "infracoes": "infracao", "titulares": "titular", "dado": "dado", "mes": "mes"}
        for plural, esperado in casos.items():
            self.assertEqual(singular(plural), esperado, plural)

    def test_palavras_tira_vazias_e_corta(self):
        self.assertEqual(palavras("Posso pedir a eliminação dos meus dados?"), ["pedir", "elimin", "dado"])
        self.assertEqual(palavras("consentimento", corte=None), ["consentimento"])
        self.assertEqual(palavras("consentimento"), palavras("consentir"))


class BuscaEmLeiPequena(unittest.TestCase):
    def setUp(self):
        self.lei = [
            disp("art1", "O controlador deverá indicar encarregado pelo tratamento de dados pessoais."),
            disp("art2", "O titular tem direito a obter do controlador, mediante requisição:"),
            disp("art2.I", "acesso aos dados;", "inciso", "art2"),
            disp("art2.II", "eliminação dos dados tratados com consentimento;", "inciso", "art2"),
            disp("art2.III", "portabilidade dos dados a outro fornecedor;", "inciso", "art2"),
            disp("art3", "O controlador deverá comunicar a ocorrência de incidente de segurança."),
            disp("art4", "(Revogado)", situacao="revogado"),
            disp("art5", "(VETADO).", situacao="vetado"),
        ]

    def test_acha_o_dispositivo(self):
        r = Busca(self.lei).buscar("Quem indica o encarregado?")
        self.assertEqual(r.resultados[0].dispositivo.id, "art1")

    def test_inciso_leva_o_texto_do_caput(self):
        # "titular" e "direito" só aparecem no caput, mas os incisos também respondem.
        ids = [x.dispositivo.id for x in Busca(self.lei).buscar("direitos do titular").resultados]
        self.assertIn("art2.II", ids)

    def test_agrupa_por_artigo(self):
        r = Busca(self.lei).buscar("dados do titular", artigos=1, por_artigo=2)
        self.assertEqual(r.artigos, ["2"])
        self.assertEqual(len(r.resultados), 2)

    def test_revogado_e_vetado_ficam_fora(self):
        busca = Busca(self.lei)
        self.assertEqual(busca.buscar("revogado").resultados, [])
        self.assertEqual(busca.buscar("vetado").resultados, [])

    def test_glossario_troca_palavra_do_dia_a_dia(self):
        sem = Busca(self.lei).buscar("Teve um vazamento, e agora?")
        com = Busca(self.lei, glossario={"vazamento": "incidente de segurança"}).buscar("Teve um vazamento, e agora?")
        self.assertNotIn("3", sem.artigos)
        self.assertEqual(com.artigos[0], "3")

    def test_glossario_com_pontuacao_colada(self):
        busca = Busca(self.lei, glossario={"dpo": "encarregado"})
        self.assertEqual(busca.buscar("Preciso de DPO?").artigos[0], "1")

    def test_cobertura(self):
        busca = Busca(self.lei)
        self.assertEqual(busca.buscar("alíquota do ICMS").cobertura, 0.0)
        self.assertEqual(busca.buscar("portabilidade dos dados").cobertura, 1.0)
        self.assertTrue(0 < busca.buscar("portabilidade do IPVA").cobertura < 1)


class Gabarito(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lei = {d.id: d for d in carregar(RAIZ / "dados" / "lgpd.json")}
        cls.desenvolvimento = ler_gabarito(RAIZ / "gabarito" / "desenvolvimento.jsonl")
        cls.teste = ler_gabarito(RAIZ / "gabarito" / "teste.jsonl")

    def test_respostas_esperadas_existem_e_estao_em_vigor(self):
        for p in self.desenvolvimento + self.teste:
            for ident in p.esperado:
                self.assertIn(ident, self.lei, p.pergunta)
                self.assertEqual(self.lei[ident].situacao, "vigente", p.pergunta)

    def test_tipos(self):
        for p in self.desenvolvimento + self.teste:
            self.assertIn(p.tipo, {"lei", "cotidiana", "fora"})
            self.assertEqual(p.tipo == "fora", not p.esperado, p.pergunta)

    def test_teste_nao_repete_desenvolvimento(self):
        a = {p.pergunta for p in self.desenvolvimento}
        b = {p.pergunta for p in self.teste}
        self.assertFalse(a & b)

    def test_cobre(self):
        self.assertTrue(cobre("art18", "art18.V"))
        self.assertTrue(cobre("art18.V", "art18.V"))
        self.assertFalse(cobre("art18.V", "art18"))
        self.assertFalse(cobre("art1", "art18"))

    def test_busca_nao_piora_no_desenvolvimento(self):
        # Trava contra regressão, só no conjunto de desenvolvimento.
        busca = Busca(list(self.lei.values()), glossario=GLOSSARIO)
        medida, _ = avaliar(busca, self.desenvolvimento)
        self.assertGreaterEqual(medida.artigo_nos_5, 28)
        self.assertGreaterEqual(medida.artigo_no_1, 19)
        self.assertEqual(medida.na_lei_recusadas, 0)

    def test_arquivos_sao_jsonl_valido(self):
        for nome in ("desenvolvimento.jsonl", "teste.jsonl"):
            for linha in (RAIZ / "gabarito" / nome).read_text(encoding="utf-8").splitlines():
                self.assertEqual(set(json.loads(linha)), {"pergunta", "esperado", "tipo"})


if __name__ == "__main__":
    unittest.main()
