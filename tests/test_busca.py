import json
import unittest
from pathlib import Path

from lgpd_rag.avaliar import Pergunta, avaliar, cobre, ler_gabarito
from lgpd_rag.busca import Busca
from lgpd_rag.contexto import Contexto
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

    def test_lista_inteira_nos_trechos(self):
        # A busca acha só um inciso; a medida só conta a resposta inteira com a lista toda.
        lei = self.lei + [disp("art9", "Não respondem quando provarem:"),
                          disp("art9.I", "que não trataram os dados;", "inciso", "art9"),
                          disp("art9.II", "que não houve violação;", "inciso", "art9"),
                          disp("art9.III", "que a culpa é exclusiva de terceiro.", "inciso", "art9")]
        busca = Busca(lei)
        perguntas = [Pergunta("culpa exclusiva de terceiro", ["art9"], "lei")]
        self.assertEqual([r.dispositivo.id for r in busca.buscar(perguntas[0].pergunta).resultados], ["art9.III"])
        sem, _ = avaliar(busca, perguntas, contexto=Contexto(lei, lista_maxima=0))
        com, _ = avaliar(busca, perguntas, contexto=Contexto(lei))
        self.assertEqual((sem.inteira_nos_trechos, com.inteira_nos_trechos), (0, 1))

    def test_cobertura(self):
        busca = Busca(self.lei)
        self.assertEqual(busca.buscar("alíquota do ICMS").cobertura, 0.0)
        self.assertEqual(busca.buscar("portabilidade dos dados").cobertura, 1.0)
        self.assertTrue(0 < busca.buscar("portabilidade do IPVA").cobertura < 1)


class Definicoes(unittest.TestCase):
    def setUp(self):
        # "titular" aparece em todo lugar e pesa pouco; a definição sozinha perderia no BM25.
        self.lei = [
            disp("art5", "Para os fins desta Lei, considera-se:"),
            disp("art5.I", "titular: pessoa natural a quem se referem os dados;", "inciso", "art5"),
            disp("art5.II", "dado anonimizado: dado que não identifica o titular;", "inciso", "art5"),
            disp("art5.III", "anonimização: meio pelo qual um dado perde a associação a um indivíduo;", "inciso", "art5"),
            disp("art5.IV", "encarregado: pessoa indicada pelo controlador;", "inciso", "art5"),
            disp("art6", "O titular pode pedir acesso. O titular pode pedir correção. Quem é o titular decide."),
            disp("art7", "O titular é informado sobre o dado anonimizado e o titular é ouvido."),
        ]

    def ids(self, busca, pergunta):
        return [r.dispositivo.id for r in busca.buscar(pergunta).resultados]

    def test_pergunta_de_conceito_vai_a_definicao(self):
        busca = Busca(self.lei)
        self.assertEqual(self.ids(busca, "Quem é o titular dos dados?")[0], "art5.I")
        self.assertEqual(self.ids(busca, "O que a lei chama de titular?")[0], "art5.I")

    def test_sem_o_atalho_a_definicao_perde(self):
        self.assertNotEqual(self.ids(Busca(self.lei, definicoes=False), "Quem é o titular dos dados?")[0], "art5.I")

    def test_so_pergunta_de_conceito(self):
        busca = Busca(self.lei)
        self.assertEqual(busca.definicoes_pedidas("O titular pode pedir acesso?"), [])
        self.assertEqual(busca.definicoes_pedidas("Quem é o titular?")[0].id, "art5.I")

    def test_expressao_mais_longa_ganha(self):
        # "anonimizado" e "anonimização" têm o mesmo radical.
        busca = Busca(self.lei)
        self.assertEqual([d.id for d in busca.definicoes_pedidas("O que é dado anonimizado?")], ["art5.II"])
        self.assertEqual([d.id for d in busca.definicoes_pedidas("O que é anonimização?")], ["art5.III"])

    def test_duas_definicoes_na_ordem_da_pergunta(self):
        busca = Busca(self.lei)
        pedidas = busca.definicoes_pedidas("Qual a diferença entre anonimização e titular?")
        self.assertEqual([d.id for d in pedidas], ["art5.III", "art5.I"])

    def test_glossario_vale_antes(self):
        busca = Busca(self.lei, glossario={"dpo": "encarregado"})
        self.assertEqual([d.id for d in busca.definicoes_pedidas("O que é um DPO?")], ["art5.IV"])


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
        self.assertGreaterEqual(medida.artigo_nos_5, 30)
        self.assertGreaterEqual(medida.artigo_no_1, 24)
        self.assertGreaterEqual(medida.inteira_nos_trechos, 30)
        self.assertEqual(medida.na_lei_recusadas, 0)

    def test_empresa_estrangeira_e_transferencia(self):
        # "Estrangeiro" leva ao art. 3º (a lei vale qualquer que seja o país da sede);
        # mandar dados para outro país continua levando ao art. 33.
        busca = Busca(list(self.lei.values()), glossario=GLOSSARIO)
        self.assertEqual(busca.buscar("Uma empresa estrangeira precisa seguir a LGPD?").artigos[0], "3")
        self.assertEqual(busca.buscar("Posso mandar dados de clientes para outro país?").artigos[0], "33")
        self.assertIn("3", busca.buscar("A LGPD vale para sites de fora do Brasil usados por brasileiros?").artigos)

    def test_sem_os_ajustes_volta_ao_que_era(self):
        # As opções --sem-definicoes e --sem-listas reproduzem a busca da etapa 4.
        lei = list(self.lei.values())
        busca = Busca(lei, glossario=GLOSSARIO, definicoes=False)
        medida, _ = avaliar(busca, self.desenvolvimento, contexto=Contexto(lei, lista_maxima=0))
        self.assertEqual(medida.artigo_no_1, 21)
        self.assertEqual(medida.inteira_nos_trechos, 17)

    def test_arquivos_sao_jsonl_valido(self):
        for nome in ("desenvolvimento.jsonl", "teste.jsonl"):
            for linha in (RAIZ / "gabarito" / nome).read_text(encoding="utf-8").splitlines():
                self.assertEqual(set(json.loads(linha)), {"pergunta", "esperado", "tipo"})


if __name__ == "__main__":
    unittest.main()
