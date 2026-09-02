"""Partição por opt-out — a regra pura do gate de supressão (H0).

Contexto: até esta correção, `disparador_opt_out` era consultado só no
preview do disparo. Quem criava campanha pelo painel enviava para quem
pediu descadastro. A função aqui é a metade determinística do gate; a
metade que fala com o banco está em `tests/integration/test_opt_out_campanha.py`.
"""

from __future__ import annotations

from whatsapp_langchain.shared.campanha import particionar_suprimidos


class TestParticionarSuprimidos:
    def test_sem_supressao_passa_tudo(self) -> None:
        tels = ["+5511900000001", "+5511900000002"]
        permitidos, bloqueados = particionar_suprimidos(tels, set())
        assert permitidos == tels
        assert bloqueados == []

    def test_separa_o_suprimido(self) -> None:
        permitidos, bloqueados = particionar_suprimidos(
            ["+5511900000001", "+5511900000002", "+5511900000003"],
            {"+5511900000002"},
        )
        assert permitidos == ["+5511900000001", "+5511900000003"]
        assert bloqueados == ["+5511900000002"]

    def test_preserva_a_ordem(self) -> None:
        """A ordem vira `campanha_destinatario.id`, que é a ordem de envio."""
        tels = [f"+55119000000{i:02d}" for i in range(10)]
        permitidos, _ = particionar_suprimidos(tels, {tels[3], tels[7]})
        assert permitidos == [t for t in tels if t not in {tels[3], tels[7]}]

    def test_todos_suprimidos_esvazia(self) -> None:
        tels = ["+5511900000001", "+5511900000002"]
        permitidos, bloqueados = particionar_suprimidos(tels, set(tels))
        assert permitidos == []
        assert bloqueados == tels

    def test_lista_vazia(self) -> None:
        assert particionar_suprimidos([], {"+5511900000001"}) == ([], [])

    def test_suprimido_ausente_da_lista_nao_inventa(self) -> None:
        """Supressão que não casa com ninguém não pode remover ninguém."""
        tels = ["+5511900000001"]
        permitidos, bloqueados = particionar_suprimidos(tels, {"+5599999999999"})
        assert permitidos == tels
        assert bloqueados == []

    def test_duplicata_na_entrada_e_bloqueada_nas_duas(self) -> None:
        """A dedup é de quem chama; aqui nenhuma cópia pode escapar do gate."""
        permitidos, bloqueados = particionar_suprimidos(
            ["+5511900000001", "+5511900000001"], {"+5511900000001"}
        )
        assert permitidos == []
        assert len(bloqueados) == 2
