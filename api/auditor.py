import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from typing import Dict, List, Tuple, Any
import socket
from datetime import datetime


class WebsiteAuditor:
    """Core website audit engine for SEO, CWV, UX, and Conversion analysis."""

    def __init__(self, timeout=30):
        self.timeout = timeout
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.redirect_chain = []
        self.response_headers = {}
        self.status_code = 200
        self.page_size = 0

    def _is_private_ip(self, hostname: str) -> bool:
        """Check if hostname resolves to private IP (SSRF protection)."""
        try:
            ip = socket.gethostbyname(hostname)
            # Private IP ranges
            if ip.startswith('127.') or ip.startswith('192.168.') or ip.startswith('10.'):
                return True
            if ip.startswith('172.'):
                second = int(ip.split('.')[1])
                if 16 <= second <= 31:
                    return True
            if ip.startswith('169.254.'):  # Link-local
                return True
            return False
        except:
            return False

    def _create_session(self, credentials: Dict = None) -> requests.Session:
        """Create an HTTP session, optionally with authentication."""
        session = requests.Session()
        session.headers.update(self.headers)

        if credentials:
            username = credentials.get('username', '')
            password = credentials.get('password', '')
            if username and password:
                # Try HTTP Basic Auth first
                session.auth = (username, password)

        return session

    def _try_form_login(self, session: requests.Session, url: str, credentials: Dict) -> bool:
        """
        Attempt form-based login by finding login forms on the page.
        Returns True if login appears successful.
        """
        try:
            username = credentials.get('username', '')
            password = credentials.get('password', '')

            # Common login URL patterns
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            login_paths = [
                '/login', '/signin', '/sign-in', '/auth/login',
                '/account/login', '/customer/account/login',  # Magento
                '/wp-login.php',  # WordPress
                '/user/login',  # Drupal
                '/admin',
            ]

            login_url = None
            login_page_html = None

            for path in login_paths:
                try:
                    test_url = base_url + path
                    resp = session.get(test_url, timeout=10, allow_redirects=True, verify=True)
                    if resp.status_code == 200 and ('password' in resp.text.lower()):
                        login_url = test_url
                        login_page_html = resp.text
                        break
                except:
                    continue

            if not login_url or not login_page_html:
                return False

            # Parse login form
            soup = BeautifulSoup(login_page_html, 'lxml')
            forms = soup.find_all('form')

            for form in forms:
                # Look for password field in form
                pwd_input = form.find('input', {'type': 'password'})
                if not pwd_input:
                    continue

                # Get form action
                action = form.get('action', login_url)
                if action and not action.startswith('http'):
                    action = urljoin(login_url, action)

                # Build form data
                form_data = {}
                for inp in form.find_all('input'):
                    name = inp.get('name', '')
                    if not name:
                        continue
                    inp_type = inp.get('type', 'text').lower()

                    if inp_type == 'password':
                        form_data[name] = password
                    elif inp_type in ('text', 'email'):
                        form_data[name] = username
                    elif inp_type == 'hidden':
                        form_data[name] = inp.get('value', '')
                    elif inp_type == 'submit':
                        form_data[name] = inp.get('value', 'Submit')

                # Submit the form
                try:
                    resp = session.post(
                        action or login_url,
                        data=form_data,
                        timeout=15,
                        allow_redirects=True,
                        verify=True
                    )
                    # Check if login succeeded (no login form in response)
                    if resp.status_code == 200 and 'password' not in resp.text.lower()[:5000]:
                        return True
                except:
                    continue

            return False
        except:
            return False

    def fetch_page(self, url: str, credentials: Dict = None) -> Tuple[str, Dict, int, List[str], str]:
        """
        Fetch a webpage with SSRF protection and timeout.
        Supports optional authentication via credentials dict.
        Returns: (html_content, response_headers, status_code, redirect_chain, error_msg)
        """
        if not url.startswith('http'):
            url = 'https://' + url

        # SSRF protection
        parsed = urlparse(url)
        if self._is_private_ip(parsed.hostname or ''):
            return '', {}, 0, [], 'SSRF Protection: Private IP address detected'

        self.redirect_chain = []
        self.response_headers = {}
        self.status_code = 200

        try:
            session = self._create_session(credentials)

            # If credentials provided, attempt form-based login first
            if credentials and credentials.get('username') and credentials.get('password'):
                self._try_form_login(session, url, credentials)

            response = session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
                verify=True
            )

            self.redirect_chain = [r.url for r in response.history] + [response.url]
            self.response_headers = dict(response.headers)
            self.status_code = response.status_code
            self.page_size = len(response.content)

            html = response.text
            return html, self.response_headers, self.status_code, self.redirect_chain, ''

        except requests.exceptions.Timeout:
            return '', {}, 0, self.redirect_chain, 'Timeout: Page took too long to load'
        except requests.exceptions.SSLError:
            return '', {}, 0, self.redirect_chain, 'SSL Error: Certificate validation failed'
        except requests.exceptions.ConnectionError:
            return '', {}, 0, self.redirect_chain, 'Connection Error: Unable to reach host'
        except Exception as e:
            return '', {}, 0, self.redirect_chain, f'Error: {str(e)}'

    def _fetch_resource(self, url: str, path: str) -> str:
        """Fetch secondary resources like robots.txt or sitemap.xml."""
        try:
            full_url = urljoin(url, path)
            parsed = urlparse(full_url)
            if self._is_private_ip(parsed.hostname or ''):
                return ''
            response = requests.get(full_url, headers=self.headers, timeout=5, verify=True)
            if response.status_code == 200:
                return response.text
        except:
            pass
        return ''

    def audit_seo(self, html: str, url: str, headers: Dict) -> List[Dict]:
        """Audit SEO parameters (25 checks)."""
        findings = []
        soup = BeautifulSoup(html, 'lxml')

        # 1. Title tag presence and length
        title = soup.find('title')
        if title and title.string:
            title_text = title.string.strip()
            score = 3 if 30 <= len(title_text) <= 60 else 2
            evaluation = 'Good' if score == 3 else 'Can be Improved'
            findings.append({
                'parameter': 'Title Tag',
                'category': 'Meta Tags',
                'evaluation': evaluation,
                'score': score,
                'max_score': 3,
                'impact': 'High',
                'remarks': f'Title length: {len(title_text)} chars. "{title_text[:50]}..."'
            })
        else:
            findings.append({
                'parameter': 'Title Tag',
                'category': 'Meta Tags',
                'evaluation': 'Bad',
                'score': 0,
                'max_score': 3,
                'impact': 'High',
                'remarks': 'Title tag is missing or empty'
            })

        # 2. Meta description presence and length
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            desc_text = meta_desc.get('content').strip()
            score = 3 if 120 <= len(desc_text) <= 160 else 2
            evaluation = 'Good' if score == 3 else 'Can be Improved'
            findings.append({
                'parameter': 'Meta Description',
                'category': 'Meta Tags',
                'evaluation': evaluation,
                'score': score,
                'max_score': 3,
                'impact': 'High',
                'remarks': f'Description length: {len(desc_text)} chars'
            })
        else:
            findings.append({
                'parameter': 'Meta Description',
                'category': 'Meta Tags',
                'evaluation': 'Bad',
                'score': 0,
                'max_score': 3,
                'impact': 'High',
                'remarks': 'Meta description is missing or empty'
            })

        # 3. Canonical tag
        canonical = soup.find('link', attrs={'rel': 'canonical'})
        findings.append({
            'parameter': 'Canonical Tag',
            'category': 'Meta Tags',
            'evaluation': 'Good' if canonical else 'Can be Improved',
            'score': 3 if canonical else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'Canonical: {canonical.get("href") if canonical else "Not present"}'
        })

        # 4. H1 count
        h1_tags = soup.find_all('h1')
        h1_count = len(h1_tags)
        if h1_count == 1:
            findings.append({
                'parameter': 'H1 Count',
                'category': 'Heading Structure',
                'evaluation': 'Good',
                'score': 3,
                'max_score': 3,
                'impact': 'High',
                'remarks': 'Exactly one H1 tag present'
            })
        elif h1_count == 0:
            findings.append({
                'parameter': 'H1 Count',
                'category': 'Heading Structure',
                'evaluation': 'Bad',
                'score': 0,
                'max_score': 3,
                'impact': 'High',
                'remarks': 'No H1 tags found on page'
            })
        else:
            findings.append({
                'parameter': 'H1 Count',
                'category': 'Heading Structure',
                'evaluation': 'Can be Improved',
                'score': 1,
                'max_score': 3,
                'impact': 'High',
                'remarks': f'Multiple H1 tags found: {h1_count}'
            })

        # 5. H2 and H3 presence
        h2_count = len(soup.find_all('h2'))
        h3_count = len(soup.find_all('h3'))
        findings.append({
            'parameter': 'H2/H3 Structure',
            'category': 'Heading Structure',
            'evaluation': 'Good' if h2_count > 0 else 'Can be Improved',
            'score': 3 if h2_count > 0 else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'H2: {h2_count}, H3: {h3_count}'
        })

        # 6. Meta robots
        meta_robots = soup.find('meta', attrs={'name': 'robots'})
        if meta_robots:
            content = meta_robots.get('content', '').upper()
            is_good = 'INDEX' in content and 'FOLLOW' in content
            findings.append({
                'parameter': 'Meta Robots',
                'category': 'Meta Tags',
                'evaluation': 'Good' if is_good else 'Can be Improved',
                'score': 3 if is_good else 2,
                'max_score': 3,
                'impact': 'High',
                'remarks': f'Content: {content}'
            })
        else:
            findings.append({
                'parameter': 'Meta Robots',
                'category': 'Meta Tags',
                'evaluation': 'Can be Improved',
                'score': 2,
                'max_score': 3,
                'impact': 'High',
                'remarks': 'Not explicitly set (defaults to index, follow)'
            })

        # 7. Schema.org JSON-LD
        ld_json = soup.find('script', attrs={'type': 'application/ld+json'})
        if ld_json:
            try:
                schema_data = json.loads(ld_json.string)
                has_placeholder = str(schema_data).lower().count('example') > 0
                findings.append({
                    'parameter': 'Schema.org JSON-LD',
                    'category': 'Structured Data',
                    'evaluation': 'Good' if not has_placeholder else 'Can be Improved',
                    'score': 3 if not has_placeholder else 2,
                    'max_score': 3,
                    'impact': 'Medium',
                    'remarks': f'Schema type: {schema_data.get("@type", "Unknown")}'
                })
            except:
                findings.append({
                    'parameter': 'Schema.org JSON-LD',
                    'category': 'Structured Data',
                    'evaluation': 'Can be Improved',
                    'score': 1,
                    'max_score': 3,
                    'impact': 'Medium',
                    'remarks': 'Invalid JSON-LD structure'
                })
        else:
            findings.append({
                'parameter': 'Schema.org JSON-LD',
                'category': 'Structured Data',
                'evaluation': 'Can be Improved',
                'score': 1,
                'max_score': 3,
                'impact': 'Medium',
                'remarks': 'No JSON-LD markup found'
            })

        # 8. Open Graph tags
        og_tags = {
            'og:title': soup.find('meta', attrs={'property': 'og:title'}),
            'og:description': soup.find('meta', attrs={'property': 'og:description'}),
            'og:image': soup.find('meta', attrs={'property': 'og:image'}),
            'og:url': soup.find('meta', attrs={'property': 'og:url'})
        }
        og_present = sum(1 for v in og_tags.values() if v)
        findings.append({
            'parameter': 'Open Graph Tags',
            'category': 'Social Meta',
            'evaluation': 'Good' if og_present >= 4 else 'Can be Improved' if og_present >= 2 else 'Bad',
            'score': 3 if og_present >= 4 else 2 if og_present >= 2 else 0,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{og_present}/4 OG tags present'
        })

        # 9. Twitter Card tags
        twitter_tags = {
            'twitter:card': soup.find('meta', attrs={'name': 'twitter:card'}),
            'twitter:title': soup.find('meta', attrs={'name': 'twitter:title'}),
            'twitter:description': soup.find('meta', attrs={'name': 'twitter:description'}),
            'twitter:image': soup.find('meta', attrs={'name': 'twitter:image'})
        }
        twitter_present = sum(1 for v in twitter_tags.values() if v)
        findings.append({
            'parameter': 'Twitter Card Tags',
            'category': 'Social Meta',
            'evaluation': 'Good' if twitter_present >= 3 else 'Can be Improved' if twitter_present >= 1 else 'Bad',
            'score': 3 if twitter_present >= 3 else 2 if twitter_present >= 1 else 0,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{twitter_present}/4 Twitter tags present'
        })

        # 10. Hreflang tags
        hreflang = soup.find_all('link', attrs={'rel': 'alternate'})
        findings.append({
            'parameter': 'Hreflang Tags',
            'category': 'Internationalization',
            'evaluation': 'Good' if hreflang else 'N/A',
            'score': 3 if hreflang else 0,
            'max_score': 3,
            'impact': 'Low',
            'remarks': f'{len(hreflang)} hreflang alternate links present'
        })

        # 11. robots.txt
        robots_content = self._fetch_resource(url, '/robots.txt')
        findings.append({
            'parameter': 'robots.txt',
            'category': 'Crawlability',
            'evaluation': 'Good' if robots_content else 'Can be Improved',
            'score': 3 if robots_content else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'robots.txt accessible' if robots_content else 'robots.txt not found'
        })

        # 12. XML Sitemap
        sitemap_content = self._fetch_resource(url, '/sitemap.xml')
        findings.append({
            'parameter': 'XML Sitemap',
            'category': 'Crawlability',
            'evaluation': 'Good' if sitemap_content else 'Can be Improved',
            'score': 3 if sitemap_content else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'XML sitemap found' if sitemap_content else 'XML sitemap not found'
        })

        # 13-18. Security Headers
        security_headers = {
            'HSTS': ('Strict-Transport-Security', 'High'),
            'CSP': ('Content-Security-Policy', 'High'),
            'X-Content-Type-Options': ('X-Content-Type-Options', 'High'),
            'X-Frame-Options': ('X-Frame-Options', 'High'),
            'Referrer-Policy': ('Referrer-Policy', 'Medium'),
            'Permissions-Policy': ('Permissions-Policy', 'Medium')
        }

        for header_name, (header_key, impact) in security_headers.items():
            is_present = header_key in headers
            findings.append({
                'parameter': f'{header_name} Header',
                'category': 'Security Headers',
                'evaluation': 'Good' if is_present else 'Can be Improved',
                'score': 3 if is_present else 1,
                'max_score': 3,
                'impact': impact,
                'remarks': f'Header present: {is_present}'
            })

        # 19. Internal links count
        internal_links = 0
        empty_anchors = 0
        domain = urlparse(url).netloc
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if href.startswith(('http://', 'https://')):
                if domain in href:
                    internal_links += 1
            elif href.startswith('/') or href.startswith('.'):
                internal_links += 1
            if not link.get_text(strip=True):
                empty_anchors += 1

        findings.append({
            'parameter': 'Internal Links',
            'category': 'Link Structure',
            'evaluation': 'Good' if internal_links > 10 else 'Can be Improved',
            'score': 3 if internal_links > 10 else 2 if internal_links > 0 else 0,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{internal_links} internal links, {empty_anchors} empty anchors'
        })

        # 20. External links with rel attributes
        external_links = 0
        external_with_rel = 0
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if href.startswith(('http://', 'https://')):
                if domain not in href:
                    external_links += 1
                    if link.get('rel'):
                        external_with_rel += 1

        findings.append({
            'parameter': 'External Links Rel Attributes',
            'category': 'Link Structure',
            'evaluation': 'Good' if external_with_rel == external_links and external_links > 0 else 'Can be Improved',
            'score': 3 if external_with_rel == external_links else 2 if external_with_rel > 0 else 1,
            'max_score': 3,
            'impact': 'Low',
            'remarks': f'{external_with_rel}/{external_links} external links with rel attributes'
        })

        # 21. Broken mailto/tel links
        broken_contact = 0
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if href.startswith('mailto:'):
                if '@' not in href:
                    broken_contact += 1
            elif href.startswith('tel:'):
                if not re.search(r'\d', href):
                    broken_contact += 1

        findings.append({
            'parameter': 'Broken Contact Links',
            'category': 'Link Structure',
            'evaluation': 'Good' if broken_contact == 0 else 'Bad',
            'score': 3 if broken_contact == 0 else 0,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{broken_contact} broken mailto/tel links' if broken_contact > 0 else 'No broken contact links'
        })

        # 22. Placeholder content detection
        placeholder_keywords = ['lorem ipsum', 'add text here', 'cta text', 'example.com', 'your company', 'your business']
        html_lower = html.lower()
        has_placeholder = sum(1 for keyword in placeholder_keywords if keyword in html_lower)

        findings.append({
            'parameter': 'Placeholder Content',
            'category': 'Content Quality',
            'evaluation': 'Good' if has_placeholder == 0 else 'Bad',
            'score': 3 if has_placeholder == 0 else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{has_placeholder} placeholder patterns detected' if has_placeholder > 0 else 'No placeholder content found'
        })

        # 23. Blog/content section
        blog_indicators = ['blog', 'articles', 'news', 'insights', 'resources']
        has_blog = any(indicator in html.lower() for indicator in blog_indicators)
        findings.append({
            'parameter': 'Blog/Content Section',
            'category': 'Content Quality',
            'evaluation': 'Good' if has_blog else 'Can be Improved',
            'score': 3 if has_blog else 1,
            'max_score': 3,
            'impact': 'Low',
            'remarks': 'Blog/content section indicators found' if has_blog else 'No blog section detected'
        })

        # 24. Alt text coverage
        images = soup.find_all('img')
        images_with_alt = sum(1 for img in images if img.get('alt'))
        alt_coverage = (images_with_alt / len(images) * 100) if images else 0

        findings.append({
            'parameter': 'Image Alt Text Coverage',
            'category': 'Accessibility',
            'evaluation': 'Good' if alt_coverage >= 80 else 'Can be Improved' if alt_coverage >= 50 else 'Bad',
            'score': 3 if alt_coverage >= 80 else 2 if alt_coverage >= 50 else 1 if images else 0,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{images_with_alt}/{len(images)} images have alt text ({alt_coverage:.0f}%)' if images else 'No images found'
        })

        # 25. Keyword positioning in title
        if title and title.string:
            title_text = title.string.lower()
            # Simple check: does first word(s) seem relevant (not just "Home" or generic)
            first_words = ' '.join(title_text.split()[:2])
            is_good = len(title_text.split()) > 2 and first_words not in ['home page', 'welcome to']
            findings.append({
                'parameter': 'Title Keyword Positioning',
                'category': 'Meta Tags',
                'evaluation': 'Good' if is_good else 'Can be Improved',
                'score': 3 if is_good else 2,
                'max_score': 3,
                'impact': 'Medium',
                'remarks': f'Title starts with: "{first_words}"'
            })

        return findings

    def audit_cwv(self, html: str, url: str, headers: Dict) -> List[Dict]:
        """Audit Core Web Vitals parameters (15 checks)."""
        findings = []
        soup = BeautifulSoup(html, 'lxml')

        # 1. HTML page size
        page_kb = self.page_size / 1024
        findings.append({
            'parameter': 'HTML Page Size',
            'category': 'Page Performance',
            'evaluation': 'Good' if page_kb < 100 else 'Can be Improved' if page_kb < 300 else 'Bad',
            'score': 3 if page_kb < 100 else 2 if page_kb < 300 else 1,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'Page size: {page_kb:.1f} KB'
        })

        # 2. Total image count and size estimation
        images = soup.find_all('img')
        image_count = len(images)
        estimated_image_size = image_count * 50  # Conservative estimate: 50KB per image

        findings.append({
            'parameter': 'Image Count',
            'category': 'Resources',
            'evaluation': 'Good' if image_count < 10 else 'Can be Improved',
            'score': 3 if image_count < 10 else 2,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{image_count} images found, ~{estimated_image_size}KB estimated'
        })

        # 3. Images without width/height (CLS risk)
        images_without_wh = sum(1 for img in images if not (img.get('width') and img.get('height')))
        findings.append({
            'parameter': 'Images Without Dimensions',
            'category': 'Performance',
            'evaluation': 'Good' if images_without_wh == 0 else 'Can be Improved' if images_without_wh < len(images)//2 else 'Bad',
            'score': 3 if images_without_wh == 0 else 2 if images_without_wh < len(images)//2 else 1,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{images_without_wh}/{image_count} images missing width/height'
        })

        # 4. Images without lazy loading
        images_without_lazy = sum(1 for img in images if not img.get('loading'))
        findings.append({
            'parameter': 'Images Without Lazy Loading',
            'category': 'Performance',
            'evaluation': 'Good' if images_without_lazy == 0 else 'Can be Improved',
            'score': 3 if images_without_lazy == 0 else 2,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{images_without_lazy}/{image_count} images without lazy loading'
        })

        # 5. PNG images that could be WebP
        png_images = sum(1 for img in images if 'png' in img.get('src', '').lower())
        findings.append({
            'parameter': 'PNG to WebP Optimization',
            'category': 'Image Optimization',
            'evaluation': 'Can be Improved' if png_images > 0 else 'Good',
            'score': 2 if png_images > 0 else 3,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{png_images} PNG images found (consider WebP conversion)'
        })

        # 6. CSS file count (external)
        css_files = soup.find_all('link', attrs={'rel': 'stylesheet'})
        css_count = len(css_files)
        findings.append({
            'parameter': 'External CSS Files',
            'category': 'Resources',
            'evaluation': 'Good' if css_count <= 3 else 'Can be Improved',
            'score': 3 if css_count <= 3 else 2,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{css_count} external CSS files'
        })

        # 7. JS file count (external)
        js_files = soup.find_all('script', attrs={'src': True})
        js_count = len(js_files)
        findings.append({
            'parameter': 'External JS Files',
            'category': 'Resources',
            'evaluation': 'Good' if js_count <= 5 else 'Can be Improved',
            'score': 3 if js_count <= 5 else 2,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{js_count} external JS files'
        })

        # 8. Inline CSS size
        inline_styles = soup.find_all('style')
        inline_css_content = ''.join(style.string or '' for style in inline_styles)
        inline_css_kb = len(inline_css_content) / 1024
        findings.append({
            'parameter': 'Inline CSS Size',
            'category': 'Code Quality',
            'evaluation': 'Good' if inline_css_kb < 10 else 'Can be Improved' if inline_css_kb < 30 else 'Bad',
            'score': 3 if inline_css_kb < 10 else 2 if inline_css_kb < 30 else 1,
            'max_score': 3,
            'impact': 'Low',
            'remarks': f'Inline CSS: {inline_css_kb:.1f} KB'
        })

        # 9. Inline JS size
        inline_scripts = soup.find_all('script', string=True)
        inline_js_content = ''.join(script.string or '' for script in inline_scripts)
        inline_js_kb = len(inline_js_content) / 1024
        findings.append({
            'parameter': 'Inline JS Size',
            'category': 'Code Quality',
            'evaluation': 'Good' if inline_js_kb < 20 else 'Can be Improved' if inline_js_kb < 50 else 'Bad',
            'score': 3 if inline_js_kb < 20 else 2 if inline_js_kb < 50 else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'Inline JS: {inline_js_kb:.1f} KB'
        })

        # 10. Render-blocking resources
        render_blocking = sum(1 for css in css_files if not css.get('media'))
        render_blocking += sum(1 for js in js_files if not js.get('async') and not js.get('defer'))
        findings.append({
            'parameter': 'Render-Blocking Resources',
            'category': 'Performance',
            'evaluation': 'Good' if render_blocking == 0 else 'Can be Improved',
            'score': 3 if render_blocking == 0 else 2,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{render_blocking} render-blocking resources'
        })

        # 11. Font loading (preload/display swap)
        font_tags = soup.find_all('link', attrs={'rel': 'preload'})
        font_preload = sum(1 for tag in font_tags if 'font' in tag.get('href', '').lower())
        findings.append({
            'parameter': 'Font Preloading',
            'category': 'Performance',
            'evaluation': 'Good' if font_preload > 0 else 'Can be Improved',
            'score': 3 if font_preload > 0 else 2,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{font_preload} fonts preloaded'
        })

        # 12. Cache-Control header optimization
        cache_control = headers.get('Cache-Control', '')
        if cache_control:
            findings.append({
                'parameter': 'Cache-Control Header',
                'category': 'Caching',
                'evaluation': 'Good' if 'max-age' in cache_control else 'Can be Improved',
                'score': 3 if 'max-age' in cache_control else 2,
                'max_score': 3,
                'impact': 'High',
                'remarks': f'Cache-Control: {cache_control[:50]}'
            })
        else:
            findings.append({
                'parameter': 'Cache-Control Header',
                'category': 'Caching',
                'evaluation': 'Bad',
                'score': 0,
                'max_score': 3,
                'impact': 'High',
                'remarks': 'Cache-Control header not set'
            })

        # 13. Compression (gzip/brotli)
        content_encoding = headers.get('Content-Encoding', '').lower()
        is_compressed = 'gzip' in content_encoding or 'br' in content_encoding
        findings.append({
            'parameter': 'Response Compression',
            'category': 'Caching',
            'evaluation': 'Good' if is_compressed else 'Can be Improved',
            'score': 3 if is_compressed else 1,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'Encoding: {content_encoding}' if is_compressed else 'No compression detected'
        })

        # 14. CDN detection
        cdn_indicators = ['cloudflare', 'cdn', 'akamai', 'fastly', 'cloudfront']
        server_header = headers.get('Server', '').lower()
        via_header = headers.get('Via', '').lower()
        has_cdn = any(indicator in server_header or indicator in via_header for indicator in cdn_indicators)
        findings.append({
            'parameter': 'CDN Detection',
            'category': 'Delivery',
            'evaluation': 'Good' if has_cdn else 'Can be Improved',
            'score': 3 if has_cdn else 2,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'CDN detected: {server_header[:30]}' if has_cdn else 'No CDN indicators detected'
        })

        # 15. Third-party script count
        third_party_scripts = 0
        domain = urlparse(url).netloc
        for script in js_files:
            src = script.get('src', '')
            if src and domain not in src:
                third_party_scripts += 1

        findings.append({
            'parameter': 'Third-Party Scripts',
            'category': 'Performance',
            'evaluation': 'Good' if third_party_scripts <= 3 else 'Can be Improved',
            'score': 3 if third_party_scripts <= 3 else 2,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{third_party_scripts} third-party scripts detected'
        })

        return findings

    def audit_ux(self, html: str, url: str) -> List[Dict]:
        """Audit UX/Usability parameters (20 checks)."""
        findings = []
        soup = BeautifulSoup(html, 'lxml')

        # 1. Viewport meta tag
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        findings.append({
            'parameter': 'Viewport Meta Tag',
            'category': 'Mobile',
            'evaluation': 'Good' if viewport else 'Bad',
            'score': 3 if viewport else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': 'Viewport meta tag present' if viewport else 'Missing viewport meta tag'
        })

        # 2. HTML lang attribute
        html_tag = soup.find('html')
        lang_attr = html_tag.get('lang') if html_tag else None
        findings.append({
            'parameter': 'HTML Lang Attribute',
            'category': 'Accessibility',
            'evaluation': 'Good' if lang_attr else 'Can be Improved',
            'score': 3 if lang_attr else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'Language: {lang_attr}' if lang_attr else 'Lang attribute missing'
        })

        # 3. Heading hierarchy
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        hierarchy_ok = True
        last_level = 0
        for heading in headings:
            level = int(heading.name[1])
            if level > last_level + 1:
                hierarchy_ok = False
                break
            last_level = level

        findings.append({
            'parameter': 'Heading Hierarchy',
            'category': 'Accessibility',
            'evaluation': 'Good' if hierarchy_ok else 'Can be Improved',
            'score': 3 if hierarchy_ok else 2,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'Proper heading hierarchy' if hierarchy_ok else 'Irregular heading nesting detected'
        })

        # 4. Skip navigation link
        skip_link = soup.find('a', string=re.compile(r'skip', re.I))
        findings.append({
            'parameter': 'Skip Navigation Link',
            'category': 'Accessibility',
            'evaluation': 'Good' if skip_link else 'Can be Improved',
            'score': 3 if skip_link else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'Skip link present' if skip_link else 'No skip navigation link found'
        })

        # 5. Form labels associated with inputs
        inputs = soup.find_all('input')
        labeled_inputs = 0
        for inp in inputs:
            input_id = inp.get('id')
            if input_id:
                label = soup.find('label', attrs={'for': input_id})
                if label:
                    labeled_inputs += 1

        findings.append({
            'parameter': 'Form Label Association',
            'category': 'Accessibility',
            'evaluation': 'Good' if labeled_inputs == len(inputs) else 'Can be Improved' if labeled_inputs > 0 else 'N/A',
            'score': 3 if labeled_inputs == len(inputs) else 2 if labeled_inputs > 0 else 0,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{labeled_inputs}/{len(inputs)} inputs have associated labels' if inputs else 'No inputs found'
        })

        # 6. Image alt text coverage %
        images = soup.find_all('img')
        images_with_alt = sum(1 for img in images if img.get('alt'))
        alt_coverage = (images_with_alt / len(images) * 100) if images else 100

        findings.append({
            'parameter': 'Image Alt Coverage %',
            'category': 'Accessibility',
            'evaluation': 'Good' if alt_coverage >= 80 else 'Can be Improved' if alt_coverage >= 50 else 'Bad',
            'score': 3 if alt_coverage >= 80 else 2 if alt_coverage >= 50 else 1,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{alt_coverage:.0f}% of images have alt text'
        })

        # 7. Empty anchor text links
        empty_anchors = sum(1 for link in soup.find_all('a') if not link.get_text(strip=True))
        findings.append({
            'parameter': 'Empty Anchor Text Links',
            'category': 'Accessibility',
            'evaluation': 'Good' if empty_anchors == 0 else 'Bad',
            'score': 3 if empty_anchors == 0 else 0,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{empty_anchors} empty anchor links found' if empty_anchors > 0 else 'No empty anchors'
        })

        # 8. Javascript: href links
        js_links = sum(1 for link in soup.find_all('a') if link.get('href', '').startswith('javascript:'))
        findings.append({
            'parameter': 'JavaScript Href Links',
            'category': 'Best Practices',
            'evaluation': 'Good' if js_links == 0 else 'Bad',
            'score': 3 if js_links == 0 else 0,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{js_links} javascript: href links' if js_links > 0 else 'No javascript: hrefs'
        })

        # 9. Mobile-friendly indicators
        has_viewport = bool(viewport)
        no_fixed_widths = 'width: 960px' not in html and 'width: 1024px' not in html
        responsive_indicators = has_viewport and no_fixed_widths
        findings.append({
            'parameter': 'Mobile-Friendly Indicators',
            'category': 'Mobile',
            'evaluation': 'Good' if responsive_indicators else 'Can be Improved',
            'score': 3 if responsive_indicators else 2,
            'max_score': 3,
            'impact': 'High',
            'remarks': 'Responsive design indicators present' if responsive_indicators else 'May not be fully responsive'
        })

        # 10. Navigation structure (nav element)
        nav_element = soup.find('nav')
        findings.append({
            'parameter': 'Navigation Structure',
            'category': 'Information Architecture',
            'evaluation': 'Good' if nav_element else 'Can be Improved',
            'score': 3 if nav_element else 2,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'Semantic nav element present' if nav_element else 'No semantic nav element'
        })

        # 11. Footer present with useful links
        footer = soup.find('footer')
        footer_links = len(footer.find_all('a')) if footer else 0
        findings.append({
            'parameter': 'Footer with Links',
            'category': 'Information Architecture',
            'evaluation': 'Good' if footer and footer_links > 0 else 'Can be Improved',
            'score': 3 if footer and footer_links > 0 else 2,
            'max_score': 3,
            'impact': 'Low',
            'remarks': f'Footer present with {footer_links} links' if footer else 'No footer element found'
        })

        # 12. Search functionality
        search_indicators = ['search', 'find', 'query'] + soup.find_all('input', attrs={'type': 'search'})
        has_search = any(indicator in html.lower() for indicator in ['search']) or len(soup.find_all('input', attrs={'type': 'search'})) > 0
        findings.append({
            'parameter': 'Search Functionality',
            'category': 'Navigation',
            'evaluation': 'Good' if has_search else 'Can be Improved',
            'score': 3 if has_search else 1,
            'max_score': 3,
            'impact': 'Low',
            'remarks': 'Search functionality detected' if has_search else 'No search box found'
        })

        # 13. 404 error handling (simulate)
        findings.append({
            'parameter': '404 Error Handling',
            'category': 'Error Handling',
            'evaluation': 'N/A',
            'score': 0,
            'max_score': 3,
            'impact': 'Low',
            'remarks': 'Cannot test 404 from homepage analysis'
        })

        # 14. Cookie notice
        cookie_indicators = ['cookie', 'consent', 'privacy policy']
        has_cookie_notice = any(indicator in html.lower() for indicator in cookie_indicators)
        findings.append({
            'parameter': 'Cookie Notice/Consent',
            'category': 'Legal/Compliance',
            'evaluation': 'Good' if has_cookie_notice else 'Can be Improved',
            'score': 3 if has_cookie_notice else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'Cookie/privacy notice indicators found' if has_cookie_notice else 'No cookie notice detected'
        })

        # 15. Readable font sizes
        inline_styles = soup.find_all(style=re.compile(r'font-size'))
        small_fonts = sum(1 for tag in inline_styles if 'font-size: 10px' in tag.get('style', '') or 'font-size: 11px' in tag.get('style', ''))
        findings.append({
            'parameter': 'Readable Font Sizes',
            'category': 'Readability',
            'evaluation': 'Good' if small_fonts == 0 else 'Can be Improved',
            'score': 3 if small_fonts == 0 else 2,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{small_fonts} very small font elements detected' if small_fonts > 0 else 'Font sizes appear readable'
        })

        # 16. Color contrast (simplified)
        findings.append({
            'parameter': 'Color Contrast Compliance',
            'category': 'Readability',
            'evaluation': 'Can be Improved',
            'score': 2,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'Cannot validate without pixel analysis; review manually'
        })

        # 17. Social media links
        social_platforms = ['facebook', 'twitter', 'instagram', 'linkedin', 'youtube']
        social_links = 0
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').lower()
            if any(platform in href for platform in social_platforms):
                social_links += 1

        findings.append({
            'parameter': 'Social Media Links',
            'category': 'Social Integration',
            'evaluation': 'Good' if social_links > 0 else 'Can be Improved',
            'score': 3 if social_links >= 2 else 2 if social_links > 0 else 1,
            'max_score': 3,
            'impact': 'Low',
            'remarks': f'{social_links} social media links found'
        })

        # 18. Contact information accessible
        has_phone = 'tel:' in html or re.search(r'\+?\d{2,}', html)
        has_email = 'mailto:' in html or re.search(r'[\w.-]+@[\w.-]+\.\w+', html)
        has_address = any(term in html.lower() for term in ['address', 'street', 'city', 'contact us'])
        contact_count = sum([bool(has_phone), bool(has_email), bool(has_address)])

        findings.append({
            'parameter': 'Contact Information Accessible',
            'category': 'Trust/Accessibility',
            'evaluation': 'Good' if contact_count >= 2 else 'Can be Improved' if contact_count >= 1 else 'Bad',
            'score': 3 if contact_count >= 2 else 2 if contact_count >= 1 else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'Phone: {has_phone}, Email: {has_email}, Address: {has_address}'
        })

        # 19. Breadcrumbs
        breadcrumb_indicators = ['breadcrumb', 'current:', 'you are here']
        has_breadcrumbs = any(indicator in html.lower() for indicator in breadcrumb_indicators)
        findings.append({
            'parameter': 'Breadcrumbs Present',
            'category': 'Navigation',
            'evaluation': 'Good' if has_breadcrumbs else 'Can be Improved',
            'score': 3 if has_breadcrumbs else 1,
            'max_score': 3,
            'impact': 'Low',
            'remarks': 'Breadcrumbs found' if has_breadcrumbs else 'No breadcrumbs detected'
        })

        # 20. Consistent branding (logo)
        logo = soup.find('img', attrs={'alt': re.compile(r'logo', re.I)}) or soup.find('div', class_=re.compile(r'logo', re.I))
        findings.append({
            'parameter': 'Consistent Branding/Logo',
            'category': 'Brand Identity',
            'evaluation': 'Good' if logo else 'Can be Improved',
            'score': 3 if logo else 2,
            'max_score': 3,
            'impact': 'Low',
            'remarks': 'Logo/branding element detected' if logo else 'Logo not clearly identified'
        })

        return findings

    def audit_conversion(self, html: str, url: str) -> List[Dict]:
        """Audit Conversion parameters (20 checks)."""
        findings = []
        soup = BeautifulSoup(html, 'lxml')

        # 1. CTA buttons detected
        cta_keywords = ['buy', 'shop', 'sign up', 'register', 'get started', 'order', 'contact us', 'learn more', 'subscribe', 'download']
        buttons = soup.find_all(['button', 'a'], class_=re.compile(r'btn|cta|primary', re.I))
        cta_count = 0
        for btn in buttons:
            text = btn.get_text(strip=True).lower()
            if any(keyword in text for keyword in cta_keywords):
                cta_count += 1

        findings.append({
            'parameter': 'CTA Buttons Detected',
            'category': 'Conversion',
            'evaluation': 'Good' if cta_count >= 2 else 'Can be Improved' if cta_count >= 1 else 'Bad',
            'score': 3 if cta_count >= 2 else 2 if cta_count >= 1 else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{cta_count} CTA buttons detected'
        })

        # 2. CTA wording uses action verbs
        action_verbs = ['buy', 'shop', 'sign up', 'register', 'get started', 'order', 'contact', 'subscribe', 'download', 'learn', 'start', 'join', 'claim']
        html_lower = html.lower()
        verb_count = sum(1 for verb in action_verbs if verb in html_lower)
        findings.append({
            'parameter': 'CTA Action Verb Wording',
            'category': 'Conversion',
            'evaluation': 'Good' if verb_count >= 3 else 'Can be Improved' if verb_count >= 1 else 'Bad',
            'score': 3 if verb_count >= 3 else 2 if verb_count >= 1 else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{verb_count} action verb CTAs detected'
        })

        # 3. Trust signals (reviews/testimonials/ratings)
        trust_keywords = ['review', 'testimonial', 'rating', 'star', '★', '⭐', 'verified buyer', 'customer feedback']
        trust_signals = sum(1 for keyword in trust_keywords if keyword in html_lower)
        findings.append({
            'parameter': 'Trust Signals',
            'category': 'Trust',
            'evaluation': 'Good' if trust_signals >= 2 else 'Can be Improved' if trust_signals >= 1 else 'Bad',
            'score': 3 if trust_signals >= 2 else 2 if trust_signals >= 1 else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{trust_signals} trust signal indicators found'
        })

        # 4. Trust badges/certifications visible
        badge_keywords = ['certified', 'verified', 'iso', 'badge', 'award', 'trusted', 'secure', 'ssl']
        badges = sum(1 for keyword in badge_keywords if keyword in html_lower)
        findings.append({
            'parameter': 'Trust Badges/Certifications',
            'category': 'Trust',
            'evaluation': 'Good' if badges >= 1 else 'Can be Improved',
            'score': 3 if badges >= 1 else 2,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{badges} certification/badge indicators found'
        })

        # 5. Social proof (followers, customer counts)
        proof_keywords = ['customers', 'followers', 'members', 'subscribers', 'users', 'downloads', 'sold', '+million', '+thousand']
        social_proof = sum(1 for keyword in proof_keywords if keyword in html_lower)
        findings.append({
            'parameter': 'Social Proof Indicators',
            'category': 'Trust',
            'evaluation': 'Good' if social_proof >= 2 else 'Can be Improved' if social_proof >= 1 else 'Bad',
            'score': 3 if social_proof >= 2 else 2 if social_proof >= 1 else 0,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{social_proof} social proof indicators found'
        })

        # 6. Phone number visible
        has_phone = 'tel:' in html or bool(re.search(r'\+?\d{2,}\s?\d{1,}', html))
        findings.append({
            'parameter': 'Phone Number Visible',
            'category': 'Contact',
            'evaluation': 'Good' if has_phone else 'Bad',
            'score': 3 if has_phone else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': 'Phone number found' if has_phone else 'No phone number visible'
        })

        # 7. Email contact visible
        has_email = 'mailto:' in html or bool(re.search(r'[\w.-]+@[\w.-]+\.\w+', html))
        findings.append({
            'parameter': 'Email Contact Visible',
            'category': 'Contact',
            'evaluation': 'Good' if has_email else 'Bad',
            'score': 3 if has_email else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': 'Email contact found' if has_email else 'No email contact visible'
        })

        # 8. Physical address visible
        address_keywords = ['address', 'street', 'city', 'country', 'zip', 'postal']
        has_address = any(keyword in html_lower for keyword in address_keywords)
        findings.append({
            'parameter': 'Physical Address Visible',
            'category': 'Contact',
            'evaluation': 'Good' if has_address else 'Can be Improved',
            'score': 3 if has_address else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'Physical address found' if has_address else 'No physical address visible'
        })

        # 9. Live chat/WhatsApp widget
        chat_keywords = ['live chat', 'chat with us', 'whatsapp', 'chat widget', 'intercom']
        has_chat = any(keyword in html_lower for keyword in chat_keywords)
        findings.append({
            'parameter': 'Live Chat/WhatsApp Widget',
            'category': 'Support',
            'evaluation': 'Good' if has_chat else 'Can be Improved',
            'score': 3 if has_chat else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'Live chat/messaging detected' if has_chat else 'No live chat widget found'
        })

        # 10. Urgency/scarcity signals
        urgency_keywords = ['limited', 'offer', 'sale', 'discount', 'deadline', 'expires', 'hurry', 'rush', 'exclusive', 'today only', 'ends']
        urgency = sum(1 for keyword in urgency_keywords if keyword in html_lower)
        findings.append({
            'parameter': 'Urgency/Scarcity Signals',
            'category': 'Persuasion',
            'evaluation': 'Good' if urgency >= 2 else 'Can be Improved' if urgency >= 1 else 'Bad',
            'score': 3 if urgency >= 2 else 2 if urgency >= 1 else 0,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{urgency} urgency indicators found'
        })

        # 11. Pricing visible
        pricing_keywords = ['price', '$', '€', '£', '¥', 'cost', 'free', 'plan']
        has_pricing = any(keyword in html_lower for keyword in pricing_keywords)
        findings.append({
            'parameter': 'Pricing Visible',
            'category': 'Product Information',
            'evaluation': 'Good' if has_pricing else 'Bad',
            'score': 3 if has_pricing else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': 'Pricing information visible' if has_pricing else 'No pricing visible'
        })

        # 12. Free shipping/delivery messaging
        shipping_keywords = ['free shipping', 'free delivery', 'worldwide shipping', 'flat rate', 'shipping policy']
        has_shipping = any(keyword in html_lower for keyword in shipping_keywords)
        findings.append({
            'parameter': 'Free Shipping/Delivery Messaging',
            'category': 'Incentives',
            'evaluation': 'Good' if has_shipping else 'Can be Improved',
            'score': 3 if has_shipping else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'Free shipping messaging found' if has_shipping else 'No shipping incentives visible'
        })

        # 13. Returns/refund policy linked
        policy_keywords = ['return policy', 'refund policy', 'return', 'refund', 'guarantee']
        has_policy = any(keyword in html_lower for keyword in policy_keywords)
        findings.append({
            'parameter': 'Returns/Refund Policy Linked',
            'category': 'Legal/Trust',
            'evaluation': 'Good' if has_policy else 'Can be Improved',
            'score': 3 if has_policy else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'Returns/refund policy found' if has_policy else 'No refund policy visible'
        })

        # 14. Value proposition clear above fold
        # Simplified: check if key value words appear early
        value_keywords = ['best', 'premium', 'quality', 'affordable', 'reliable', 'professional', 'innovative', 'solution']
        above_fold_text = ' '.join(soup.find_all(string=True)[:100])  # First ~100 text nodes
        value_prop = sum(1 for keyword in value_keywords if keyword in above_fold_text.lower())
        findings.append({
            'parameter': 'Value Proposition Clear',
            'category': 'Messaging',
            'evaluation': 'Good' if value_prop >= 2 else 'Can be Improved',
            'score': 3 if value_prop >= 2 else 2,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{value_prop} value proposition words in initial content'
        })

        # 15. Newsletter/email capture
        newsletter_keywords = ['newsletter', 'email list', 'subscribe', 'email capture', 'lead magnet']
        has_newsletter = any(keyword in html_lower for keyword in newsletter_keywords)
        findings.append({
            'parameter': 'Newsletter/Email Capture',
            'category': 'Lead Generation',
            'evaluation': 'Good' if has_newsletter else 'Can be Improved',
            'score': 3 if has_newsletter else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': 'Newsletter signup found' if has_newsletter else 'No email capture mechanism'
        })

        # 16. Loyalty/rewards program
        loyalty_keywords = ['loyalty', 'rewards', 'points', 'member', 'membership', 'vip']
        has_loyalty = any(keyword in html_lower for keyword in loyalty_keywords)
        findings.append({
            'parameter': 'Loyalty/Rewards Program',
            'category': 'Retention',
            'evaluation': 'Good' if has_loyalty else 'Can be Improved',
            'score': 3 if has_loyalty else 1,
            'max_score': 3,
            'impact': 'Low',
            'remarks': 'Loyalty program mentioned' if has_loyalty else 'No loyalty program visible'
        })

        # 17. Placeholder/unfinished content
        placeholder_keywords = ['lorem ipsum', 'add text here', 'cta text', 'example.com', '[replace', '{{']
        has_placeholder = any(keyword in html_lower for keyword in placeholder_keywords)
        findings.append({
            'parameter': 'Unfinished/Placeholder Content',
            'category': 'Content Quality',
            'evaluation': 'Good' if not has_placeholder else 'Bad',
            'score': 3 if not has_placeholder else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': 'No placeholder content found' if not has_placeholder else 'Unfinished content detected'
        })

        # 18. Exit intent popup
        exit_keywords = ['exit intent', 'before you go', 'wait', 'don\'t leave']
        has_exit = any(keyword in html_lower for keyword in exit_keywords)
        findings.append({
            'parameter': 'Exit Intent Popup',
            'category': 'Engagement',
            'evaluation': 'Good' if has_exit else 'Can be Improved',
            'score': 3 if has_exit else 1,
            'max_score': 3,
            'impact': 'Low',
            'remarks': 'Exit intent indicators found' if has_exit else 'No exit intent popup'
        })

        # 19. Form count and field count
        forms = soup.find_all('form')
        form_count = len(forms)
        total_fields = sum(len(form.find_all(['input', 'textarea', 'select'])) for form in forms)
        findings.append({
            'parameter': 'Form Count & Field Count',
            'category': 'Lead Capture',
            'evaluation': 'Good' if 0 < form_count <= 3 else 'Can be Improved',
            'score': 3 if 0 < form_count <= 3 else 2 if form_count > 0 else 1,
            'max_score': 3,
            'impact': 'Medium',
            'remarks': f'{form_count} forms, {total_fields} total fields'
        })

        # 20. Payment method logos visible
        payment_keywords = ['visa', 'mastercard', 'paypal', 'amex', 'stripe', 'apple pay', 'google pay']
        payment_visible = sum(1 for keyword in payment_keywords if keyword in html_lower)
        findings.append({
            'parameter': 'Payment Method Logos Visible',
            'category': 'Trust/Commerce',
            'evaluation': 'Good' if payment_visible >= 2 else 'Can be Improved' if payment_visible >= 1 else 'Bad',
            'score': 3 if payment_visible >= 2 else 2 if payment_visible >= 1 else 0,
            'max_score': 3,
            'impact': 'High',
            'remarks': f'{payment_visible} payment methods detected'
        })

        return findings

    def run_full_audit(self, url: str, credentials: Dict = None) -> Dict[str, Any]:
        """Orchestrate the full audit process with optional authentication."""
        # Step 1: Fetch page (with credentials if provided)
        html, headers, status_code, redirect_chain, error = self.fetch_page(url, credentials=credentials)

        audit_result = {
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'status_code': status_code,
            'error': error,
            'seo': [],
            'cwv': [],
            'ux': [],
            'conversion': [],
            'metadata': {
                'page_size_kb': self.page_size / 1024,
                'redirect_chain': redirect_chain
            }
        }

        if error:
            return audit_result

        # Step 2-5: Run all audit categories
        audit_result['seo'] = self.audit_seo(html, url, headers)
        audit_result['cwv'] = self.audit_cwv(html, url, headers)
        audit_result['ux'] = self.audit_ux(html, url)
        audit_result['conversion'] = self.audit_conversion(html, url)

        return audit_result

