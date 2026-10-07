"""
robots_compliance.py

NoobSync Knowledge Base AI — Week 3
Owner: Akshada (Security/CRM/Docs)
Used by: Anushka's URL scraper (Week 3, Task 1)

WHAT THIS DOES
--------------
Before the scraper ingests ANY page from ANY URL, it must go through this
module first. This module:

  1. Fetches and parses the site's robots.txt (cached per domain, so we
     don't re-fetch it on every single page).
  2. Rejects any URL path disallowed for our crawler's user-agent.
  3. Rate-limits requests: minimum 1 second between requests to the SAME
     domain (default, configurable).
  4. Hard-caps total pages crawled per session at 50 (default, configurable).

WHY THIS MATTERS
----------------
- Legal / ethical: ignoring robots.txt can be a ToS violation and, in some
  jurisdictions, has been used as evidence of unauthorized access.
- Practical: hammering a client's (or prospect's) website with rapid
  requests can get our scraper IP-banned, or worse, cause real load issues
  on their server — which looks terrible if we're trying to sell them a
  product built on scraping their own site.

HOW ANUSHKA PLUGS THIS IN
--------------------------
    from robots_compliance import CrawlSession

    session = CrawlSession(user_agent="NoobSyncBot/1.0", max_pages=50, min_delay=1.0)

    for url in urls_to_crawl:
        if not session.can_visit(url):
            continue  # disallowed by robots.txt, or page cap hit
        session.wait_if_needed(url)   # blocks just long enough to respect rate limit
        response = requests.get(url, headers={"User-Agent": session.user_agent})
        session.record_visit(url)
        # ... hand response.text to ingestion pipeline ...

That's the entire integration surface: can_visit(), wait_if_needed(), record_visit().
"""

import time
import urllib.request
import urllib.error
from urllib.parse import urlparse
from dataclasses import dataclass
from protego import Protego

# NOTE ON LIBRARY CHOICE:
# Python's stdlib `urllib.robotparser` does NOT correctly support wildcard
# patterns (e.g. "Disallow: /*/tree/") in Disallow/Allow rules — it was
# tested against GitHub's real robots.txt during development and silently
# allowed paths that should have been blocked. We use `protego` instead
# (the same robots.txt parser Scrapy uses in production), which correctly
# implements wildcards ("*") and end-of-string anchors ("$") per the
# de-facto robots.txt spec. Install: pip install protego


class CrawlLimitReached(Exception):
    """Raised when a crawl session hits its max_pages cap."""
    pass


@dataclass
class DomainState:
    """Tracks robots.txt parser + last-request time for one domain."""
    parser: Protego
    last_request_time: float = 0.0


class CrawlSession:
    """
    One instance = one crawl job (e.g. one call to ingest a given URL and
    its internal pages). Tracks robots.txt rules per domain, enforces a
    minimum delay between requests to the same domain, and caps total
    pages visited across the whole session.
    """

    def __init__(self, user_agent="NoobSyncBot/1.0", max_pages=50, min_delay=1.0,
                 robots_fetch_timeout=5):
        self.user_agent = user_agent
        self.max_pages = max_pages
        self.min_delay = min_delay
        self.robots_fetch_timeout = robots_fetch_timeout

        self._domains: dict[str, DomainState] = {}
        self.pages_visited = 0
        self.skipped_disallowed = []   # URLs rejected by robots.txt
        self.skipped_capped = []       # URLs rejected because max_pages was hit

    # ------------------------------------------------------------------
    # Internal: robots.txt fetch + cache (one fetch per domain per session)
    # ------------------------------------------------------------------
    def _get_domain_state(self, url: str) -> DomainState:
        domain = urlparse(url).netloc
        if domain not in self._domains:
            robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
            try:
                req = urllib.request.Request(
                    robots_url, headers={"User-Agent": self.user_agent}
                )
                with urllib.request.urlopen(req, timeout=self.robots_fetch_timeout) as resp:
                    robots_content = resp.read().decode("utf-8", errors="ignore")
                parser = Protego.parse(robots_content)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    # No robots.txt = allow everything (standard behavior)
                    parser = Protego.parse("")
                else:
                    print(f"[robots_compliance] WARNING: HTTP {e.code} fetching "
                          f"{robots_url} — defaulting to allow, flag for manual review.")
                    parser = Protego.parse("")
            except Exception as e:
                # Network error, timeout, malformed content, etc. Fail safe
                # by defaulting to allow-all, but LOG loudly so this domain
                # gets flagged for manual review rather than silently
                # crawled or silently skipped.
                print(f"[robots_compliance] WARNING: could not fetch/parse "
                      f"{robots_url} ({e}) — defaulting to allow, flag this "
                      f"domain for manual review.")
                parser = Protego.parse("")
            self._domains[domain] = DomainState(parser=parser)
        return self._domains[domain]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def can_visit(self, url: str) -> bool:
        """
        Returns True if this URL is safe to crawl right now:
          - allowed by the domain's robots.txt for our user-agent, AND
          - the session hasn't hit its max_pages cap yet.
        Does NOT consume a "page slot" or wait — call record_visit() after
        actually fetching the page.
        """
        if self.pages_visited >= self.max_pages:
            self.skipped_capped.append(url)
            return False

        state = self._get_domain_state(url)
        allowed = state.parser.can_fetch(url, self.user_agent)
        if not allowed:
            self.skipped_disallowed.append(url)
        return allowed

    def wait_if_needed(self, url: str) -> None:
        """
        Blocks (if necessary) so that at least `min_delay` seconds have
        passed since the last request to this URL's domain. Call this
        right before making the actual HTTP request.
        """
        state = self._get_domain_state(url)
        elapsed = time.time() - state.last_request_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)

    def record_visit(self, url: str) -> None:
        """
        Call this immediately after a request completes (success or not).
        Updates the rate-limit clock and the page counter. Raises
        CrawlLimitReached if this call pushes us over max_pages, so the
        caller's loop can stop cleanly.
        """
        state = self._get_domain_state(url)
        state.last_request_time = time.time()
        self.pages_visited += 1
        if self.pages_visited > self.max_pages:
            raise CrawlLimitReached(
                f"Crawl session exceeded max_pages={self.max_pages}"
            )

    def summary(self) -> dict:
        """Quick report for logging / the security audit / the playbook."""
        return {
            "pages_visited": self.pages_visited,
            "max_pages": self.max_pages,
            "disallowed_skipped": len(self.skipped_disallowed),
            "capped_skipped": len(self.skipped_capped),
            "domains_seen": list(self._domains.keys()),
        }


# ==========================================================================
# DEMO / SELF-TEST
# Proves the "Done When": scraper rejects disallowed paths, doesn't hammer
# servers. Run this file directly: `python robots_compliance.py`
# ==========================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("TEST 1: robots.txt is fetched and disallowed paths are rejected")
    print("=" * 70)

    # github.com's robots.txt disallows a number of paths (e.g. /search,
    # /*/search, /*/tree/main/*/*.js etc). We use a couple of known
    # disallowed patterns plus the homepage (which IS allowed).
    session = CrawlSession(user_agent="NoobSyncBot/1.0", max_pages=50, min_delay=1.0)

    test_urls = [
        "https://github.com/",                                    # ALLOWED
        "https://github.com/anthropics/claude-code/tree/main",    # DISALLOWED (/*/tree/)
        "https://github.com/gist/",                                # DISALLOWED (/gist/)
    ]

    for url in test_urls:
        result = session.can_visit(url)
        print(f"  {url:45s} -> {'ALLOWED' if result else 'DISALLOWED'}")

    print()
    print("=" * 70)
    print("TEST 2: rate limiting — 3 requests to same domain, min_delay=1.0s")
    print("=" * 70)
    rl_session = CrawlSession(user_agent="NoobSyncBot/1.0", max_pages=50, min_delay=1.0)
    start = time.time()
    for i in range(3):
        url = "https://github.com/"
        if rl_session.can_visit(url):
            rl_session.wait_if_needed(url)
            rl_session.record_visit(url)
            print(f"  Request {i+1} completed at t={time.time()-start:.2f}s")
    total_time = time.time() - start
    print(f"  Total time for 3 requests: {total_time:.2f}s "
          f"(expected >= ~2.0s due to 1s delay between requests 1->2 and 2->3)")
    assert total_time >= 1.9, "Rate limiting does not appear to be working!"
    print("  PASS: rate limiting enforced correctly.")

    print()
    print("=" * 70)
    print("TEST 3: max_pages cap is enforced")
    print("=" * 70)
    capped_session = CrawlSession(user_agent="NoobSyncBot/1.0", max_pages=2, min_delay=0.0)
    urls = ["https://github.com/", "https://github.com/about", "https://github.com/pricing"]
    for url in urls:
        allowed = capped_session.can_visit(url)
        print(f"  {url:40s} -> {'ALLOWED' if allowed else 'REJECTED (cap or robots.txt)'}")
        if allowed:
            capped_session.record_visit(url)
    print(f"  Pages visited: {capped_session.pages_visited} (max_pages={capped_session.max_pages})")
    assert capped_session.pages_visited <= capped_session.max_pages
    print("  PASS: max_pages cap enforced correctly.")

    print()
    print("=" * 70)
    print("SESSION SUMMARY (session 1)")
    print("=" * 70)
    print(session.summary())