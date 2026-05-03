"""Tests do chunker (M5.c.1)."""

from whatsapp_langchain.shared.chunking import split_text


def test_empty_returns_empty():
    assert split_text("") == []
    assert split_text("   \n\n  ") == []


def test_short_text_returns_single_chunk():
    out = split_text("texto curto")
    assert out == ["texto curto"]


def test_text_at_limit_returns_single():
    text = "a" * 800
    out = split_text(text, max_chars=800)
    assert out == [text]


def test_text_over_limit_splits_on_paragraphs():
    p1 = "Parágrafo 1 sobre trocas. " * 20  # ~500 chars
    p2 = "Parágrafo 2 sobre devolução. " * 20  # ~580 chars
    p3 = "Parágrafo 3 sobre defeitos. " * 20  # ~560 chars
    text = f"{p1}\n\n{p2}\n\n{p3}"
    out = split_text(text, max_chars=800, overlap=0)
    assert len(out) >= 2
    # Cada chunk respeita max_chars
    for chunk in out:
        assert len(chunk) <= 800


def test_long_paragraph_splits_on_sentences():
    sentences = ". ".join([f"Frase {i} sobre um tópico" for i in range(50)])
    out = split_text(sentences, max_chars=200, overlap=0)
    assert len(out) > 1
    for chunk in out:
        assert len(chunk) <= 220  # margem por causa do split de sentença


def test_giant_unbreakable_string_force_cuts():
    """String sem quebras maior que max_chars é cortada na régua."""
    text = "x" * 2000
    out = split_text(text, max_chars=500, overlap=0)
    assert len(out) >= 4
    for chunk in out:
        assert len(chunk) <= 500


def test_overlap_preserves_context():
    p1 = "Primeiro parágrafo termina com a palavra ALPHA."
    p2 = "Segundo parágrafo começa após ALPHA."
    p3 = "Terceiro parágrafo continua sequência."
    text = f"{p1}\n\n{p2}\n\n{p3}"
    out = split_text(text, max_chars=70, overlap=20)
    assert len(out) >= 2
    # Cada chunk após o primeiro contém parte do anterior.
    for prev, curr in zip(out, out[1:]):
        # Pega ultimos 20 chars do prev e checa que esteja no curr
        tail = prev[-20:].strip()
        assert tail in curr or curr.startswith(prev[-15:].strip())


def test_overlap_zero_disables():
    p1 = "Parágrafo um curto."
    p2 = "Parágrafo dois curto."
    text = f"{p1}\n\n{p2}"
    out = split_text(text, max_chars=25, overlap=0)
    assert out == [p1, p2]


def test_default_chunking_realistic_doc():
    """Doc realista de FAQ com mistura de listas e parágrafos."""
    doc = """Política de Trocas

Você pode trocar qualquer produto até 7 dias após a compra,
desde que esteja sem uso e com a embalagem original.

Em caso de defeito, o prazo é de 30 dias.

Não trocamos:
- Produtos íntimos
- Produtos personalizados
- Produtos consumíveis abertos

Para iniciar, mande nota fiscal e foto do produto."""
    out = split_text(doc)
    assert len(out) >= 1
    full = " ".join(out)
    # Tudo importante deve aparecer pelo menos em algum chunk.
    assert "7 dias" in full
    assert "defeito" in full
    assert "30 dias" in full


def test_no_loss_of_content_minus_overlap():
    """Concat dos chunks (sem overlap) deve cobrir o doc inteiro."""
    parts = [f"Item {i} com texto suficiente pra forçar split." for i in range(20)]
    text = "\n\n".join(parts)
    out = split_text(text, max_chars=200, overlap=0)
    full = " ".join(out)
    for i in range(20):
        assert f"Item {i}" in full
