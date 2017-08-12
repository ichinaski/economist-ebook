import os
import io
import hashlib
import requests
import sqlite3
import logging

import newspaper

from bs4 import BeautifulSoup
from PIL import Image
from ebooklib import epub


os.makedirs('images', exist_ok=True)


class Database:
    '''Simple key-value store for urls and html content.'''

    def __init__(self):
        self.conn = sqlite3.connect('articles.db')
        self._ensure_schema(self.conn)

    def _ensure_schema(self, conn):
        c = conn.cursor()
        try:
            c.execute('''CREATE TABLE IF NOT EXISTS articles(
                         url text PRIMARY KEY NOT NULL,
                         html text)''')
            conn.commit()
        finally:
            c.close()

    def get(self, url):
        cursor = self.conn.cursor()
        try:
            row = cursor.execute("""
                SELECT html
                FROM articles WHERE url=?
            """, (url, ))
            row = cursor.fetchone()
            if row:
                return row[0]
        except Exception:
            logging.exception('cannot get article: %s', url)
        finally:
            cursor.close()

        return None

    def set(self, url, html):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO articles(url, html)
                VALUES (?, ?)
            ''', (url, html))
            self.conn.commit()
        finally:
            cursor.close()


class Article:
    def __init__(self, url, title=None):
        self.url = url
        self.title = title
        self.html = ''  # original article html
        self.images = []
        self.content = ''  # parsed html content

    def download(self, db):
        self.html = db.get(self.url)
        if not self.html:
            self.html = fetch(self.url).text
            db.set(self.url, self.html)

    def build(self, db):
        self.download(db)

        soup = BeautifulSoup(self.html, "lxml")
        a = soup.find('article', class_='blog-post')

        article = newspaper.Article(self.url)
        article.download(html=str(a))
        article.parse()

        # Header
        content = '<h1>{}</h1>'.format(self.title)

        # Top image
        if article.has_top_image():
            img = article.top_image
            filename = download_image(img)
            self.images.append(filename)
            content += '<center><img src="{}" /></center>'.format(filename)

        # If we have more images, space them out throughout the text
        images = [i for i in article.images if i != article.top_image]
        paragraphs = article.text.split('\n')

        rate = len(paragraphs) / (len(images) + 1)
        for i, img in enumerate(images, 1):
            pos = round(i * rate) + i
            filename = download_image(img)
            self.images.append(filename)
            img_tag = '<center><img src="{}" /></center>'.format(filename)
            paragraphs.insert(pos, img_tag)

        content += '<br>'.join(paragraphs)
        self.content = content


class Section:
    def __init__(self, title, articles=[]):
        self.title = title
        self.articles = articles

    def build(self, db):
        for a in self.articles:
            try:
                a.build(db)
            except Exception:
                logging.exception('cannot build article')

    def __str__(self):
        return '{}: {} articles'.format(self.title, len(self.articles))


class Economist:
    base_url = 'http://www.economist.com'
    print_edition = '{}/printedition/'.format(base_url)
    author = 'The Economist'
    language = 'en'

    def __init__(self):
        self.id = ''
        self.title = ''
        self.html = ''
        self.cover_img = None
        self.sections = []
        self.db = Database()

    def fetch_issue(self):
        '''fetch latest issue, assembling sections and articles'''
        res = fetch(self.print_edition)

        date = res.url[-10:]
        self.id = 'the_economist_{}'.format(date)
        self.title = 'The Economist - {}'.format(date)

        html = res.text
        soup = BeautifulSoup(html, "lxml")
        soup = soup.find('div', class_='main-content')

        # Issue cover
        cover = soup.find('img', class_='print-edition__cover-widget__image')
        if cover:
            self.cover_img = cover['src']

        main_list = soup.find('ul', class_='list')
        for li in main_list.find_all('li', class_='list__item'):
            name = li.find('div', class_='list__title').text
            articles = []
            for a in li.find_all('a', class_='list__link'):
                title = ' - '.join([s.text for s in a.find_all('span')])
                href = self.absolute_url(a.get('href'))
                article = Article(href, title=title)
                articles.append(article)

            section = Section(name, articles)
            self.sections.append(section)

    def build(self):
        '''build issue, downloading articles if needed, and write ebook'''

        self.fetch_issue()
        self.info()

        for s in self.sections:
            s.build(self.db)

        book = epub.EpubBook()

        # add metadata
        book.set_title(self.title)
        book.set_identifier(self.id)
        book.set_language(self.language)
        book.add_author(self.author)

        toc = []
        spine = []

        if self.cover_img:
            img = fetch(self.cover_img).content
            book.set_cover("image.jpg", img)
            spine.append('cover')

        spine.append('nav')

        # Sections
        for section in self.sections:
            items = []

            for article in section.articles:
                if not article.content:
                    logging.error('%s could not be downloaded. Skipping.',
                                  article.url)
                    continue
                item = epub.EpubHtml(title=article.title,
                                     file_name='{}.xhtml'.format(article.title),
                                     lang=self.language)
                item.content = article.content

                # images were downloaded by the article, and placed
                # in disk for refenrence. We now add them to the book.
                for filename in article.images:
                    img = epub.EpubImage()
                    img.file_name = filename
                    with open(filename, 'rb') as f:
                        img.content = f.read()
                    book.add_item(img)
                items.append(item)

            for item in items:
                book.add_item(item)
            toc.append((epub.Section(section.title, href=items[0].file_name),
                        items))
            spine.extend(items)

        book.toc = toc
        book.spine = spine

        # add navigation files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # create epub file
        epub.write_epub('{}.epub'.format(self.id), book, {})

    def absolute_url(self, url):
        return self.base_url + url if url.startswith('/') else url

    def info(self):
        print('Title: %s' % (self.title, ))
        print('Author: %s' % (self.author, ))
        print('Cover: %s' % (self.cover_img, ))
        print('Sections: {}'.format([str(s) for s in self.sections]))


def fetch(url):
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    return res


def download_image(image_url, max_width=400):
    '''download and resize image, storing the data in "images" directory'''

    filename = 'images/{}-{}'.format(
        hashlib.md5(image_url.encode('utf-8')).hexdigest(),
        os.path.basename(image_url))

    if os.path.exists(filename):
        return filename

    data = fetch(image_url).content
    image = Image.open(io.BytesIO(data))

    w, h = image.size

    if w > max_width:
        ratio = w / max_width

        size = (max_width, int(h/ratio))
        image = image.resize(size, Image.LANCZOS)

    image.save(filename)
    return filename


if __name__ == '__main__':
    Economist().build()
