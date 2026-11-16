"""Cliente do Gemini sem dependências (só urllib), de dois jeitos:

- Google AI Studio: a chave vem da variável GEMINI_API_KEY e vai no cabeçalho
  x-goog-api-key, nunca na URL. É o jeito mais simples para quem clona o repositório.
- Vertex AI, sem chave nenhuma: usa o login do gcloud no computador de quem roda
  (`gcloud auth application-default login`) e cobra no projeto do Google Cloud
  indicado, o mesmo que já tem orçamento e alertas.

Nenhuma mensagem de erro mostra a chave, o token ou o conteúdo do login.
O modelo pode ser trocado pela variável GEMINI_MODELO.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ENDERECO = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
TOKEN_DO_GOOGLE = "https://oauth2.googleapis.com/token"
MODELO_PADRAO = "gemini-3.8-flash"
RACIOCINIO_PADRAO = "LOW"  # pouco raciocínio: a resposta é curta e o texto vem pronto
REPETIR_EM = (429, 500, 503)  # cota momentânea e instabilidade do serviço
REFAZER_LOGIN = "rode  gcloud auth application-default login"


class ErroDoModelo(RuntimeError):
    pass


@dataclass
class Uso:
    chamadas: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0  # inclui os tokens de raciocínio, cobrados como saída


def endereco_vertex(projeto: str, regiao: str, modelo: str) -> str:
    """O mesmo endereço que a biblioteca oficial do Google monta para o Vertex AI."""
    if regiao == "global":
        base = "https://aiplatform.googleapis.com"
    elif regiao in ("us", "eu"):  # multirregião
        base = f"https://aiplatform.{regiao}.rep.googleapis.com"
    else:
        base = f"https://{regiao}-aiplatform.googleapis.com"
    projeto, regiao, modelo = (urllib.parse.quote(p, safe="") for p in (projeto, regiao, modelo))
    return f"{base}/v1beta1/projects/{projeto}/locations/{regiao}/publishers/google/models/{modelo}:generateContent"


def caminho_do_login_do_gcloud() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", "")) / "gcloud" / "application_default_credentials.json"
    return Path.home() / ".config" / "gcloud" / "application_default_credentials.json"


def token_do_login_do_gcloud(caminho: Path | None = None, abrir: Callable[..., Any] = urllib.request.urlopen) -> str:
    """Troca o login guardado pelo gcloud por um token de acesso de uma hora."""
    try:
        login = json.loads(Path(caminho or caminho_do_login_do_gcloud()).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErroDoModelo(f"não achei o login do gcloud: {REFAZER_LOGIN}") from None
    except (OSError, ValueError):
        raise ErroDoModelo(f"não consegui ler o login do gcloud: {REFAZER_LOGIN}") from None
    if not isinstance(login, dict) or login.get("type") != "authorized_user":
        raise ErroDoModelo(f"o login do gcloud precisa ser de um usuário: {REFAZER_LOGIN}")
    campos = {chave: login.get(chave, "") for chave in ("client_id", "client_secret", "refresh_token")}
    pedido = urllib.request.Request(
        TOKEN_DO_GOOGLE,
        data=urllib.parse.urlencode({**campos, "grant_type": "refresh_token"}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with abrir(pedido, timeout=30) as resposta:
            token = json.loads(resposta.read().decode("utf-8")).get("access_token")
    except urllib.error.HTTPError as erro:
        erro.close()
        raise ErroDoModelo(f"o Google recusou o login do gcloud (HTTP {erro.code}): {REFAZER_LOGIN}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        raise ErroDoModelo("não consegui renovar o login do gcloud (sem conexão ou resposta inválida)") from None
    if not token:
        raise ErroDoModelo(f"o Google não devolveu o token do login do gcloud: {REFAZER_LOGIN}")
    return token


class Gemini:
    def __init__(
        self,
        chave: str | None = None,
        modelo: str | None = None,
        raciocinio: str | None = RACIOCINIO_PADRAO,
        vertex_projeto: str | None = None,  # com projeto, usa o Vertex AI e o login do gcloud
        vertex_regiao: str = "us",
        obter_token: Callable[[], str] | None = None,
        # Em pico de demanda o Gemini devolve 503 por alguns segundos: 5 tentativas,
        # esperando 5, 10, 20 e 40 s entre elas (no máximo 75 s por pergunta).
        tentativas: int = 5,
        espera: float = 5.0,
        tempo_limite: float = 120.0,
        abrir: Callable[..., Any] = urllib.request.urlopen,
        dormir: Callable[[float], None] = time.sleep,
        avisar: Callable[[str], None] | None = None,  # recebe "ocupado, nova tentativa em X s"
    ) -> None:
        self.modelo = modelo or os.environ.get("GEMINI_MODELO") or MODELO_PADRAO
        self.raciocinio = raciocinio
        self.vertex_projeto, self.vertex_regiao = vertex_projeto, vertex_regiao
        self.tentativas, self.espera, self.tempo_limite = tentativas, espera, tempo_limite
        self._abrir, self._dormir = abrir, dormir
        self._avisar = avisar or (lambda _texto: None)
        self._token: str | None = None
        self.uso = Uso()
        if vertex_projeto:
            self._chave = ""
            self._obter_token = obter_token or (lambda: token_do_login_do_gcloud(abrir=abrir))
        else:
            # Espaço ou quebra de linha colados junto com a chave fazem o Google recusá-la.
            self._chave = (chave if chave is not None else os.environ.get("GEMINI_API_KEY", "")).strip()
            if not self._chave:
                raise ErroDoModelo("defina a variável de ambiente GEMINI_API_KEY com a sua chave do Google AI Studio")

    def __repr__(self) -> str:
        onde = f"vertex={self.vertex_projeto!r}" if self.vertex_projeto else "ai_studio"
        return f"Gemini(modelo={self.modelo!r}, {onde})"

    @property
    def descricao(self) -> str:
        if self.vertex_projeto:
            return f"{self.modelo} pelo Vertex AI (projeto {self.vertex_projeto}, região {self.vertex_regiao}, login do gcloud)"
        return f"{self.modelo} pelo Google AI Studio (chave GEMINI_API_KEY)"

    def _esperar(self, tentativa: int, motivo: str) -> None:
        segundos = self.espera * 2 ** (tentativa - 1)
        self._avisar(f"  Gemini {motivo}; tentativa {tentativa + 1} de {self.tentativas} em {segundos:.0f} s")
        self._dormir(segundos)

    def _sem_segredo(self, texto: str) -> str:
        for segredo in (self._chave, self._token):
            if segredo:
                texto = texto.replace(segredo, "***")
        return texto

    def _pedido(self, corpo: bytes) -> urllib.request.Request:
        if self.vertex_projeto:
            if self._token is None:
                self._token = self._obter_token()
            endereco = endereco_vertex(self.vertex_projeto, self.vertex_regiao, self.modelo)
            # A cota e a cobrança ficam no projeto indicado, não no projeto padrão do gcloud.
            cabecalhos = {"Authorization": f"Bearer {self._token}", "x-goog-user-project": self.vertex_projeto}
        else:
            endereco = ENDERECO.format(modelo=urllib.parse.quote(self.modelo, safe=""))
            cabecalhos = {"x-goog-api-key": self._chave}
        return urllib.request.Request(
            endereco, data=corpo, headers={"Content-Type": "application/json", **cabecalhos}, method="POST"
        )

    def responder(self, sistema: str, mensagem: str) -> str:
        configuracao: dict[str, Any] = {
            "temperature": 0,
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,
        }
        if self.raciocinio:
            configuracao["thinkingConfig"] = {"thinkingLevel": self.raciocinio}
        corpo = json.dumps({
            "systemInstruction": {"parts": [{"text": sistema}]},
            "contents": [{"role": "user", "parts": [{"text": mensagem}]}],
            "generationConfig": configuracao,
        }).encode("utf-8")
        renovou_login = False
        for tentativa in range(1, self.tentativas + 1):
            try:
                with self._abrir(self._pedido(corpo), timeout=self.tempo_limite) as resposta:
                    dados = json.loads(resposta.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as erro:
                try:
                    vencido = erro.code == 401 and bool(self.vertex_projeto) and not renovou_login
                    repetir = (erro.code in REPETIR_EM or vencido) and tentativa < self.tentativas
                    detalhe = "" if repetir else self._sem_segredo(_mensagem(erro))
                finally:
                    erro.close()
                if vencido and repetir:  # o token de uma hora venceu: pega outro e tenta já
                    self._token, renovou_login = None, True
                    continue
                if repetir:
                    self._esperar(tentativa, f"ocupado (HTTP {erro.code})")
                    continue
                raise ErroDoModelo(f"HTTP {erro.code}: {detalhe}") from None
            except urllib.error.URLError as erro:
                if tentativa < self.tentativas:
                    self._esperar(tentativa, "sem conexão")
                    continue
                raise ErroDoModelo(f"sem conexão com o Gemini ({self._sem_segredo(str(erro.reason))})") from None
            except (TimeoutError, ConnectionError):  # a resposta demorou ou a conexão caiu no meio
                if tentativa < self.tentativas:
                    self._esperar(tentativa, f"não respondeu em {self.tempo_limite:.0f} s")
                    continue
                raise ErroDoModelo(f"o Gemini não respondeu em {self.tempo_limite:.0f} s") from None
        return self._ler(dados)

    def _ler(self, dados: dict) -> str:
        uso = dados.get("usageMetadata") or {}
        self.uso.chamadas += 1
        self.uso.tokens_entrada += int(uso.get("promptTokenCount", 0))
        self.uso.tokens_saida += int(uso.get("candidatesTokenCount", 0)) + int(uso.get("thoughtsTokenCount", 0))

        candidatos = dados.get("candidates") or []
        if not candidatos:
            motivo = (dados.get("promptFeedback") or {}).get("blockReason", "sem candidatos")
            raise ErroDoModelo(f"o modelo não respondeu ({motivo})")
        partes = (candidatos[0].get("content") or {}).get("parts") or []
        texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))
        if not texto.strip():
            raise ErroDoModelo(f"resposta vazia ({candidatos[0].get('finishReason', 'sem motivo')})")
        return texto


def _mensagem(erro: urllib.error.HTTPError) -> str:
    try:
        corpo = json.loads(erro.read().decode("utf-8"))
        return str((corpo.get("error") or {}).get("message", ""))[:300]
    except Exception:
        return str(erro.reason)[:300]
