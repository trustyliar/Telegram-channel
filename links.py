"""Pure link helpers: find URLs, resolve short links, rebuild Amazon links with our tag."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import httpx

URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.I)
ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d|exec/obidos/ASIN)/([A-Z0-9]{10})(?:[/?]|$)", re.I)
SHORTENERS = {
    "amzn.to", "amzn.in", "a.co", "amzn.eu", "fkrt.cc", "fkrt.it", "fkrt.to",
    "bit.ly", "cutt.ly", "tinyurl.com", "t.co", "ltl.sh", "myntr.it", "ajiio.in",
    "linkredirect.in", "extp.in", "earnkaro.com", "ekaro.in", "bitli.in", "wishlink.com",
    "tinyurl.com", "is.gd", "rb.gy", "link.amazon",
}
SOURCE_JUNK_RE = re.compile(r"(https?://)?(t\.me|telegram\.(me|dog))/\S+|@\w{4,}", re.I)


def host(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def is_amazon(url: str) -> bool:
    h = host(url)
    return h.startswith("amazon.") or h.endswith(".amazon.in") or h.endswith(".amazon.com")


def extract_urls(text: str) -> list[str]:
    seen, out = set(), []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(".,;")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def asin_from_url(url: str) -> str | None:
    m = ASIN_RE.search(urlparse(url).path + "/")
    return m.group(1).upper() if m else None


def build_amazon_url(asin: str, tag: str, domain: str = "amazon.in") -> str:
    return f"https://www.{domain}/dp/{asin}?tag={tag}"


DROP_PARAMS = {"tag", "ascsubtag", "linkcode", "ref", "ref_", "btn_ref", "btn_type", "qid", "ds", "dc", "th", "psc",
               "pd_rd_r", "pd_rd_w", "pd_rd_wg", "pd_rd_i", "content-id",
               "pf_rd_r", "pf_rd_p", "pf_rd_s", "pf_rd_t", "pf_rd_i", "pf_rd_m"}


def tag_amazon_url(url: str, tag: str):
    """Return (our_tagged_url, dedup_key). Product pages -> clean /dp/ link; search/deal pages -> same page, our tag."""
    asin = asin_from_url(url)
    if asin:
        return build_amazon_url(asin, tag), asin
    parts = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in DROP_PARAMS]
    key = "url:" + parts.path + "?" + urlencode(sorted(q))
    q.append(("tag", tag))
    return urlunsplit(("https", parts.netloc, parts.path, urlencode(q, safe=":,"), "")), key


async def resolve(url: str, client: httpx.AsyncClient, max_hops: int = 6) -> str:
    """Follow redirects (short links) manually and return the final URL.
    Stops early once an Amazon URL with an ASIN is reached (no need to load the page)."""
    cur = url
    for _ in range(max_hops):
        if host(cur) not in SHORTENERS:
            return cur  # real Amazon page or unknown final domain: no need to fetch
        try:
            r = await client.get(cur, follow_redirects=False, timeout=10)
        except httpx.HTTPError:
            return cur
        loc = r.headers.get("location")
        if r.status_code in (301, 302, 303, 307, 308) and loc:
            cur = str(httpx.URL(cur).join(loc))
        else:
            return cur
    return cur


async def rewrite_text(text: str, tag: str, client: httpx.AsyncClient, extra_urls: list[str] | None = None):
    """Return (new_text, asins, other_links). Replaces every Amazon link in `text` with our tagged link."""
    urls = extract_urls(text)
    for u in extra_urls or []:
        if u not in urls:
            urls.append(u)
    asins, others = [], []
    new = text
    for u in urls:
        if host(u) in ("t.me", "telegram.me", "telegram.dog"):
            continue
        final = await resolve(u, client)
        if is_amazon(final):
            new_url, key = tag_amazon_url(final, tag)
            asins.append(key)
            new = new.replace(u, new_url)
        else:
            others.append(final)
    new = SOURCE_JUNK_RE.sub("", new)
    new = re.sub(r"[ \t]+\n", "\n", new)
    new = re.sub(r"\n{3,}", "\n\n", new).strip()
    return new, asins, others


def chunk_text(text: str, limit: int = 4000) -> list[str]:
    """Split text into pieces under Telegram's 4096-char message limit, on blank lines, then lines."""
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for block in text.split("\n\n"):
        for piece in ([block] if len(block) <= limit else block.split("\n")):
            sep = "\n\n" if cur else ""
            if len(cur) + len(sep) + len(piece) > limit and cur:
                chunks.append(cur)
                cur = piece
            else:
                cur += sep + piece
    if cur:
        chunks.append(cur)
    return chunks
