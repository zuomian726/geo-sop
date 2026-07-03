"""
网页内容采集模块
用于采集引用参考链接的网页内容
"""
import requests
from bs4 import BeautifulSoup
import time
import logging
import random
from urllib.parse import urlparse
import chardet
import config
from models import ReferenceContent, get_db

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# User-Agent 列表，模拟不同浏览器
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Edg/120.0.0.0',
]


class WebCrawler:
    """网页爬虫"""

    def __init__(self):
        self.session = requests.Session()
        self._update_headers()

    def _update_headers(self):
        """更新请求头，使用随机User-Agent"""
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }
        self.session.headers.update(headers)

    def _detect_encoding(self, response):
        """检测网页编码"""
        # 1. 尝试从响应头获取编码
        content_type = response.headers.get('Content-Type', '')
        if 'charset=' in content_type:
            charset = content_type.split('charset=')[-1].strip()
            if charset:
                return charset

        # 2. 使用 chardet 检测编码
        raw_content = response.content
        result = chardet.detect(raw_content)
        encoding = result.get('encoding', 'utf-8')

        # 3. 处理常见编码别名
        encoding_map = {
            'GB2312': 'GBK',
            'GBK2312': 'GBK',
            'gb2312': 'GBK',
            'gbk': 'GBK',
            'GBK': 'GBK',
            'UTF-8': 'utf-8',
            'utf-8': 'utf-8',
            'windows-1252': 'utf-8',
        }

        return encoding_map.get(encoding, 'utf-8')

    def crawl(self, url: str, retry_times: int = None) -> dict:
        """
        采集网页内容

        Args:
            url: 网页URL
            retry_times: 重试次数（默认使用配置）

        Returns:
            dict: {
                'success': bool,
                'title': str,
                'content': str,
                'html_content': str,
                'error': str
            }
        """
        if retry_times is None:
            retry_times = config.CRAWL_RETRY_TIMES

        for attempt in range(retry_times):
            try:
                # 更新请求头（每次请求使用不同的User-Agent）
                self._update_headers()

                logger.info(f"正在采集: {url} (尝试 {attempt + 1}/{retry_times})")

                response = self.session.get(
                    url,
                    timeout=config.CRAWL_TIMEOUT,
                    allow_redirects=True,
                    verify=False  # 忽略SSL证书验证
                )
                response.raise_for_status()

                # 检测并设置正确编码
                encoding = self._detect_encoding(response)
                response.encoding = encoding

                # 解析HTML
                soup = BeautifulSoup(response.text, 'html.parser')

                # 提取标题
                title = self._extract_title(soup)

                # 提取正文内容
                content = self._extract_content(soup)

                logger.info(f"采集成功: {url} - 标题: {title}")

                return {
                    'success': True,
                    'title': title,
                    'content': content,
                    'html_content': response.text,
                    'error': None
                }

            except requests.exceptions.Timeout:
                logger.warning(f"采集超时: {url} (尝试 {attempt + 1}/{retry_times})")
                error = "请求超时"

            except requests.exceptions.SSLError:
                logger.warning(f"SSL证书错误: {url} (尝试 {attempt + 1}/{retry_times})")
                # 尝试不验证SSL证书重试
                self.session.verify = False
                error = "SSL证书错误"

            except requests.exceptions.HTTPError as e:
                logger.warning(f"HTTP错误: {url} - {str(e)} (尝试 {attempt + 1}/{retry_times})")
                error = f"HTTP错误: {str(e)}"

            except requests.exceptions.RequestException as e:
                logger.warning(f"采集失败: {url} - {str(e)} (尝试 {attempt + 1}/{retry_times})")
                error = str(e)

            except Exception as e:
                logger.error(f"解析失败: {url} - {str(e)}")
                error = f"解析错误: {str(e)}"

            # 重试前等待，增加随机延迟避免被封
            if attempt < retry_times - 1:
                delay = config.CRAWL_RETRY_DELAY + random.uniform(0, 2)
                logger.info(f"等待 {delay:.2f} 秒后重试...")
                time.sleep(delay)

        return {
            'success': False,
            'title': None,
            'content': None,
            'html_content': None,
            'error': error
        }

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取网页标题"""
        # 优先级：og:title > title标签 > h1标签
        title = None

        # 尝试 og:title
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title.get('content').strip()

        # 尝试 title 标签
        if not title:
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip()

        # 尝试 h1 标签
        if not title:
            h1_tag = soup.find('h1')
            if h1_tag:
                title = h1_tag.get_text().strip()

        return title or "无标题"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """提取网页正文内容"""
        # 移除不需要的标签
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'noscript']):
            tag.decompose()

        # 尝试找到主要内容区域
        content_selectors = [
            'article',
            '[class*="content"]',
            '[class*="article"]',
            '[class*="post"]',
            '[id*="content"]',
            '[id*="article"]',
            '[id*="post"]',
            'main',
            '.markdown-body',
            '.container',
            '.main-content',
            '.article-content',
        ]

        content_element = None
        for selector in content_selectors:
            content_element = soup.select_one(selector)
            if content_element:
                break

        # 如果没找到主要内容区域，使用 body
        if not content_element:
            content_element = soup.find('body')

        # 提取文本
        if content_element:
            text = content_element.get_text(separator='\n', strip=True)
            # 清理多余的空白
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            return '\n'.join(lines)

        return ""


def crawl_reference_url(collection_result_id: int, url: str) -> ReferenceContent:
    """
    采集引用链接并保存到数据库

    Args:
        collection_result_id: 采集结果ID
        url: 引用链接URL

    Returns:
        ReferenceContent: 保存的内容记录
    """
    db = next(get_db())

    try:
        # 检查是否已存在
        existing = db.query(ReferenceContent).filter_by(
            collection_result_id=collection_result_id,
            url=url
        ).first()

        if existing:
            logger.info(f"引用链接已存在: {url}")
            return existing

        # 创建新记录
        content_record = ReferenceContent(
            collection_result_id=collection_result_id,
            url=url,
            crawl_status='pending'
        )
        db.add(content_record)
        db.commit()
        db.refresh(content_record)

        # 采集内容
        crawler = WebCrawler()
        result = crawler.crawl(url)

        if result['success']:
            content_record.title = result['title']
            content_record.content = result['content']
            content_record.html_content = result['html_content']
            content_record.crawl_status = 'success'
            logger.info(f"引用链接采集成功: {url}")
        else:
            content_record.crawl_status = 'failed'
            content_record.crawl_error = result['error']
            logger.error(f"引用链接采集失败: {url} - {result['error']}")

        db.commit()
        # 在 Session 关闭前转换为字典，避免 detached instance 错误
        return content_record.to_dict()

    except Exception as e:
        db.rollback()
        logger.error(f"保存引用链接内容失败: {url} - {str(e)}")
        raise
    finally:
        db.close()


def batch_crawl_references(collection_result_id: int, urls: list) -> list:
    """
    批量采集引用链接

    Args:
        collection_result_id: 采集结果ID
        urls: 引用链接列表

    Returns:
        list: 采集的内容记录字典列表
    """
    results = []
    for url in urls:
        try:
            content_dict = crawl_reference_url(collection_result_id, url)
            results.append(content_dict)
            # 添加随机延迟，避免请求过快被封
            time.sleep(random.uniform(1, 3))
        except Exception as e:
            logger.error(f"批量采集失败: {url} - {str(e)}")

    return results