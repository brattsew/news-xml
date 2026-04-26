import time
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = "news.xml"
SAVE_EVERY = 100
DELAY = 0.05
LENTA_SITE = "https://lenta.ru"
START_YEAR = 2026
START_MONTH = 4
START_DAY = 26
DAYS_IN_MONTH = {
    1: 31, 2: 28, 3: 31, 4: 30,
    5: 31, 6: 30, 7: 31, 8: 31,
    9: 30, 10: 31, 11: 30, 12: 31,
}

SITEMAP_SOURCES = {
    "rbc": {
        "site": "https://www.rbc.ru",
        "sitemap": "https://www.rbc.ru/sitemap_index.xml",
        "parts": [
            "/politics/", "/economics/", "/society/",
            "/business/", "/technology_and_media/",
            "/finances/", "/rbcfreenews/",
        ],
    },
    "ria": {
        "site": "https://ria.ru",
        "sitemap": "https://ria.ru/sitemap_article_index.xml",
        "parts": ["/20"],
    },
}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})

def is_leap_year(year):
    return year % 400 == 0 or (year % 100 != 0 and year % 4 == 0)

def previous_day(year, month, day):
    day -= 1
    if day > 0:
        return year, month, day
    month -= 1
    if month == 0:
        year -= 1
        month = 12
    if month == 2 and is_leap_year(year):
        return year, month, 29
    return year, month, DAYS_IN_MONTH[month]

def get_page(url):
    try:
        response = session.get(url, timeout=15)
        time.sleep(DELAY)
        if response.status_code != 200:
            print("Страница не открылась:", url, "код:", response.status_code)
            return None
        return response.text
    except Exception as error:
        print("Ошибка при открытии страницы:", url, error)
        return None
    
def get_path(url):
    if "://" not in url:
        return url
    parts = url.split("/", 3)
    if len(parts) == 4:
        return "/" + parts[3]
    return "/"

def clear_tag_name(tag):
    return tag.tag.split("}")[-1]

def has_good_part(path, good_parts):
    for part in good_parts:
        if part in path:
            return True
    return False

def collect_lenta_links(news_limit):
    print("Собираем ссылки из архива Lenta...")
    links = []
    used_links = set()
    year = START_YEAR
    month = START_MONTH
    day = START_DAY
    while len(links) < news_limit and year >= 1999:
        archive_url = LENTA_SITE + "/" + str(year) + "/" + str(month).zfill(2)
        archive_url += "/" + str(day).zfill(2) + "/"
        html = get_page(archive_url)
        if html is not None:
            soup = BeautifulSoup(html, "html.parser")
            for link in soup.find_all("a"):
                href = link.get("href", "")
                if "/news/" not in href and "/articles/" not in href:
                    continue
                if href.startswith("/"):
                    href = LENTA_SITE + href
                href = href.split("?")[0]
                if href not in used_links:
                    used_links.add(href)
                    links.append(href)
                if len(links) >= news_limit:
                    break
        print("Ссылок собрано:", len(links))
        year, month, day = previous_day(year, month, day)
    return links

def add_links_from_sitemap(sitemap_url, site, good_parts, links, used_links, news_limit):
    text = get_page(sitemap_url)
    if text is None:
        return
    try:
        root = ET.fromstring(text)
    except Exception as error:
        print("Не удалось прочитать sitemap:", sitemap_url, error)
        return
    if clear_tag_name(root) == "sitemapindex":
        for item in root:
            loc = item.find("{*}loc")
            if loc is not None and loc.text and len(links) < news_limit:
                add_links_from_sitemap(
                    loc.text.strip(),
                    site,
                    good_parts,
                    links,
                    used_links,
                    news_limit,
                )
    if clear_tag_name(root) == "urlset":
        for item in root:
            loc = item.find("{*}loc")
            if loc is None or not loc.text:
                continue
            url = loc.text.strip().split("?")[0]
            path = get_path(url)
            if not url.startswith(site):
                continue
            if has_good_part(path, good_parts) and url not in used_links:
                used_links.add(url)
                links.append(url)
            if len(links) >= news_limit:
                break
    print("Ссылок собрано:", len(links))

def collect_sitemap_links(source_name, news_limit):
    print("Собираем ссылки из sitemap...")
    links = []
    used_links = set()
    source = SITEMAP_SOURCES[source_name]
    add_links_from_sitemap(
        source["sitemap"],
        source["site"],
        source["parts"],
        links,
        used_links,
        news_limit,
    )
    return links

def collect_links(source_name, news_limit):
    if source_name == "lenta":
        return collect_lenta_links(news_limit)
    if source_name not in SITEMAP_SOURCES:
        print("Ошибка: неизвестный источник:", source_name)
        print("Можно выбрать: lenta, rbc, ria")
        return []
    return collect_sitemap_links(source_name, news_limit)

def choose_settings():
    print("Источники: lenta, rbc, ria")
    source = input("Введите источник: ").strip()
    if not source:
        source = "lenta"
    limit = input("Сколько новостей собрать: ").strip()
    if limit.isdigit():
        news_limit = int(limit)
    else:
        news_limit = 100
    return source, news_limit

def get_meta(soup, name):
    variants = [{"property": name}, {"name": name}, {"itemprop": name}]
    for variant in variants:
        tag = soup.find("meta", attrs=variant)
        if tag is not None and tag.get("content"):
            return tag.get("content").strip()
    return ""

def get_title(soup):
    title_tag = soup.find("h1")
    if title_tag is not None:
        return title_tag.get_text(" ", strip=True)
    return get_meta(soup, "og:title")

def get_text(soup):
    possible_blocks = [
        soup.find(attrs={"itemprop": "articleBody"}),
        soup.find("div", class_="topic-body__content"),
        soup.find("div", class_="article__text"),
        soup.find("div", class_="article__content"),
        soup.find("article"),
    ]
    article_block = None
    for block in possible_blocks:
        if block is not None:
            article_block = block
            break
    if article_block is None:
        paragraphs = soup.find_all("p")
    else:
        paragraphs = article_block.find_all("p")
    if not paragraphs and article_block is not None:
        text = article_block.get_text(" ", strip=True)
        if len(text) > 20:
            return text
    if not paragraphs:
        paragraphs = soup.find_all("p")
    text_parts = []
    for paragraph in paragraphs:
        text = paragraph.get_text(" ", strip=True)
        if len(text) <= 20:
            continue
        if text == "Реклама":
            continue
        if text.startswith("Подписывайтесь"):
            continue
        if text.startswith("Читайте РБК"):
            continue
        text_parts.append(text)
    return "\n".join(text_parts)

def get_date(url, soup):
    path = get_path(url)
    parts = path.split("/")
    if "ria.ru" in url and len(parts) > 1:
        date = parts[1]
        if len(date) == 8 and date.isdigit():
            return date[:4] + "-" + date[4:6] + "-" + date[6:8]
    if "lenta.ru" in url and len(parts) > 4:
        year = parts[2]
        month = parts[3]
        day = parts[4]
        if year.isdigit() and month.isdigit() and day.isdigit():
            return year + "-" + month + "-" + day
    if "rbc.ru" in url and len(parts) > 4:
        day = parts[2]
        month = parts[3]
        year = parts[4]
        if year.isdigit() and month.isdigit() and day.isdigit():
            return year + "-" + month + "-" + day
    date = get_meta(soup, "datePublished")
    if date:
        return date[:10]
    date = get_meta(soup, "article:published_time")
    if date:
        if len(date) >= 8 and date[:8].isdigit():
            return date[:4] + "-" + date[4:6] + "-" + date[6:8]
        return date[:10]
    return ""

def get_lenta_category(path, soup):
    parts = path.split("/")
    if len(parts) > 4:
        archive_link = "/" + parts[2] + "/" + parts[3] + "/" + parts[4] + "/"
        found_date = False
        for link in soup.find_all("a"):
            href = link.get("href", "")
            if href == archive_link:
                found_date = True
                continue
            if found_date and href.startswith("/rubrics/"):
                text = link.get_text(" ", strip=True)
                if text and text != "Все":
                    return text
    if len(parts) > 1 and parts[1]:
        return parts[1]
    return ""

def get_category(url, soup):
    path = get_path(url)
    if "lenta.ru" in url:
        return get_lenta_category(path, soup)
    if "ria.ru" in url:
        category = get_meta(soup, "analytics:rubric")
        if category:
            return category
    category = get_meta(soup, "articleSection")
    if category:
        return category
    parts = path.split("/")
    if len(parts) > 1 and parts[1]:
        return parts[1]
    return ""

def parse_news(url, number):
    html = get_page(url)
    if html is None:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = get_text(soup)
    if not text:
        print("Нет текста новости:", url)
        return None
    return {
        "id": str(number),
        "title": get_title(soup),
        "url": url,
        "date": get_date(url, soup),
        "category": get_category(url, soup),
        "text": text,
    }

def save_to_xml(news_list):
    root = ET.Element("dataset")
    for item in news_list:
        news_tag = ET.SubElement(root, "news", {"id": item["id"]})
        for field in ["title", "url", "date", "category", "text"]:
            tag = ET.SubElement(news_tag, field)
            tag.text = item.get(field, "")
    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

def main():
    source, news_limit = choose_settings()
    print("Выбран источник:", source)
    print("Лимит новостей:", news_limit)
    links = collect_links(source, news_limit)
    print("Всего ссылок собрано:", len(links))
    news_list = []
    checked = 0
    save_to_xml(news_list)
    for url in links:
        checked += 1
        news = parse_news(url, len(news_list) + 1)
        if news is not None:
            news_list.append(news)
        print("Ссылок проверено:", checked, "| новостей сохранено:", len(news_list))
        if len(news_list) > 0 and len(news_list) % SAVE_EVERY == 0:
            save_to_xml(news_list)
            print("Промежуточное сохранение:", len(news_list), "новостей")
        if len(news_list) >= news_limit:
            break
    save_to_xml(news_list)
    print("\nГотово!")
    print("Источник:", source)
    print("Общее количество сохраненных новостей:", len(news_list))
    print("Итоговый XML-файл:", OUTPUT_FILE)
    
if __name__ == "__main__":
    main()
