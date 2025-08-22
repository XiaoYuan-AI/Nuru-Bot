from re import search

from bs4 import BeautifulSoup
from readability import Document
from requests import get


def bing_search(query: str, count: int = 5):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
    }
    url = f"https://www.bing.com/search?q={query}&count={count}"
    response = get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for item in soup.select("li.b_algo")[:count]:
        title_tag = item.select_one("h2 a")
        snippet_tag = item.select_one("p")
        if title_tag:
            results.append({
                "title": title_tag.text,
                "link": extract_url(title_tag["href"]),
                "snippet": snippet_tag.text if snippet_tag else ""
            })
    return results


def extract_url(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
    }
    response = get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    meta_refresh = soup.find("meta", attrs={"http-equiv": "refresh"})
    if meta_refresh:
        content = meta_refresh.get("content")
        return content
    scripts = soup.find_all("script")
    for script in scripts:
        if "window.location" in script.text:
            content = search(r'window\.location\s*=\s*["\'](https?://[^"\']+)["\']', script.text)
            return content


def extract_text(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
    }
    response = get(url, headers=headers)
    response.raise_for_status()
    doc = Document(response.text)
    html = doc.summary()
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    return text
