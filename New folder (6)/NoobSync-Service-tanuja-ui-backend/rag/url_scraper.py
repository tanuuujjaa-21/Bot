from ssrf_protection import is_safe_url, SSRFValidationError
from robots_compliance import CrawlSession
session = CrawlSession(
    user_agent="NoobSyncBot/1.0",
    max_pages=50,
    min_delay=1.0
)
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# --- Security audit additions (Akshada, Week 3 Task 2 closeout) -----------
# Max size for a single page's response body. Protects against a
# malicious/misconfigured server sending an extremely large response and
# exhausting memory. 10MB is generous for a normal web page — real pages
# are typically well under 1MB of HTML.
MAX_PAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# Rolling cap on total extracted text across the whole crawl, so even a
# scrape that legitimately visits all 50 allowed pages can't accumulate
# unbounded memory if every page happens to be large. ~5MB of plain text
# is already far more than the RAG ingestion pipeline needs from a single
# source.
MAX_TOTAL_TEXT_CHARS = 5_000_000
# ---------------------------------------------------------------------------


def fetch_page(url):
    print(f"\nFetching: {url}")

    try:
        # SSRF Protection
        is_safe_url(url)

        # robots.txt Protection
        allowed = session.can_visit(url)
        print(f"can_visit = {allowed}")

        if not allowed:
            print("Blocked by robots.txt or crawl limit")
            print(session.summary())
            return None
        
        session.wait_if_needed(url)

        # Stream the response so we can enforce a hard size cap instead of
        # trusting the server's Content-Length header (a malicious server
        # could omit it or lie about it) and instead of buffering an
        # arbitrarily large body into memory before we get a chance to check.
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": session.user_agent},
            stream=True,
        )

        session.record_visit(url)

        print("Status Code:", response.status_code)

        if response.status_code != 200:
            print("Failed to fetch page.")
            response.close()
            return None

        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_PAGE_SIZE_BYTES:
            print(f"Rejected: Content-Length {content_length} exceeds "
                  f"{MAX_PAGE_SIZE_BYTES} byte cap")
            response.close()
            return None

        # Read in chunks and enforce the cap ourselves too, in case
        # Content-Length is missing or understated.
        downloaded = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            downloaded.extend(chunk)
            if len(downloaded) > MAX_PAGE_SIZE_BYTES:
                print(f"Rejected: response body exceeded {MAX_PAGE_SIZE_BYTES} "
                      f"byte cap while streaming")
                response.close()
                return None

        return downloaded.decode(response.encoding or "utf-8", errors="ignore")

    except SSRFValidationError as e:
        print(f"Rejected unsafe URL: {url} ({e})")
        return None
    
    except Exception as e:
        print("Error:", e)
        return None


def extract_text(html):
    soup = BeautifulSoup(html, "html.parser")

    # Strip script/style as before, PLUS other content that shouldn't reach
    # the RAG pipeline: noscript blocks, and anything explicitly hidden via
    # inline style or the "hidden" attribute. Hidden text is a known vector
    # for indirect prompt injection — a malicious page can include text like
    # "ignore previous instructions..." in a div styled display:none, which
    # a naive scraper would still extract even though no human visitor ever
    # sees it. Stripping this before it reaches the LLM closes that gap.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    for tag in soup.find_all(hidden=True):
        if tag.decomposed:
            continue
        tag.decompose()

    for tag in soup.find_all(style=True):
        if tag.decomposed:
            continue
        style_value = tag.get("style", "").replace(" ", "").lower()
        if "display:none" in style_value or "visibility:hidden" in style_value:
            tag.decompose()

    text = soup.get_text(separator="\n")

    lines = [line.strip() for line in text.splitlines()]
    clean_text = "\n".join(line for line in lines if line)

    return clean_text


def get_internal_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")

    links = set()

    for a in soup.find_all("a", href=True):
        full_url = urljoin(base_url, a["href"])

        if urlparse(full_url).netloc == urlparse(base_url).netloc:
            links.add(full_url)

    return links


def scrape_website(url):
    html = fetch_page(url)

    if not html:
        return "Could not fetch website."

    all_text = extract_text(html)

    print("\nFinding internal links...")
    links = get_internal_links(html, url)
    print(f"Found {len(links)} internal links.")

    max_pages = 10
    for index, link in enumerate(sorted(links)):
        if index >= max_pages:
            print(f"Reached maximum of {max_pages} pages.")
            break

        # Enforce the aggregate text cap across the whole crawl, not just
        # per-page — see MAX_TOTAL_TEXT_CHARS note above.
        if len(all_text) >= MAX_TOTAL_TEXT_CHARS:
            print(f"Stopping: total extracted text reached "
                  f"{MAX_TOTAL_TEXT_CHARS} char cap")
            break

        print(f"Scraping: {link}")

        page_html = fetch_page(link)

        if page_html:
            all_text += "\n\n" + extract_text(page_html)

    return all_text


if __name__ == "__main__":
    url = "https://books.toscrape.com/"

    text = scrape_website(url)

    print("\n================ OUTPUT ================\n")
    print(text)
