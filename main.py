import sys
import requests
import json
import re
import os
import urllib.parse
import time
import random
import argparse
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3 import Retry
from bs4 import BeautifulSoup


def fetch_url_title(url, cookies=None):
    try:
        headers = {'Cookie': cookies} if cookies else {}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            title_tag = soup.title
            if title_tag:
                title = title_tag.string.strip()
                # 替换非法字符
                title_cleaned = title.replace('/', '-').replace('\\', '-').replace(':', '-').replace('*', '-').replace(
                    '?', '-').replace('"', '-').replace('<', '-').replace('>', '-').replace('|', '-')
                # 去除固定的字符串
                title_cleaned = title_cleaned.replace(' · 语雀', '')
                # 提取链接中的部分并按指定格式拼接到标题中
                match = re.search(r'u\d+/([\w-]+)', url)
                if match:
                    extracted_part = match.group(1)  # 获取第一个捕获组的内容
                    final_title = f"{extracted_part}-{title_cleaned}"
                    print("页面标题:", final_title)
                    return final_title
                else:
                    return title_cleaned
            else:
                return "无标题"
        else:
            print(f"请求失败，状态码：{response.status_code}")
            return "请求失败"
    except requests.exceptions.RequestException as e:
        print(f"请求发生错误：{e}")
        return "请求错误"


def save_page(book_id, slug, path, cookies=None):
    print(book_id, slug, path)
    try:
        # 分割路径为各个部分，处理每个部分的空格
        path_components = [component.strip() for component in path.replace("/", "\\").split("\\")]

        # 重新组合路径
        path = os.path.join(*path_components)

        headers = {'Cookie': cookies} if cookies else {}
        docsdata = requests.get(
            f'https://www.yuque.com/api/docs/{slug}?book_id={book_id}&merge_dynamic_data=false&mode=markdown',
            headers=headers, timeout=10
        )
        if docsdata.status_code != 200:
            print("文档下载失败 页面可能被删除 ", book_id, slug, docsdata.content)
            return
        docsjson = json.loads(docsdata.content)
        markdown_content = docsjson['data']['sourcecode']
        #directory = os.path.dirname(path).strip()
        assets_dir = os.path.join(os.path.dirname(path), 'assets')
        if not os.path.exists(assets_dir):
            os.makedirs(assets_dir)

        def download_image(match):
            url = match.group(1)
            if not url.startswith('http'):
                return match.group(0)
            url = url.split('#')[0]  # 移除URL中的所有参数
            timestamp = int(time.time() * 1000)
            extension = os.path.splitext(url)[1]
            image_name = f"image-{timestamp}{extension}"
            # 移除或替换文件名中的非法字符
            image_name = re.sub(r'[<>:"/\\|?*]', '_', image_name)
            image_path = os.path.join(assets_dir, image_name)
            try:
                image_data = requests.get(url, headers=headers, timeout=10).content
                with open(image_path, 'wb') as img_file:
                    img_file.write(image_data)
                return f'![image-{timestamp}](./assets/{image_name})'
            except requests.exceptions.RequestException as e:
                print(f"图片下载失败: {e}")
                return match.group(0)

        markdown_content = re.sub(r'!\[.*?\]\((.*?)\)', download_image, markdown_content)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")


def get_book(url, cookies=None, output_path="download"):
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    headers = {'Cookie': cookies} if cookies else {}
    try:
        docsdata = session.get(url, headers=headers, timeout=10)
        data = re.findall(r"decodeURIComponent\(\"(.+)\"\)\);", docsdata.content.decode('utf-8'))
        docsjson = json.loads(urllib.parse.unquote(data[0]))
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return

    list = {}
    temp = {}
    md = ""
    table = str.maketrans('\/:*?"<>|\n\r', "___________")

    book_title = fetch_url_title(url, cookies)
    output_dir = os.path.join(output_path, book_title)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for doc in tqdm(docsjson['book']['toc'], desc="Downloading Documents", unit="doc"):
        if doc['type'] == 'TITLE' or doc['child_uuid'] != '':
            list[doc['uuid']] = {'0': doc['title'], '1': doc['parent_uuid']}
            uuid = doc['uuid']
            temp[doc['uuid']] = ''
            while True:
                if list[uuid]['1'] != '':
                    if temp[doc['uuid']] == '':
                        temp[doc['uuid']] = doc['title'].translate(table)
                    else:
                        temp[doc['uuid']] = list[uuid]['0'].translate(table) + '/' + temp[doc['uuid']]
                    uuid = list[uuid]['1']
                else:
                    temp[doc['uuid']] = list[uuid]['0'].translate(table) + '/' + temp[doc['uuid']]
                    break
            doc_dir = os.path.join(output_dir, temp[doc['uuid']])
            if not os.path.exists(doc_dir):
                os.makedirs(doc_dir)
            if temp[doc['uuid']].endswith("/"):
                md += "## " + temp[doc['uuid']][:-1] + "\n"
            else:
                md += "  " * (temp[doc['uuid']].count("/") - 1) + "* " + temp[doc['uuid']][
                                                                         temp[doc['uuid']].rfind("/") + 1:] + "\n"
        if doc['url'] != '':
            if doc['parent_uuid'] != "":
                if temp[doc['parent_uuid']].endswith("/"):
                    md += " " * temp[doc['parent_uuid']].count("/") + "* [" + doc['title'] + "](" + urllib.parse.quote(
                        temp[doc['parent_uuid']] + "/" + doc['title'].translate(table) + '.md') + ")" + "\n"
                else:
                    md += "  " * temp[doc['parent_uuid']].count("/") + "* [" + doc['title'] + "](" + urllib.parse.quote(
                        temp[doc['parent_uuid']] + "/" + doc['title'].translate(table) + '.md') + ")" + "\n"
                save_page(str(docsjson['book']['id']), doc['url'],
                          os.path.join(output_dir, temp[doc['parent_uuid']], doc['title'].translate(table) + '.md'),
                          cookies)
            else:
                md += " " + "* [" + doc['title'] + "](" + urllib.parse.quote(
                    doc['title'].translate(table) + '.md') + ")" + "\n"
                save_page(str(docsjson['book']['id']), doc['url'],
                          os.path.join(output_dir, doc['title'].translate(table) + '.md'), cookies)
            time.sleep(random.randint(1, 4))

    with open(os.path.join(output_dir, 'SUMMARY.md'), 'w', encoding='utf-8') as f:
        f.write(md)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='从语雀下载书籍文档。')
    parser.add_argument('url', nargs='?', default="https://www.yuque.com/burpheart/phpaudit", help='书籍的 URL。')
    parser.add_argument('--cookie', default=None, help='用于认证的 Cookie。')
    parser.add_argument('--output', default="download", help='下载文件的输出目录。')

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    get_book(args.url, args.cookie, args.output)
