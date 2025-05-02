import execjs
import re
import itertools
from urllib.parse import urlparse, urljoin, parse_qsl
from .form import Form
from .utils import remove_url_params, contains_url, get_all_path_links, get_url_path
from bs4 import BeautifulSoup
import six

class Page(object):
    def __init__(self, response):
        assert hasattr(response, 'request')
        self.request = response.request
        self.headers = response.headers
        self.cookies = response.cookies
        self.status_code = response.status_code

        if 'text/html' in self.headers.get('content-type', ''):
            self.html = response.text
        else:
            self.html = ''

        self.document = BeautifulSoup(self.html, 'html.parser')
        self.response = response

    @property
    def url(self):
        return self.request.url

    @property
    def parsed_url(self):
        return urlparse(self.request.url)

    @property
    def url_parameters(self):
        _, _, query = self.url.partition("?")
        return parse_qsl(query)

    def get_forms(self, blacklist=[]):
        """Generator for all forms on the page."""
        for form in self.document.find_all('form'):
            form_obj = Form(self.url, form)
            if any(re.search(x, form.get('action') or "") for x in blacklist):
                continue
            yield form_obj

    def get_links(self, blacklist=[]):
        """
        Generator for all links on the page, yielding each URL only once.
        This function normalizes URLs by removing query parameters and
        uses a deduplication set to avoid redundant scanning.
        """
        seen = set()

        # Extract URLs from different elements
        refresh = [
            re.split("url=", m.get('content'), flags=re.IGNORECASE)[-1].strip("'")
            for m in self.document.find_all(attrs={'http-equiv': 'refresh'})
        ]
        ahref = [h.get('href') for h in self.document.find_all('a')]
        src_all = [s.get('src') for s in self.document.find_all(contains_url)]
        script_links = []

        # Extract potential URLs from JavaScript within <script> tags using ExecJS.
        for script in self.document.find_all('script'):
            # Matches patterns like: href = '/some/path' or location: "/test"
            urls = re.findall(
                r"""(?:href|url|location|u)\s*(?:=|:)\s*([a-zA-Z0-9_\/\.'"\-\+]+)(?:;|\s|$)""",
                script.text
            )
            for u in urls:
                try:
                    value_expr = u.strip()
                    # Ensure that the extracted value is properly quoted.
                    if not (value_expr.startswith("'") or value_expr.startswith('"')):
                        value_expr = "'" + value_expr + "'"
                    
                    # Compile and execute the JavaScript expression.
                    ctx = execjs.compile("function executeJs() { return " + value_expr + "; }")
                    js_url = ctx.call("executeJs")
                    if isinstance(js_url, six.string_types):
                        script_links.append(js_url)
                        continue
                except execjs.ProgramError:
                    # Skip this match if JavaScript evaluation fails.
                    continue
                script_links.append(u)

        # Combine links from various sources
        for ref in itertools.chain(refresh, ahref, src_all, script_links):
            if not ref:
                continue

            # Normalize the URL relative to the current page URL.
            url = urljoin(self.url, ref.strip())

            # Skip URLs that match any blacklist pattern.
            if any(re.search(x, url) for x in blacklist):
                continue

            # Canonicalize URL: remove query parameters if present.
            if urlparse(url).query:
                url = remove_url_params(url)

            # Deduplicate URLs.
            if url in seen:
                continue
            seen.add(url)
            yield url

            # Optionally generate additional links from the URL's path.
            # Extra path links are only yielded if they haven't been seen.
            for extra_link in get_all_path_links(url):
                norm_link = urljoin(url, extra_link)
                if urlparse(norm_link).query:
                    norm_link = remove_url_params(norm_link)
                if norm_link not in seen:
                    seen.add(norm_link)
                    yield norm_link
