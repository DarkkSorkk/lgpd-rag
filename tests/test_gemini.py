"""Testes do cliente do Gemini, sem rede e sem chave: a função que abre a conexão é falsa."""

import io
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

from lgpd_rag.gemini import ENDERECO, ErroDoModelo, Gemini, endereco_vertex, token_do_login_do_gcloud

CHAVE = "chave-de-teste-123456"


class Resposta:
    def __init__(self, dados):
        self._bytes = json.dumps(dados).encode("utf-8")

    def read(self):
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        return False


def ok(texto='{"fora_da_lei": true}', entrada=100, saida=20, raciocinio=30, partes=None):
    return Resposta({
        "candidates": [{"content": {"parts": partes or [{"text": texto}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": entrada, "candidatesTokenCount": saida, "thoughtsTokenCount": raciocinio},
    })


def erro_http(codigo, mensagem="falhou"):
    corpo = io.BytesIO(json.dumps({"error": {"message": mensagem}}).encode("utf-8"))
    return urllib.error.HTTPError("https://exemplo.invalid", codigo, "erro", {}, corpo)


class Abridor:
    """Faz o papel de urllib.request.urlopen: devolve (ou levanta) o que recebeu, na ordem."""

    def __init__(self, *saidas):
        self.saidas = list(saidas)
        self.pedidos = []

    def __call__(self, pedido, timeout):
        self.pedidos.append(pedido)
        saida = self.saidas.pop(0)
        if isinstance(saida, Exception):
            raise saida
        return saida


def cliente(*saidas, **opcoes):
    abridor = Abridor(*saidas)
    esperas = []
    g = Gemini(chave=CHAVE, modelo="modelo-x", abrir=abridor, dormir=esperas.append, **opcoes)
    return g, abridor, esperas


class Pedido(unittest.TestCase):
    def test_chave_no_cabecalho_e_nunca_na_url(self):
        g, abridor, _ = cliente(ok())
        g.responder("sistema", "mensagem")
        pedido = abridor.pedidos[0]
        self.assertEqual(pedido.full_url, ENDERECO.format(modelo="modelo-x"))
        self.assertNotIn(CHAVE, pedido.full_url)
        self.assertEqual(pedido.get_header("X-goog-api-key"), CHAVE)

    def test_corpo(self):
        g, abridor, _ = cliente(ok())
        g.responder("as regras", "a pergunta")
        corpo = json.loads(abridor.pedidos[0].data)
        self.assertEqual(corpo["systemInstruction"]["parts"][0]["text"], "as regras")
        self.assertEqual(corpo["contents"][0]["parts"][0]["text"], "a pergunta")
        config = corpo["generationConfig"]
        self.assertEqual(config["temperature"], 0)
        self.assertEqual(config["responseMimeType"], "application/json")
        self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "LOW"})

    def test_sem_raciocinio(self):
        g, abridor, _ = cliente(ok(), raciocinio=None)
        g.responder("s", "m")
        self.assertNotIn("thinkingConfig", json.loads(abridor.pedidos[0].data)["generationConfig"])


class LerResposta(unittest.TestCase):
    def test_ignora_o_texto_do_raciocinio(self):
        g, _, _ = cliente(ok(partes=[{"text": "pensando...", "thought": True}, {"text": '{"a": 1}'}]))
        self.assertEqual(g.responder("s", "m"), '{"a": 1}')

    def test_soma_o_uso_com_raciocinio(self):
        g, _, _ = cliente(ok(entrada=100, saida=20, raciocinio=30), ok(entrada=50, saida=10, raciocinio=0))
        g.responder("s", "m")
        g.responder("s", "m")
        self.assertEqual((g.uso.chamadas, g.uso.tokens_entrada, g.uso.tokens_saida), (2, 150, 60))

    def test_pergunta_bloqueada(self):
        g, _, _ = cliente(Resposta({"promptFeedback": {"blockReason": "SAFETY"}}))
        with self.assertRaisesRegex(ErroDoModelo, "SAFETY"):
            g.responder("s", "m")

    def test_resposta_vazia(self):
        g, _, _ = cliente(ok(texto=""))
        with self.assertRaisesRegex(ErroDoModelo, "vazia"):
            g.responder("s", "m")


class Erros(unittest.TestCase):
    def test_sem_chave(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ErroDoModelo, "GEMINI_API_KEY"):
                Gemini()

    def test_chave_da_variavel_de_ambiente(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": CHAVE, "GEMINI_MODELO": "outro"}, clear=True):
            g = Gemini(abrir=Abridor(ok()))
        self.assertEqual(g.modelo, "outro")
        self.assertNotIn(CHAVE, repr(g))

    def test_erro_http_nao_mostra_a_chave(self):
        g, _, _ = cliente(erro_http(400, f"API key {CHAVE} inválida"))
        with self.assertRaises(ErroDoModelo) as contexto:
            g.responder("s", "m")
        self.assertIn("HTTP 400", str(contexto.exception))
        self.assertNotIn(CHAVE, str(contexto.exception))

    def test_tenta_de_novo_quando_o_servico_oscila(self):
        avisos = []
        g, abridor, esperas = cliente(erro_http(503), erro_http(429), ok('{"ok": true}'), avisar=avisos.append)
        self.assertEqual(g.responder("s", "m"), '{"ok": true}')
        self.assertEqual(len(abridor.pedidos), 3)
        self.assertEqual(esperas, [5.0, 10.0])
        # Quem roda vê que está esperando, em vez de achar que travou.
        self.assertEqual(avisos, [
            "  Gemini ocupado (HTTP 503); tentativa 2 de 5 em 5 s",
            "  Gemini ocupado (HTTP 429); tentativa 3 de 5 em 10 s",
        ])

    def test_desiste_depois_das_tentativas(self):
        g, abridor, esperas = cliente(*(erro_http(503) for _ in range(5)))
        with self.assertRaisesRegex(ErroDoModelo, "HTTP 503"):
            g.responder("s", "m")
        self.assertEqual(len(abridor.pedidos), 5)
        self.assertEqual(esperas, [5.0, 10.0, 20.0, 40.0])

    def test_tempo_esgotado_tenta_de_novo(self):
        # Foi o primeiro erro da rodada real: TimeoutError não é URLError.
        g, _, _ = cliente(TimeoutError("lento"), ok('{"ok": true}'))
        self.assertEqual(g.responder("s", "m"), '{"ok": true}')

    def test_tempo_esgotado_em_todas(self):
        g, _, _ = cliente(*(TimeoutError("lento") for _ in range(5)))
        with self.assertRaisesRegex(ErroDoModelo, "não respondeu em 120 s"):
            g.responder("s", "m")

    def test_nao_repete_erro_que_nao_passa_sozinho(self):
        g, abridor, _ = cliente(erro_http(403), ok())
        with self.assertRaisesRegex(ErroDoModelo, "HTTP 403"):
            g.responder("s", "m")
        self.assertEqual(len(abridor.pedidos), 1)

    def test_sem_conexao(self):
        g, _, _ = cliente(*(urllib.error.URLError("rede fora") for _ in range(5)))
        with self.assertRaisesRegex(ErroDoModelo, "sem conexão"):
            g.responder("s", "m")


class Vertex(unittest.TestCase):
    def test_enderecos(self):
        self.assertEqual(
            endereco_vertex("portfolio-88eeb", "us", "gemini-3.8-flash"),
            "https://aiplatform.us.rep.googleapis.com/v1beta1/projects/portfolio-88eeb/locations/us"
            "/publishers/google/models/gemini-3.8-flash:generateContent",
        )
        self.assertTrue(endereco_vertex("p", "global", "m").startswith("https://aiplatform.googleapis.com/v1beta1/"))
        self.assertTrue(endereco_vertex("p", "us-central1", "m").startswith("https://us-central1-aiplatform.googleapis.com/"))

    def vertex(self, *saidas, tokens=("token-1",)):
        abridor = Abridor(*saidas)
        fila = list(tokens)
        pedidos_de_token = []

        def obter_token():
            pedidos_de_token.append(1)
            return fila.pop(0) if len(fila) > 1 else fila[0]

        with mock.patch.dict(os.environ, {}, clear=True):  # não precisa de GEMINI_API_KEY
            g = Gemini(modelo="m", vertex_projeto="portfolio-88eeb", obter_token=obter_token,
                       abrir=abridor, dormir=lambda _s: None)
        return g, abridor, pedidos_de_token

    def test_login_do_gcloud_e_projeto_de_cobranca(self):
        g, abridor, _ = self.vertex(ok())
        g.responder("s", "m")
        pedido = abridor.pedidos[0]
        self.assertEqual(pedido.get_header("Authorization"), "Bearer token-1")
        self.assertEqual(pedido.get_header("X-goog-user-project"), "portfolio-88eeb")
        self.assertIsNone(pedido.get_header("X-goog-api-key"))
        self.assertIn("/projects/portfolio-88eeb/locations/us/", pedido.full_url)
        self.assertIn("portfolio-88eeb", g.descricao)

    def test_token_vencido_pega_outro_uma_vez(self):
        g, abridor, pedidos_de_token = self.vertex(erro_http(401), ok('{"ok": 1}'), tokens=("velho", "novo"))
        self.assertEqual(g.responder("s", "m"), '{"ok": 1}')
        self.assertEqual(len(pedidos_de_token), 2)
        self.assertEqual(abridor.pedidos[1].get_header("Authorization"), "Bearer novo")

    def test_401_de_novo_desiste(self):
        g, _, _ = self.vertex(erro_http(401), erro_http(401))
        with self.assertRaisesRegex(ErroDoModelo, "HTTP 401"):
            g.responder("s", "m")

    def test_erro_nao_mostra_o_token(self):
        g, _, _ = self.vertex(erro_http(403, "token token-1 sem permissão"))
        with self.assertRaises(ErroDoModelo) as contexto:
            g.responder("s", "m")
        self.assertNotIn("token-1", str(contexto.exception))


class LoginDoGcloud(unittest.TestCase):
    LOGIN = {"type": "authorized_user", "client_id": "id-x", "client_secret": "segredo-x", "refresh_token": "renova-x"}

    def arquivo(self, conteudo):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        caminho = Path(pasta.name) / "application_default_credentials.json"
        caminho.write_text(json.dumps(conteudo), encoding="utf-8")
        return caminho

    def test_troca_o_login_por_um_token(self):
        abridor = Abridor(Resposta({"access_token": "tok-123", "expires_in": 3599}))
        self.assertEqual(token_do_login_do_gcloud(self.arquivo(self.LOGIN), abrir=abridor), "tok-123")
        pedido = abridor.pedidos[0]
        self.assertEqual(pedido.full_url, "https://oauth2.googleapis.com/token")
        corpo = urllib.parse.parse_qs(pedido.data.decode("utf-8"))
        self.assertEqual(corpo["grant_type"], ["refresh_token"])
        self.assertEqual(corpo["refresh_token"], ["renova-x"])

    def test_sem_login(self):
        with self.assertRaisesRegex(ErroDoModelo, "gcloud auth application-default login"):
            token_do_login_do_gcloud(Path(tempfile.gettempdir()) / "nao-existe-lgpd-rag.json")

    def test_login_de_conta_de_servico_nao_serve(self):
        with self.assertRaisesRegex(ErroDoModelo, "usuário"):
            token_do_login_do_gcloud(self.arquivo({"type": "service_account"}), abrir=Abridor())

    def test_login_recusado_nao_mostra_segredo(self):
        abridor = Abridor(erro_http(400, "invalid_grant renova-x segredo-x"))
        with self.assertRaises(ErroDoModelo) as contexto:
            token_do_login_do_gcloud(self.arquivo(self.LOGIN), abrir=abridor)
        mensagem = str(contexto.exception)
        self.assertIn("HTTP 400", mensagem)
        for segredo in ("renova-x", "segredo-x", "id-x"):
            self.assertNotIn(segredo, mensagem)


if __name__ == "__main__":
    unittest.main()
