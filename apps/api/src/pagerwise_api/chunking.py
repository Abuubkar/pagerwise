"""Markdown documents to retrieval chunks: split on headings, keep the heading path, never split a code block."""

import re
from collections.abc import Callable
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
PATH_SEP = " > "


@dataclass
class Section:
    heading_path: list[str]
    blocks: list[str]  # paragraphs, lists, code blocks; each kept whole where it fits


@dataclass
class ChunkDraft:
    heading_path: str
    text: str
    token_count: int


@dataclass
class ParsedDocument:
    service: str
    title: str
    body: str


def parse_document(markdown: str) -> ParsedDocument:
    """Reads the `service:` frontmatter line and the first H1. Both are required."""
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        raise ValueError("document has no frontmatter")
    service = re.search(r"^service:\s*(\S+)\s*$", match.group(1), re.MULTILINE)
    if not service:
        raise ValueError("frontmatter has no service")
    body = markdown[match.end() :]
    title = next((m.group(2) for line in body.splitlines() if (m := HEADING_RE.match(line)) and m.group(1) == "#"), None)
    if not title:
        raise ValueError("document has no H1 title")
    return ParsedDocument(service=service.group(1), title=title, body=body)


def parse_sections(body: str) -> list[Section]:
    """One section per heading, with the heading line as its first block. Headings inside code fences are code."""
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    block: list[str] = []
    in_fence = False

    def end_block() -> None:
        if block and any(line.strip() for line in block):
            if not sections:  # text before the first heading
                sections.append(Section(heading_path=[], blocks=[]))
            sections[-1].blocks.append("\n".join(block).strip("\n"))
        block.clear()

    for line in body.splitlines():
        if FENCE_RE.match(line):
            if not in_fence:
                end_block()
            block.append(line)
            in_fence = not in_fence
            if not in_fence:
                end_block()
            continue
        if in_fence:
            block.append(line)
            continue
        heading = HEADING_RE.match(line)
        if heading:
            end_block()
            level = len(heading.group(1))
            stack = [(lvl, name) for lvl, name in stack if lvl < level] + [(level, heading.group(2))]
            sections.append(Section(heading_path=[name for _, name in stack], blocks=[line]))
        elif not line.strip():
            end_block()
        else:
            block.append(line)
    if in_fence:
        raise ValueError("unclosed code fence")
    end_block()
    return sections


def embed_text(heading_path: str, text: str) -> str:
    """What the embedding model sees: the heading path gives a short section its context."""
    return f"{heading_path}\n\n{text}" if heading_path else text


def chunk_markdown(
    body: str, count_tokens: Callable[[str], int], min_tokens: int = 300, max_tokens: int = 500
) -> list[ChunkDraft]:
    """Each section becomes one piece, or several if it's over max_tokens (split between blocks). A piece then
    merges into the chunk before it when either is under min_tokens and the merge stays within max_tokens, so small
    sections don't become thin chunks. Token counts include the heading path prefix (see embed_text)."""

    def draft(path: list[str], blocks: list[str]) -> ChunkDraft:
        joined, text = PATH_SEP.join(path), "\n\n".join(blocks)
        return ChunkDraft(heading_path=joined, text=text, token_count=count_tokens(embed_text(joined, text)))

    pieces: list[tuple[list[str], list[str]]] = []
    carried: list[str] = []  # headings with no text of their own ("## Likely causes" right above "### ...")
    for section in parse_sections(body):
        if len(section.blocks) == 1 and HEADING_RE.match(section.blocks[0]):
            carried.append(section.blocks[0])
            continue
        current: list[str] = []
        blocks, carried = [*carried, *section.blocks], []
        for block in blocks:
            for part in _fit_block(block, section.heading_path, count_tokens, max_tokens):
                if current and draft(section.heading_path, [*current, part]).token_count > max_tokens:
                    pieces.append((section.heading_path, current))
                    current = []
                current.append(part)
        if current:
            pieces.append((section.heading_path, current))
    if carried:  # a document ending in bare headings keeps them rather than dropping text
        pieces.append(([], carried))

    chunks: list[tuple[list[str], list[str]]] = []
    for path, blocks in pieces:
        if chunks:
            prev_path, prev_blocks = chunks[-1]
            merged_path = _common_prefix(prev_path, path)
            either_small = min(draft(prev_path, prev_blocks).token_count, draft(path, blocks).token_count) < min_tokens
            if either_small and draft(merged_path, [*prev_blocks, *blocks]).token_count <= max_tokens:
                chunks[-1] = (merged_path, [*prev_blocks, *blocks])
                continue
        chunks.append((path, blocks))
    return [draft(path, blocks) for path, blocks in chunks]


def _fit_block(block: str, path: list[str], count_tokens: Callable[[str], int], max_tokens: int) -> list[str]:
    """A block that fits is returned whole. An oversized code block is an error (splitting code makes both halves
    useless); an oversized paragraph is split on line breaks, then on words."""
    joined = PATH_SEP.join(path)
    if count_tokens(embed_text(joined, block)) <= max_tokens:
        return [block]
    if FENCE_RE.match(block):
        raise ValueError(f"code block under '{joined}' is over {max_tokens} tokens and can't be split")
    units = block.split("\n") if "\n" in block else block.split(" ")
    sep = "\n" if "\n" in block else " "
    parts: list[str] = []
    current: list[str] = []
    for unit in units:
        if current and count_tokens(embed_text(joined, sep.join([*current, unit]))) > max_tokens:
            parts.append(sep.join(current))
            current = []
        current.append(unit)
    if current:
        parts.append(sep.join(current))
    # A single line can still be too long; split those on words.
    return [p for part in parts for p in (_fit_block(part, path, count_tokens, max_tokens) if part != block else [part])]


def _common_prefix(a: list[str], b: list[str]) -> list[str]:
    prefix: list[str] = []
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        prefix.append(x)
    return prefix
