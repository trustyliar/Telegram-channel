import asyncio
import httpx
from links import asin_from_url, build_amazon_url, extract_urls, rewrite_text, is_amazon


def test_asin():
    assert asin_from_url("https://www.amazon.in/Some-Name/dp/B0ABCDE123/ref=sr_1?tag=other-21") == "B0ABCDE123"
    assert asin_from_url("https://www.amazon.in/gp/product/B0ABCDE123") == "B0ABCDE123"
    assert asin_from_url("https://www.amazon.in/deals") is None


def test_build():
    assert build_amazon_url("B0ABCDE123", "me-21") == "https://www.amazon.in/dp/B0ABCDE123?tag=me-21"


def test_is_amazon():
    assert is_amazon("https://www.amazon.in/dp/B0ABCDE123")
    assert not is_amazon("https://www.flipkart.com/x")


def test_rewrite():
    text = ("Loot! Boat Earbuds 70% off\nhttps://www.amazon.in/boAt/dp/B0ABCDE123?tag=rival-21&th=1\n"
            "Join @rivaldeals https://t.me/rivaldeals\nhttps://www.flipkart.com/p/item")
    async def go():
        async with httpx.AsyncClient() as c:
            return await rewrite_text(text, "me-21", c)
    new, asins, others = asyncio.run(go())
    assert asins == ["B0ABCDE123"]
    assert "rival-21" not in new and "tag=me-21" in new
    assert "rivaldeals" not in new
    assert others == ["https://www.flipkart.com/p/item"]


def test_search_page():
    from links import tag_amazon_url
    u = "https://www.amazon.in/s?k=sparx&rh=n:157,p_6:A1&s=price-asc-rank&i=shoes&tag=dealztrendz-21&qid=99"
    new, key = tag_amazon_url(u, "me-21")
    assert "tag=me-21" in new and "dealztrendz" not in new and "qid" not in new
    assert "k=sparx" in new and "rh=n:157,p_6:A1" in new
    assert key.startswith("url:")


def test_chunk_and_strip():
    from links import chunk_text, tag_amazon_url
    text = "\n\n".join(f"line {i} " + "x" * 300 for i in range(30))
    parts = chunk_text(text)
    assert len(parts) > 1 and all(len(p) <= 4000 for p in parts)
    assert chunk_text("short") == ["short"]
    new, _ = tag_amazon_url("https://www.amazon.in/s?k=a&pd_rd_r=zzz&content-id=amzn1.sym.1&pf_rd_p=q", "me-21")
    assert "pd_rd_r" not in new and "content-id" not in new and "pf_rd_p" not in new and "k=a" in new
