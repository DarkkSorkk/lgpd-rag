import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from lgpd_rag.avaliar import Pergunta, ler_gabarito
from lgpd_rag.avaliar_respostas import Registro, estimar, main, resumir, rodar, salvar
from lgpd_rag.conferencia import Citacao, RespostaConferida, recusada, rejeitada
from lgpd_rag.gemini import ErroDoModelo
from lgpd_rag.lei import carregar
from lgpd_rag.modelo import ModeloSimulado
from lgpd_rag.perguntar import Assistente

RAIZ = Path(__file__).resolve().parent.parent
LEI = carregar(RAIZ / "dados" / "lgpd.json")
DPO = json.dumps({
    "fora_da_lei": False,
    "resposta": "Sim, o controlador deve indicar um encarregado.",
    "citacoes": [{"id": "art41", "trecho": "O controlador deverá indicar encarregado"}],
})


def respondida(*ids):
    return RespostaConferida("respondida", "texto", [Citacao(i, i, "trecho") for i in ids])


class Resumo(unittest.TestCase):
    def test_conta_cada_situacao(self):
        registros = [
            Registro(Pergunta("a", ["art41"], "lei"), respondida("art41")),
            Registro(Pergunta("b", ["art18"], "cotidiana"), respondida("art18.V")),  # dentro do esperado
            Registro(Pergunta("c", ["art7"], "lei"), respondida("art8")),  # respondeu, citou outro
            Registro(Pergunta("d", ["art7"], "lei"), rejeitada("x")),
            Registro(Pergunta("e", [], "fora"), recusada("x")),
            Registro(Pergunta("f", [], "fora"), respondida("art1")),
            Registro(Pergunta("g", [], "ataque"), rejeitada("x")),
        ]
        texto = "\n".join(resumir(registros))
        self.assertIn("respondidas com citação conferida:  3/4 (75%)", texto)
        self.assertIn("citaram o dispositivo esperado:     2/4 (50%)", texto)
        self.assertIn("barradas pela conferência:          1/4 (25%)", texto)
        self.assertIn("recusadas, como devia:              1/2 (50%)", texto)
        self.assertIn("respondidas mesmo assim:            1/2 (50%)", texto)
        self.assertIn("barrados pela conferência:          1/1 (100%)", texto)


class Rodada(unittest.TestCase):
    def test_para_no_teto_de_custo(self):
        perguntas = [Pergunta("Minha empresa precisa ter um DPO?", ["art41"], "cotidiana")] * 5
        modelo = ModeloSimulado(DPO)
        gasto = iter([0.0, 0.1, 0.2, 0.3, 0.4])
        avisos = []
        registros = rodar(Assistente(LEI, modelo), perguntas, lambda: next(gasto), teto_usd=0.25, avisar=avisos.append)
        self.assertEqual(len(registros), 3)
        self.assertEqual(len(modelo.chamadas), 3)
        self.assertIn("Teto de US$ 0.25 atingido", avisos[-1])

    def test_para_depois_de_tres_erros_seguidos_do_modelo(self):
        # Foi o que aconteceu na primeira rodada: chave inválida, 25 perguntas, 25 erros.
        perguntas = [Pergunta("Minha empresa precisa ter um DPO?", ["art41"], "cotidiana")] * 10
        modelo = ModeloSimulado(ErroDoModelo("HTTP 400: API key not valid."))
        avisos = []
        registros = rodar(Assistente(LEI, modelo), perguntas, avisar=avisos.append)
        self.assertEqual(len(registros), 3)
        self.assertIn("HTTP 400", avisos[0])
        self.assertIn("3 erros seguidos", avisos[-1])
        self.assertIn("Falhas ao chamar o modelo (não contam como resposta): 3/3", "\n".join(resumir(registros)))
        self.assertIn("barradas pela conferência:          0/3", "\n".join(resumir(registros)))

    def test_guarda_na_lista_de_quem_chamou(self):
        # Se a rodada for interrompida (Ctrl+C), quem chamou ainda tem o que já foi respondido.
        guardados = []

        def interrompe(_sistema, _mensagem):
            if guardados:
                raise KeyboardInterrupt
            return DPO

        perguntas = [Pergunta("Minha empresa precisa ter um DPO?", ["art41"], "cotidiana")] * 3
        with self.assertRaises(KeyboardInterrupt):
            rodar(Assistente(LEI, ModeloSimulado(interrompe)), perguntas, avisar=lambda _: None, registros=guardados)
        self.assertEqual(len(guardados), 1)

    def test_erro_isolado_nao_para_a_rodada(self):
        perguntas = [Pergunta("Minha empresa precisa ter um DPO?", ["art41"], "cotidiana")] * 4
        modelo = ModeloSimulado(ErroDoModelo("HTTP 503"), DPO, ErroDoModelo("HTTP 503"), DPO)
        self.assertEqual(len(rodar(Assistente(LEI, modelo), perguntas, avisar=lambda _: None)), 4)

    def test_estimar_nao_chama_o_modelo(self):
        perguntas = [
            Pergunta("Minha empresa precisa ter um DPO?", ["art41"], "cotidiana"),
            Pergunta("Qual é a alíquota do ICMS em São Paulo?", [], "fora"),  # a busca recusa antes
        ]
        e = estimar(Assistente(LEI, modelo=None), perguntas, 0.75, 3.75)
        self.assertEqual(e["chamadas"], 1)
        self.assertGreater(e["tokens_entrada"], 500)
        self.assertGreater(e["custo_usd"], 0)

    def test_salvar(self):
        registros = [Registro(Pergunta("a", ["art41"], "lei", "nota"), respondida("art41"))]
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "r" / "x.jsonl"
            salvar(registros, caminho)
            linha = json.loads(caminho.read_text(encoding="utf-8"))
        self.assertEqual(linha["pergunta"], "a")
        self.assertEqual(linha["situacao"], "respondida")
        self.assertEqual(linha["citacoes"][0]["id"], "art41")

    def test_sem_confirmar_o_custo_nao_roda(self):
        erro = io.StringIO()
        with redirect_stderr(erro):
            codigo = main([str(RAIZ / "gabarito" / "final.jsonl"), "--dados", str(RAIZ / "dados" / "lgpd.json")])
        self.assertEqual(codigo, 2)
        self.assertIn("--confirmo-custo", erro.getvalue())


class GabaritosNovos(unittest.TestCase):
    def test_final_e_ataques_sao_validos_e_ineditos(self):
        lei = {d.id: d for d in LEI}
        antigos = {p.pergunta for nome in ("desenvolvimento", "teste") for p in ler_gabarito(RAIZ / "gabarito" / f"{nome}.jsonl")}
        for nome, tipos in (("final", {"lei", "cotidiana", "fora"}), ("ataques", {"ataque"})):
            for p in ler_gabarito(RAIZ / "gabarito" / f"{nome}.jsonl"):
                self.assertIn(p.tipo, tipos)
                self.assertNotIn(p.pergunta, antigos)
                self.assertTrue(p.nota, p.pergunta)
                for ident in p.esperado:
                    self.assertEqual(lei[ident].situacao, "vigente", p.pergunta)


if __name__ == "__main__":
    unittest.main()
