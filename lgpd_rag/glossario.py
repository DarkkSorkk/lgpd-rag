"""Palavras do dia a dia trocadas pelos termos que a LGPD usa.

Quem pergunta diz "vazamento"; a lei diz "incidente de segurança". A busca por
palavra não liga as duas sozinha. A lista é pequena e geral de propósito: termos
comuns de quem lida com a LGPD, não ajustes para perguntas específicas do gabarito.
As chaves são comparadas sem acento e em minúsculas.
"""

GLOSSARIO: dict[str, str] = {
    # incidente de segurança (art. 46 a 48)
    "vazamento": "incidente de segurança",
    "vazamentos": "incidente de segurança",
    "vazou": "incidente de segurança",
    "vazaram": "incidente de segurança",
    "invasao": "incidente de segurança acesso não autorizado",
    "hacker": "incidente de segurança acesso não autorizado",
    "ataque hacker": "incidente de segurança acesso não autorizado",
    # encarregado (art. 41)
    "dpo": "encarregado",
    "data protection officer": "encarregado",
    # eliminação dos dados (art. 16 e 18)
    "apagar": "eliminação",
    "apague": "eliminação",
    "excluir": "eliminação",
    "exclua": "eliminação",
    "deletar": "eliminação",
    "delete": "eliminação",
    # consentimento (art. 7º e 8º)
    "autorizacao": "consentimento",
    "autorizar": "consentimento",
    "permissao": "consentimento",
    # sanções (art. 52)
    "punicao": "sanções",
    "penalidade": "sanções",
    "penalidades": "sanções",
    # transferência internacional (art. 33)
    "exterior": "transferência internacional",
    "outro pais": "transferência internacional",
    "fora do brasil": "transferência internacional",
    "estados unidos": "transferência internacional",
    "europa": "transferência internacional",
    # Empresa de fora que trata dados de quem está aqui: a lei vale "independentemente
    # do país de sua sede", quando os dados são de pessoas no território nacional
    # (art. 3º). Sem estas entradas, o art. 3º sumia da busca (rodada de 15/11/2026).
    # Pôr "país sede" também nas entradas acima tirou o art. 33 do 1º lugar nas
    # perguntas de transferência do desenvolvimento, então elas ficaram como estavam.
    "estrangeiro": "país sede",
    "estrangeira": "país sede",
    "estrangeiros": "país sede",
    "estrangeiras": "país sede",
    "no brasil": "território nacional",
    "brasileiro": "território nacional",
    "brasileira": "território nacional",
    "brasileiros": "território nacional",
    "brasileiras": "território nacional",
    # poder público (art. 23)
    "prefeitura": "poder público pessoa jurídica de direito público",
    "governo": "poder público pessoa jurídica de direito público",
    "orgao publico": "poder público pessoa jurídica de direito público",
    # crianças e adolescentes (art. 14)
    "filho": "criança adolescente",
    "filha": "criança adolescente",
    "filhos": "criança adolescente",
    "menor de idade": "criança adolescente",
    "menores de idade": "criança adolescente",
    # quem trata os dados é o controlador; quem pede, faz requerimento (art. 18)
    "empresa": "controlador",
    "empresas": "controlador",
    "pedir": "requerimento requisição",
    "pedido": "requerimento requisição",
    # titular
    "cliente": "titular",
    "clientes": "titular",
    "usuario": "titular",
    "usuarios": "titular",
    # término do tratamento (art. 15 e 16)
    "cancelou": "término do tratamento",
    "cancelar": "término do tratamento",
    "encerrou": "término do tratamento",
    # portabilidade (art. 18, V)
    "levar meus dados": "portabilidade",
    "levar os dados": "portabilidade",
    "transferir meus dados": "portabilidade",
    # dados sensíveis (art. 5º, II)
    "biometria": "dado biométrico sensível",
    "digital": "dado biométrico sensível",
}
