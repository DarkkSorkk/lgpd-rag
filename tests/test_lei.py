"""Testes do leitor da página do Planalto.

A página abaixo é um recorte da LGPD com a marcação que o Planalto usa de verdade:
<span> partindo frases, notas de alteração em links, "Vigência", um número de
artigo partido em dois <span>, texto de outra lei citado entre aspas e as
assinaturas no fim. O texto completo e oficial fica em dados/lgpd.json.
"""

import unittest

from lgpd_rag.lei import decodificar, ler_html, ler_linhas

PAGINA = """<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252">
<title>L13709compilado</title></head><body>
<p>Presidência da República<br>Secretaria-Geral<br>Subchefia para Assuntos Jurídicos</p>
<p><a href="#">LEI Nº 13.709, DE 14 DE AGOSTO DE 2018</a></p>
<p><a href="Msg/VEP/VEP-451.htm">Mensagem de veto</a></p>
<p><a href="#art65">Vigência</a></p>
<p align="justify"><font face="Arial" size="2"><span style="color:#800000">
  Lei Geral de Proteção de Dados Pessoais (LGPD).</span><span>&nbsp;&nbsp;&nbsp;&nbsp;<a
  href="../../../_Ato2019-2022/2019/Lei/L13853.htm#art2">(Redação dada
  pela Lei nº 13.853, de 2019)</a>&nbsp;&nbsp;&nbsp; </span>
  <font size="2"><a href="#art65..">Vigência</a></font></font></p>
<p>O PRESIDENTE DA REPÚBLICA Faço saber que o Congresso Nacional decreta e eu sanciono a seguinte Lei:</p>
<p align="center">CAPÍTULO I<br>DISPOSIÇÕES PRELIMINARES</p>
<p class="Artigo"><span>Art. 1º Esta Lei dispõe sobre o tratamento de dados pessoais, inclusive nos meios
  digitais, por pessoa natural ou por pessoa jurídica de direito público ou privado, com o objetivo de
  proteger os direitos fundamentais de liberdade e de privacidade e o livre desenvolvimento da
  personalidade da pessoa natural.</span></p>
<p class="Artigo"><span>Parágrafo único. As normas gerais contidas nesta Lei são de interesse nacional e devem
  ser observadas pela União, Estados, Distrito Federal e Municípios. </span><a
  href="../../../_Ato2019-2022/2019/Lei/L13853.htm#art2">(Incluído pela Lei nº 13.853, de 2019)</a></p>
<p class="Artigo"><span>Art. 5º Para os fins desta Lei, considera-se:</span></p>
<p class="Artigo"><span>IX - agentes de tratamento: o controlador e o operador;</span></p>
<p align="center">CAPÍTULO II</p>
<p align="center">DO TRATAMENTO DE DADOS PESSOAIS</p>
<p align="center">Seção I<br>Dos Requisitos para o Tratamento de Dados Pessoais</p>
<p class="Artigo"><span>Art. 7º O tratamento de dados pessoais somente poderá ser realizado nas seguintes
  hipóteses:</span></p>
<p class="Artigo"><span>I - mediante o fornecimento de consentimento pelo titular;</span></p>
<p class="Artigo"><span>§ 1º (Revogado).</span><span>&nbsp;&nbsp;&nbsp;&nbsp;
  <a href="../../../_Ato2019-2022/2019/Lei/L13853.htm#art2">(Redação dada pela
  Lei nº 13.853, de 2019)</a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; </span>
  <font size="2"><a href="#art65..">Vigência</a></font></p>
<p class="Artigo"><span>§ 3º O tratamento de dados pessoais cujo acesso é público deve considerar a finalidade,
  a boa-fé e o interesse público que justificaram sua disponibilização.</span></p>
<p class="Artigo"><span>Art. 11. O tratamento de dados pessoais sensíveis somente poderá ocorrer nas seguintes
  hipóteses:</span></p>
<p class="Artigo"><span>II - sem fornecimento de consentimento do titular, nas hipóteses em que for
  indispensável para:</span></p>
<p class="Artigo"><span>a) cumprimento de obrigação legal ou regulatória pelo controlador;</span></p>
<p class="Artigo"><span> Art. 5 </span><span lang="EN-US"> 7. </span><span> (VETADO). </span></p>
<p class="Artigo"><span>Art. 60. A Lei nº 12.965, de 23 de abril de 2014 (Marco Civil da Internet) , passa a
  vigorar com as seguintes alterações:</span></p>
<p>“Art. 7º ..................................................................</p>
<p>.......................................................................................</p>
<p>X - exclusão definitiva dos dados pessoais que tiver fornecido a determinada aplicação de internet,
  a seu requerimento, ao término da relação entre as partes;</p>
<p>..............................................................................” (NR)</p>
<p class="Artigo"><span>Art. 65. Esta Lei entra em vigor: <a href="#">(Redação dada pela Lei nº 13.853,
  de 2019)</a></span></p>
<p class="Artigo"><span>I - dia 28 de dezembro de 2018, quanto aos arts. 55-A, 55-B; </span></p>
<p class="Artigo"><span>I-A – dia 1º de agosto de 2021, quanto aos arts. 52, 53 e 54; <a href="#">(Incluído
  pela Lei nº 14.010, de 2020)</a></span></p>
<p>Brasília , 14 de agosto de 2018; 197º da Independência e 130º da República.</p>
<p>MICHEL TEMER</p>
</body></html>"""


class LerPaginaDoPlanalto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lista = ler_html(PAGINA)
        cls.por_id = {d.id: d for d in cls.lista}

    def test_comeca_no_art_1_e_para_na_assinatura(self):
        self.assertEqual(self.lista[0].id, "art1")
        self.assertEqual(self.lista[-1].id, "art65.I-A")
        self.assertFalse(any("TEMER" in d.texto or "PRESIDENTE" in d.texto for d in self.lista))

    def test_tira_as_notas_do_planalto(self):
        for d in self.lista:
            for nota in ("Redação dada", "Incluído pela", "Vigência", "Mensagem de veto"):
                self.assertNotIn(nota, d.texto, d.id)
        self.assertEqual(self.por_id["art65"].texto, "Esta Lei entra em vigor:")
        self.assertEqual(
            self.por_id["art1.pu"].texto,
            "As normas gerais contidas nesta Lei são de interesse nacional e devem ser observadas "
            "pela União, Estados, Distrito Federal e Municípios.",
        )

    def test_rotulos_para_citar(self):
        rotulos = {
            "art1": "Art. 1º",
            "art1.pu": "Art. 1º, parágrafo único",
            "art5.IX": "Art. 5º, IX",
            "art7.I": "Art. 7º, I",
            "art7.p3": "Art. 7º, § 3º",
            "art11": "Art. 11",
            "art11.II.a": "Art. 11, II, a",
            "art65.I-A": "Art. 65, I-A",
        }
        for ident, rotulo in rotulos.items():
            self.assertEqual(self.por_id[ident].rotulo, rotulo)

    def test_hierarquia(self):
        self.assertEqual(self.por_id["art11.II.a"].pai, "art11.II")
        self.assertEqual(self.por_id["art11.II"].pai, "art11")
        self.assertEqual(self.por_id["art7.p3"].pai, "art7")
        self.assertEqual(self.por_id["art11.II.a"].tipo, "alinea")
        self.assertEqual(self.por_id["art11.II.a"].artigo, "11")

    def test_revogado_e_vetado(self):
        self.assertEqual(self.por_id["art7.p1"].situacao, "revogado")
        self.assertEqual(self.por_id["art7.p3"].situacao, "vigente")

    def test_numero_partido_em_dois_spans(self):
        # Na página real, "Art. 57" vem como "Art. 5" + "7." em <span> separados.
        self.assertEqual(self.por_id["art57"].rotulo, "Art. 57")
        self.assertEqual(self.por_id["art57"].situacao, "vetado")

    def test_ignora_texto_citado_de_outra_lei(self):
        # O art. 60 cita artigos do Marco Civil da Internet entre aspas.
        self.assertIn("art60", self.por_id)
        self.assertFalse(any("exclusão definitiva" in d.texto for d in self.lista))

    def test_capitulo_e_secao(self):
        self.assertEqual(self.por_id["art1"].capitulo, "CAPÍTULO I - DISPOSIÇÕES PRELIMINARES")
        self.assertEqual(self.por_id["art1"].secao, "")
        self.assertEqual(self.por_id["art7"].capitulo, "CAPÍTULO II - DO TRATAMENTO DE DADOS PESSOAIS")
        self.assertEqual(self.por_id["art7"].secao, "Seção I - Dos Requisitos para o Tratamento de Dados Pessoais")

    def test_pagina_em_windows_1252(self):
        self.assertEqual(ler_html(decodificar(PAGINA.encode("cp1252"))), self.lista)


class LinksDaPagina(unittest.TestCase):
    def test_link_de_nota_sai_e_link_no_texto_da_lei_fica(self):
        html = (
            '<p>Art. 2º Conforme o <a href="#d">regulamento</a>, vale a regra. '
            '<a href="#r">Regulamento</a> <a href="#v">Vigência</a></p>'
        )
        self.assertEqual(ler_html(html)[0].texto, "Conforme o regulamento, vale a regra.")

    def test_revogado_dentro_de_link_continua_revogado(self):
        html = '<p>Art. 3º Caput.</p><p>§ 2º <a href="#x">(Revogado)</a>.</p>'
        self.assertEqual(ler_html(html)[-1].situacao, "revogado")


class LerLinhas(unittest.TestCase):
    def test_dispositivo_repetido_falha(self):
        with self.assertRaisesRegex(ValueError, "Art. 1º"):
            ler_linhas(["Art. 1º Um texto.", "Art. 1º Outro texto."])

    def test_revogado_pela_lei_fica_no_texto_e_marca_o_dispositivo(self):
        lista = ler_linhas(["Art. 55-B. (Revogado pela Lei nº 14.460, de 2022)"])
        self.assertEqual(lista[0].rotulo, "Art. 55-B")
        self.assertEqual(lista[0].texto, "(Revogado pela Lei nº 14.460, de 2022)")
        self.assertEqual(lista[0].situacao, "revogado")

    def test_titulo_do_capitulo_na_linha_seguinte(self):
        # Na página real, o título do Capítulo IX termina com um apóstrofo perdido.
        lista = ler_linhas(["CAPÍTULO IX", "DA AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS’", "Art. 55. (VETADO)."])
        self.assertEqual(lista[0].capitulo, "CAPÍTULO IX - DA AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS")
        self.assertEqual(lista[0].situacao, "vetado")

    def test_palavra_com_letras_romanas_nao_vira_inciso(self):
        lista = ler_linhas(["Art. 1º Texto que continua", "CIVIL - na linha seguinte."])
        self.assertEqual(len(lista), 1)
        self.assertEqual(lista[0].texto, "Texto que continua CIVIL - na linha seguinte.")

    def test_incisos_depois_de_paragrafo_pertencem_ao_paragrafo(self):
        lista = ler_linhas(["Art. 9º Caput:", "§ 1º Parágrafo:", "I - inciso do parágrafo;"])
        self.assertEqual(lista[-1].id, "art9.p1.I")
        self.assertEqual(lista[-1].rotulo, "Art. 9º, § 1º, I")


if __name__ == "__main__":
    unittest.main()
