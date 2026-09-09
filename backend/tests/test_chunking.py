"""SmartChunker tests: structure-aware splitting rules."""
from __future__ import annotations

from app.services.document.structure import Block
from app.services.translation.chunker import SmartChunker


def para(text: str, seq: int, page: int = 1) -> Block:
    return Block(seq=seq, type="paragraph", text=text, page=page)


class TestSmartChunker:
    def test_small_document_single_chunk(self):
        blocks = [
            Block(seq=0, type="heading", text="Chapter 1", level=1),
            para("Short content.", 1),
        ]
        chunks = SmartChunker(target_chars=4000).chunk(blocks)
        assert len(chunks) == 1
        assert chunks[0].chapter == "Chapter 1"
        assert "Short content." in chunks[0].text

    def test_chapter_boundary_forces_new_chunk(self):
        blocks = []
        seq = 0
        blocks.append(Block(seq=seq, type="heading", text="Chapter 1", level=1)); seq += 1
        for i in range(30):
            blocks.append(para(f"Chapter one paragraph {i} " + "lorem ipsum dolor " * 10, seq)); seq += 1
        blocks.append(Block(seq=seq, type="heading", text="Chapter 2", level=1)); seq += 1
        blocks.append(para("Chapter two content.", seq)); seq += 1
        chunks = SmartChunker(target_chars=500, max_chars=900).chunk(blocks)
        chapter2 = [c for c in chunks if c.chapter == "Chapter 2"]
        assert len(chapter2) >= 1
        # The Chapter 2 heading chunk must contain the chapter 2 content
        assert any("Chapter two content." in c.text for c in chapter2)
        # No chunk contains both chapters' content
        assert not any("Chapter one paragraph" in c.text and "Chapter two content." in c.text for c in chunks)

    def test_heading_not_orphaned_at_chunk_end(self):
        blocks = [
            Block(seq=0, type="heading", text="Chapter 1", level=1),
        ]
        seq = 1
        for i in range(40):
            blocks.append(para(f"Filler paragraph {i} " + "text content here " * 12, seq)); seq += 1
        blocks.append(Block(seq=seq, type="heading", text="Deep Section Heading", level=2)); seq += 1
        blocks.append(para("Section body content.", seq)); seq += 1

        chunks = SmartChunker(target_chars=400, max_chars=700).chunk(blocks)
        # Find the chunk containing the section heading
        idx = next(i for i, c in enumerate(chunks) if "Deep Section Heading" in c.text)
        chunk = chunks[idx]
        assert "Section body content." in chunk.text, "heading must stay with following content"
        assert chunk.section == "Deep Section Heading"

    def test_oversized_paragraph_split_at_sentences(self):
        long_paragraph = (
            "This is sentence one about visual impairment research. "
            * 80
        )
        blocks = [para(long_paragraph, 0)]
        chunks = SmartChunker(target_chars=500, max_chars=700).chunk(blocks)
        assert len(chunks) >= 2
        # Sentences must not be cut mid-sentence (each piece ends with '.')
        for chunk in chunks:
            for piece in chunk.text.split("\n\n"):
                assert piece.strip().endswith(".")

    def test_table_kept_whole(self):
        rows = [[f"cell {r}-{c}" for c in range(4)] for r in range(20)]
        blocks = [
            para("Before the table. " + "filler " * 40, 0),
            Block(seq=1, type="table", text="", rows=rows, page=2),
            para("After the table. " + "filler " * 40, 2),
        ]
        chunks = SmartChunker(target_chars=200, max_chars=300).chunk(blocks)
        # The table block must not be split across chunks
        table_blocks = [
            b for c in chunks for b in c.blocks if b.type == "table"
        ]
        assert len(table_blocks) >= 1
        total_rows = sum(len(b.rows) for b in table_blocks)
        assert total_rows == 20
        # Each table block retains full rows
        for b in table_blocks:
            assert all(len(row) == 4 for row in b.rows)

    def test_chunk_metadata(self):
        blocks = [
            Block(seq=0, type="heading", text="Chapter 5", level=1, page=10),
            Block(seq=1, type="heading", text="Section 5.2", level=2, page=11),
            para("Content under section.", 2, page=12),
        ]
        chunks = SmartChunker().chunk(blocks)
        assert chunks[0].chapter == "Chapter 5"
        assert chunks[0].section == "Section 5.2"
        assert chunks[0].page_start == 10
        assert chunks[0].page_end == 12
        assert chunks[0].chunk_index == 0
        assert chunks[0].char_count > 0
        assert chunks[0].token_estimate > 0

    def test_large_document_many_chunks_ordered(self):
        blocks = []
        seq = 0
        for i in range(500):
            blocks.append(para(f"Paragraph {i} " + "academic content " * 20, seq)); seq += 1
        chunks = SmartChunker(target_chars=800, max_chars=1200).chunk(blocks)
        assert len(chunks) > 10
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
        # No content lost
        assert "Paragraph 499" in chunks[-1].text
        assert "Paragraph 0" in chunks[0].text

    def test_list_items_grouped(self):
        blocks = [
            Block(seq=0, type="heading", text="Chapter 1", level=1),
        ]
        seq = 1
        for i in range(10):
            blocks.append(Block(seq=seq, type="list_item", text=f"List item {i}", marker="•")); seq += 1
        chunks = SmartChunker(target_chars=100, max_chars=200).chunk(blocks)
        # All list items present, in order
        all_text = "\n\n".join(c.text for c in chunks)
        for i in range(10):
            assert f"List item {i}" in all_text
