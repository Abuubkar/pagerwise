import pytest

from pagerwise_api.chunking import chunk_markdown, parse_document


def words(text: str) -> int:
    """Stand-in tokenizer: one token per word, so tests run offline and sizes are easy to reason about."""
    return len(text.split())


def para(n: int, word: str = "lorem") -> str:
    return " ".join([word] * n)


def test_heading_path_is_kept_and_bare_parent_headings_carry_into_the_chunk():
    body = f"# Ledger\n\n## Pool\n\n### Sizing\n\n{para(20)}\n"
    [chunk] = chunk_markdown(body, words, min_tokens=5, max_tokens=50)
    assert chunk.heading_path == "Ledger > Pool > Sizing"
    assert chunk.text.startswith("# Ledger\n\n## Pool\n\n### Sizing\n\nlorem")
    # the count includes the path prefix: 3 names + 2 separators, then 3 heading lines (2 each) + 20 words
    assert chunk.token_count == 31


def test_no_chunk_over_the_limit_and_nothing_dropped():
    body = "# Doc\n\n" + "\n\n".join(f"## S{i}\n\n{para(30, f'w{i}')}\n\n{para(30, f'v{i}')}" for i in range(6))
    chunks = chunk_markdown(body, words, min_tokens=40, max_tokens=80)
    assert all(c.token_count <= 80 for c in chunks)
    joined = " ".join(c.text for c in chunks)
    for i in range(6):
        assert joined.count(f"w{i}") == 30 and joined.count(f"v{i}") == 30


def test_small_sections_merge_under_their_common_heading():
    body = f"# Payments\n\n## Symptoms\n\n{para(10)}\n\n## Causes\n\n{para(10)}\n"
    [chunk] = chunk_markdown(body, words, min_tokens=40, max_tokens=80)
    assert chunk.heading_path == "Payments"
    assert "## Symptoms" in chunk.text and "## Causes" in chunk.text


def test_code_block_is_never_split_even_with_blank_lines_and_hashes_inside():
    code = "```bash\n# not a heading\nledgerctl pool stats\n\n" + para(30, "arg") + "\n```"
    body = f"# Doc\n\n## Steps\n\n{para(40)}\n\n{code}\n\n{para(40)}\n"
    chunks = chunk_markdown(body, words, min_tokens=10, max_tokens=60)
    holding = [c for c in chunks if "ledgerctl" in c.text]
    assert len(holding) == 1 and code in holding[0].text
    assert all(c.heading_path == "Doc > Steps" for c in chunks)  # the comment line didn't become a heading


def test_code_block_over_the_limit_is_an_error_not_a_split():
    body = "# Doc\n\n```\n" + para(100) + "\n```\n"
    with pytest.raises(ValueError, match="can't be split"):
        chunk_markdown(body, words, min_tokens=10, max_tokens=60)


def test_frontmatter_gives_service_and_title():
    doc = parse_document("---\nservice: ledger\n---\n# Ledger: pool\n\nText.\n")
    assert (doc.service, doc.title) == ("ledger", "Ledger: pool")
    assert doc.body.startswith("# Ledger: pool")
