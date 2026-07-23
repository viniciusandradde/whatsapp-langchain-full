"""Testes do sanitizador de resposta do agente (vazamento de raciocínio)."""

from whatsapp_langchain.shared.sanitize_resposta import sanitize_resposta_agente


class TestSanitize:
    def test_remove_bloco_raciocinio_e_mantem_resposta(self):
        txt = (
            "<raciocinio_interno>\n1. Quem é? aluno\n2. intenção: teste\n"
            "</raciocinio_interno>\nOlá, tudo bem? Como posso ajudar?"
        )
        assert sanitize_resposta_agente(txt) == "Olá, tudo bem? Como posso ajudar?"

    def test_multiplos_blocos(self):
        txt = "<triagem>RESOLVIDA</triagem>Resposta.<raciocinio_interno>x</raciocinio_interno>"
        assert sanitize_resposta_agente(txt) == "Resposta."

    def test_bloco_aberto_sem_fechamento(self):
        txt = "Certo, vou verificar.\n<raciocinio_interno>\n1. avaliando"
        assert sanitize_resposta_agente(txt) == "Certo, vou verificar."

    def test_so_bloco_preserva_conteudo_sem_tags(self):
        txt = "<raciocinio_interno>Pode falar. Estou à disposição.</raciocinio_interno>"
        out = sanitize_resposta_agente(txt)
        assert "raciocinio_interno" not in out
        assert "Pode falar" in out

    def test_texto_normal_intacto(self):
        txt = "A rematrícula é paga em julho, com desconto até o dia 10."
        assert sanitize_resposta_agente(txt) == txt

    def test_comparacao_matematica_nao_e_tag(self):
        txt = "Se a nota for < 6, o aluno fica em DP. Se for > 6, aprovado."
        assert sanitize_resposta_agente(txt) == txt
