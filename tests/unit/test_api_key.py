"""Testes unitários do módulo de API keys do Disparador (Task 1.3).

Cobre geração, parsing, comparação timing-safe e normalização de escopos.
Sem I/O de banco — a resolução contra o Postgres + RLS é testada em E2E
(test_api_keys_endpoints.py) junto da dependency verify_api_key (Task 2).
"""

import time

from whatsapp_langchain.shared.api_key import (
    VALID_SCOPES,
    generate_api_key,
    has_scope,
    hash_api_key,
    key_prefix_of,
    normalize_scopes,
    parse_empresa_id,
    verify_api_key,
)


class TestGenerateApiKey:
    def test_formato_e_prefixo(self):
        plain, prefix, key_hash = generate_api_key(1)
        assert plain.startswith("nxs_1_")
        assert prefix.startswith("nxs_1_")
        assert plain.startswith(prefix)  # prefix é início do segredo
        # hash é sha256 hex (64 chars) e bate com hash_api_key
        assert len(key_hash) == 64
        assert key_hash == hash_api_key(plain)

    def test_empresa_id_embutido(self):
        plain, _, _ = generate_api_key(42)
        assert parse_empresa_id(plain) == 42

    def test_unicidade(self):
        chaves = {generate_api_key(1)[0] for _ in range(50)}
        assert len(chaves) == 50  # nenhum colide

    def test_empresa_id_invalido_rejeitado(self):
        for bad in (0, -1):
            try:
                generate_api_key(bad)
                raise AssertionError("deveria ter levantado ValueError")
            except ValueError:
                pass


class TestParseEmpresaId:
    def test_validos(self):
        assert parse_empresa_id("nxs_7_" + "a" * 32) == 7

    def test_invalidos_retornam_none(self):
        for bad in (
            "",
            "abc",
            "nxs_7",  # faltando random
            "xxx_7_abcd",  # namespace errado
            "nxs_x_abcd",  # empresa não numérica
            "nxs_0_abcd",  # empresa não-positiva
            "nxs_7_abcd_extra",  # partes demais
        ):
            assert parse_empresa_id(bad) is None


class TestKeyPrefixOf:
    def test_prefixo_consistente_com_geracao(self):
        plain, prefix, _ = generate_api_key(3)
        assert key_prefix_of(plain) == prefix

    def test_token_invalido(self):
        assert key_prefix_of("lixo") is None


class TestVerifyApiKey:
    def test_match_correto(self):
        plain, _, key_hash = generate_api_key(1)
        assert verify_api_key(plain, key_hash) is True

    def test_chave_errada(self):
        _, _, key_hash = generate_api_key(1)
        assert verify_api_key("nxs_1_" + "0" * 32, key_hash) is False

    def test_entradas_vazias(self):
        assert verify_api_key("", "abc") is False
        assert verify_api_key("nxs_1_x", "") is False

    def test_timing_safe(self):
        """A comparação não deve curto-circuitar: tempo válido ≈ tempo inválido.

        Mede a mediana de muitas comparações; o desvio entre match e mismatch
        deve ser pequeno (hmac.compare_digest é tempo constante).
        """
        plain, _, key_hash = generate_api_key(1)
        wrong = "nxs_1_" + "0" * 32

        def median_ns(target: str) -> float:
            amostras = []
            for _ in range(2000):
                t0 = time.perf_counter_ns()
                verify_api_key(target, key_hash)
                amostras.append(time.perf_counter_ns() - t0)
            amostras.sort()
            return amostras[len(amostras) // 2]

        t_ok = median_ns(plain)
        t_bad = median_ns(wrong)
        # desvio relativo tolerante (ruído de CI), mas garante que não há
        # diferença de ordem de grandeza típica de comparação byte-a-byte
        maior, menor = max(t_ok, t_bad), min(t_ok, t_bad)
        assert maior < menor * 3 + 2000


class TestScopes:
    def test_normalize_default(self):
        assert normalize_scopes(None) == ["capture"]
        assert normalize_scopes([]) == ["capture"]

    def test_normalize_filtra_invalidos_e_dedup(self):
        out = normalize_scopes(["capture", "CAPTURE", "dispatch", "lixo", "templates"])
        assert out == ["capture", "dispatch", "templates"]

    def test_normalize_so_invalidos_volta_default(self):
        assert normalize_scopes(["lixo", "outro"]) == ["capture"]

    def test_has_scope(self):
        assert has_scope(["capture", "dispatch"], "dispatch") is True
        assert has_scope(["capture"], "templates") is False
        assert has_scope(None, "capture") is False

    def test_valid_scopes_constante(self):
        assert VALID_SCOPES == {"capture", "dispatch", "templates"}
