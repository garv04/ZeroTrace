#!/usr/bin/python
from .utils import get_url_host, remove_url_params
from .client import Client, NotAPage, RedirectedToExternal

from collections import deque
from re import search

class Crawler(object):
    def __init__(self, target, client=None, whitelist=None, blacklist=set(), additional_pages=[]):
        self.target = target

        if whitelist is None:
            self.whitelist = { get_url_host(target) }
        else:
            self.whitelist = whitelist
            self.whitelist.add(get_url_host(target))

        if client is None:
            self.client = Client()
        else:
            self.client = client

        if additional_pages:
            self.to_visit_links = deque(additional_pages)
        else:
            self.to_visit_links = deque()

        self.blacklist = blacklist
        self.visited_links  = set()
        self.count = 0

    def __iter__(self):
        # Add the target URL to the deque in its canonical form.
        self.to_visit_links.append(self.target)

        while self.to_visit_links:
            url = self.to_visit_links.pop()

            # Remove any fragment (hashbang) and canonicalize the URL by removing query parameters.
            url_without_hashbang, _, _ = url.partition("#")
            canonical_url = remove_url_params(url_without_hashbang)

            # Skip if the URL's host is not in our whitelist.
            if get_url_host(canonical_url) not in self.whitelist:
                continue

            # Skip if the URL matches any pattern in the blacklist.
            if any(search(pattern, canonical_url) for pattern in self.blacklist):
                continue

            # Skip if we've already visited this URL.
            if canonical_url in self.visited_links:
                continue

            try:
                page = self.client.get(canonical_url, ignore_type=False)
            except (NotAPage, RedirectedToExternal):
                continue

            # Canonicalize the URL returned by the page.
            canonical_page_url = remove_url_params(page.url)
            if canonical_page_url in self.visited_links:
                continue

            # Mark this page as visited.
            self.visited_links.add(canonical_page_url)
            self.count += 1

            # Extend the queue with new links (also canonicalized).
            for link in page.get_links():
                link_canonical = remove_url_params(link)
                if link_canonical not in self.visited_links:
                    self.to_visit_links.append(link_canonical)

            yield page
