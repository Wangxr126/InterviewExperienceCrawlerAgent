# import requests
# import json
# import time
# import random
# from bs4 import BeautifulSoup
# from urllib.parse import urljoin
# import logging
# import re
#
# # ===================== 基础配置 =====================
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s',
#     handlers=[logging.StreamHandler()]
# )
#
# USER_AGENTS = [
#     'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
#     'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
# ]
#
#
# class NowcoderInterviewSpider:
#     def __init__(self):
#         self.base_url = "https://www.nowcoder.com"
#         self.session = requests.Session()
#         self.interview_data = []
#
#     def _update_headers(self):
#         self.session.headers.update({
#             'User-Agent': random.choice(USER_AGENTS),
#             'Referer': self.base_url,
#             # 必须加上 Cookie，否则可能会被重定向到验证页面
#             # 请替换为你浏览器 F12 抓到的真实 Cookie
#             'Cookie': 'YOUR_COOKIE_HERE'
#         })
#
#     import re
#
#     def extract_meta_info(title, content):
#         """
#         从标题和内容中提取：公司、岗位、业务/部门
#         """
#         # === 1. 基础词库配置 (可根据需要扩充) ===
#         # 公司别名映射
#         company_map = {
#             '字节': '字节跳动', '字节跳动': '字节跳动', 'bytedance': '字节跳动',
#             '阿里': '阿里巴巴', '淘天': '阿里巴巴', '蚂蚁': '蚂蚁集团',
#             '腾讯': '腾讯', 'wxg': '腾讯(WXG)', 'ieg': '腾讯(IEG)', 'teg': '腾讯(TEG)',
#             '美团': '美团', '百度': '百度', '快手': '快手', '拼多多': '拼多多', 'pdd': '拼多多',
#             '京东': '京东', '网易': '网易', '小红书': '小红书', '华为': '华为', 'od': '华为OD',
#             '米哈游': '米哈游', '滴滴': '滴滴', '蔚来': '蔚来', '理想': '理想', '小鹏': '小鹏',
#             'b站': 'Bilibili', '哔哩哔哩': 'Bilibili', '去哪儿': '去哪儿', '携程': '携程',
#             '中车': '中车', '虎牙': '虎牙', '银联': '中国银联', '极氪': '极氪',
#             'cvte': 'CVTE', '航旅纵横': '航旅纵横', '千寻': '千寻智能'
#         }
#
#         # 岗位关键词
#         roles = [
#             '后端', '前端', '算法', '测试', '测开', '客户端', '安卓', 'Android', 'ios',
#             '大数据', '产品', '运营', 'Java', 'C++', 'Python', 'Go', '嵌入式', '硬件', '机械'
#         ]
#
#         # 业务/部门关键词
#         businesses = [
#             '搜索', '推荐', '广告', '电商', '支付', '游戏', '云', '基础架构', 'Infra',
#             '飞书', '抖音', '微信', 'QQ', '大模型', 'LLM', '智能运维', '自动驾驶'
#         ]
#
#         # === 2. 提取逻辑 ===
#         text_to_scan = f"{title} {content[:50]}"  # 标题 + 正文前50字
#
#         extracted = {
#             "company": "未知公司",
#             "role": "未知岗位",
#             "business": "未知业务"
#         }
#
#         # --- 提取公司 ---
#         for key, name in company_map.items():
#             if re.search(re.escape(key), text_to_scan, re.IGNORECASE):
#                 extracted['company'] = name
#                 break
#
#         # --- 提取岗位 ---
#         for role in roles:
#             if re.search(re.escape(role), text_to_scan, re.IGNORECASE):
#                 extracted['role'] = role
#                 break
#
#         # --- 提取业务 ---
#         for bus in businesses:
#             if re.search(re.escape(bus), text_to_scan, re.IGNORECASE):
#                 extracted['business'] = bus
#                 break
#
#         return extracted
#
#     def parse_list_page(self, page_num):
#         """
#         解析搜索结果列表页 (适配新版 HTML 结构)
#         """
#         # 注意：这里使用的是 search/all 网页 URL，不是 API
#         list_url = f"{self.base_url}/search/all?query=面经&type=all&searchType=历史搜索&page={page_num}"
#
#         try:
#             time.sleep(random.uniform(2, 4))  # 增加延时防止被封
#             self._update_headers()
#
#             logging.info(f"正在抓取第 {page_num} 页: {list_url}")
#             response = self.session.get(list_url, timeout=20)
#
#             if response.status_code != 200:
#                 logging.error(f"请求失败，状态码: {response.status_code}")
#                 return False
#
#             soup = BeautifulSoup(response.text, 'html.parser')
#
#             # 1. 定位所有帖子卡片
#             # 依据：<div class="tw-bg-white tw-mt-3 tw-rounded-xl">
#             post_cards = soup.find_all('div', class_=lambda
#                 x: x and 'tw-bg-white' in x and 'tw-mt-3' in x and 'tw-rounded-xl' in x)
#
#             if not post_cards:
#                 logging.warning(f"第 {page_num} 页未找到帖子（可能是Cookie失效或到了末页）")
#                 # 调试用：打印前500个字符看看是不是验证码页面
#                 # print(response.text[:500])
#                 return False
#
#             logging.info(f"第 {page_num} 页找到 {len(post_cards)} 个帖子")
#
#             for idx, card in enumerate(post_cards, 1):
#                 try:
#                     post_info = {}
#
#                     # --- 提取标题 & 链接 ---
#                     # 依据：父级 div 包含 tw-font-bold tw-text-lg
#                     title_container = card.find('div', class_=lambda x: x and 'tw-font-bold' in x and 'tw-text-lg' in x)
#                     if not title_container:
#                         continue  # 可能是广告或推荐位，跳过
#
#                     link_tag = title_container.find('a')
#                     if not link_tag:
#                         continue
#
#                     post_info['title'] = link_tag.get_text(strip=True)
#                     href = link_tag.get('href', '')
#                     # 处理链接，有时候是相对路径，有时候带参数
#                     post_info['post_url'] = urljoin(self.base_url, href.split('?')[0])
#
#                     # --- 提取时间 ---
#                     # 依据：<div class="... show-time">
#                     time_tag = card.find('div', class_=lambda x: x and 'show-time' in x)
#                     post_info['publish_time'] = time_tag.get_text(strip=True) if time_tag else '未知时间'
#
#                     # --- 提取作者 ---
#                     # 依据：<div class="user-nickname">
#                     author_tag = card.find('div', class_='user-nickname')
#                     post_info['author'] = author_tag.get_text(strip=True) if author_tag else '匿名'
#
#                     # --- 提取列表页预览内容 (作为备用) ---
#                     preview_tag = card.find('div', class_='placeholder-text')
#                     preview_content = preview_tag.get_text(strip=True) if preview_tag else ""
#
#                     logging.info(f"  [{idx}] 发现帖子: {post_info['title']} ({post_info['publish_time']})")
#
#                     # --- 进入详情页抓取完整内容 ---
#                     # ⚠️ 注意：为了速度，这里可以先只用预览内容。如果必须要全文，请保留下面这行
#                     post_info['content'] = card.contents[0].text
#
#                     # 如果详情页抓取失败，使用列表页的预览内容兜底
#                     if "失败" in post_info['content'] or not post_info['content']:
#                         post_info['content'] = f"[预览内容] {preview_content}"
#
#                     self.interview_data.append(post_info)
#
#                 except Exception as e:
#                     logging.error(f"  ❌ 解析帖子 {idx} 失败: {str(e)}")
#                     continue
#
#             return True
#
#         except Exception as e:
#             logging.error(f"❌ 第 {page_num} 页请求发生异常: {str(e)}")
#             return False
#
#     def parse_detail_page(self, post_url):
#         """
#         进入详情页抓取具体内容
#         """
#         if not post_url.startswith('http'):
#             return ""
#
#         try:
#             time.sleep(random.uniform(1, 2))  # 详情页请求间隔
#             self._update_headers()
#             response = self.session.get(post_url, timeout=15)
#
#             if response.status_code != 200:
#                 return f"请求详情页失败 {response.status_code}"
#
#             soup = BeautifulSoup(response.text, 'html.parser')
#
#             # --- 详情页正文提取策略 ---
#             # 策略1: 查找含有 post-content 的 div (最常见)
#             content_div = soup.find('div', class_=lambda x: x and ('nc-post-content' in x or 'post-topic-des' in x))
#
#             # 策略2: 如果策略1失效，查找 id="js-post-content"
#             if not content_div:
#                 content_div = soup.find(id="js-post-content")
#
#             if content_div:
#                 # 移除 script 和 style 标签
#                 for script in content_div(["script", "style"]):
#                     script.decompose()
#                 # 获取纯文本
#                 return content_div.get_text(separator='\n', strip=True)
#             else:
#                 return "未识别到正文结构 (可能需要登录或结构变更)"
#
#         except Exception as e:
#             return f"详情页解析异常: {str(e)}"
#
#     def save_data(self, save_path='newcoder_data.json'):
#         with open(save_path, 'w', encoding='utf-8') as f:
#             json.dump(self.interview_data, f, ensure_ascii=False, indent=4)
#         logging.info(f"🎉 数据已保存至 {save_path}，共 {len(self.interview_data)} 条")
#
#     def run(self, max_pages=3):
#         logging.info("🚀 开始爬虫任务...")
#         for page in range(1, max_pages + 1):
#             if not self.parse_list_page(page):
#                 break
#         self.save_data()
#
#
# # ===================== 启动 =====================
# if __name__ == "__main__":
#     spider = NowcoderInterviewSpider()
#     spider.run(max_pages=2)  # 先试爬2页
#
#
#     #尝试内容分割+提槽+难度评判+[部门]+[业务]
import requests
import json
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging
import re

# ===================== 基础配置 =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
]


class NowcoderInterviewSpider:
    def __init__(self):
        self.base_url = "https://www.nowcoder.com"
        self.session = requests.Session()
        self.interview_data = []

        # === 预编译正则关键词 ===
        self.rules = {
            "company": {
                '字节': '字节跳动', 'bytedance': '字节跳动', '抖音': '字节跳动', 'TikTok': '字节跳动',
                '阿里': '阿里巴巴', '淘天': '阿里巴巴', '蚂蚁': '蚂蚁集团', '天猫': '阿里巴巴',
                '腾讯': '腾讯', 'wxg': '腾讯(WXG)', 'ieg': '腾讯(IEG)', 'teg': '腾讯(TEG)', 'qq': '腾讯',
                '美团': '美团', '百度': '百度', '快手': '快手', '拼多多': '拼多多', 'pdd': '拼多多',
                '京东': '京东', '网易': '网易', '小红书': '小红书',
                '华为': '华为', 'od': '华为OD', '德科': '华为OD',
                '米哈游': '米哈游', '滴滴': '滴滴', '蔚来': '蔚来', '理想': '理想', '小鹏': '小鹏',
                'b站': 'Bilibili', '哔哩哔哩': 'Bilibili',
                '去哪儿': '去哪儿', '携程': '携程',
                '中车': '中车', '虎牙': '虎牙', '银联': '中国银联', '极氪': '极氪',
                'cvte': 'CVTE', '航旅纵横': '航旅纵横', '千寻': '千寻智能'
            },
            "role": [
                '后端', '前端', '算法', '测试', '测开', '客户端', '安卓', 'Android', 'ios',
                '大数据', '产品', '运营', 'Java', 'C++', 'Python', 'Go', '嵌入式', '硬件', '机械', '全栈'
            ],
            "business": [
                '搜索', '推荐', '广告', '电商', '支付', '游戏', '云', '基础架构', 'Infra',
                '飞书', '微信', '大模型', 'LLM', '智能运维', '自动驾驶', '核心', '商业化'
            ],
            "difficulty": {
                "困难": ['拷打', '深挖', '很难', '挂了', '凉', '压力', '手撕', '底层', '源码'],
                "简单": ['简单', '常规', '八股', '水面', '聊天', '基础', 'oc', '意向']
            },
            "post_type": {
                "吐槽": ['避雷', '恶心', '无语', 'kpi', '渣男'],
                "面经": ['面经', '一面', '二面', '三面', 'hr面', '复盘', '凉经'],
                "求助": ['求捞', '求助', '怎么办', '选哪个']
            }
        }

    def _update_headers(self):
        self.session.headers.update({
            'User-Agent': random.choice(USER_AGENTS),
            'Referer': self.base_url,
            # ⚠️ 必须填入 Cookie，否则无法获取完整列表
            'Cookie': 'YOUR_COOKIE_HERE'
        })

    def extract_meta_info(self, title, content_preview):
        """
        核心分析函数：从文本中提取结构化标签
        """
        text_scan = f"{title} {content_preview}".lower()

        result = {
            "company": "未知",
            "role": "未知",
            "business": "未知",
            "difficulty": "未知",
            "type": "其他",
            "tags": []
        }

        # 1. 提取公司 (优先匹配)
        for key, name in self.rules["company"].items():
            if key.lower() in text_scan:
                result['company'] = name
                result['tags'].append(name)
                break  # 找到一个就停止，避免 "字节跳动阿里" 这种被误判

        # 2. 提取岗位
        for role in self.rules["role"]:
            if role.lower() in text_scan:
                result['role'] = role
                result['tags'].append(role)
                break

        # 3. 提取业务线
        for bus in self.rules["business"]:
            if bus.lower() in text_scan:
                result['business'] = bus
                result['tags'].append(bus)
                break

        # 4. 评判难度
        diff_score = 0
        if any(k in text_scan for k in self.rules["difficulty"]["困难"]):
            diff_score += 1
        if any(k in text_scan for k in self.rules["difficulty"]["简单"]):
            diff_score -= 1

        if diff_score > 0:
            result['difficulty'] = "困难/拷打"
        elif diff_score < 0:
            result['difficulty'] = "简单/常规"
        else:
            result['difficulty'] = "适中"

        # 5. 帖子类型
        for p_type, keywords in self.rules["post_type"].items():
            if any(k in text_scan for k in keywords):
                result['type'] = p_type
                break

        return result

    def parse_list_page(self, page_num):
        list_url = f"{self.base_url}/search/all?query=面经&type=all&searchType=历史搜索&page={page_num}"

        try:
            time.sleep(random.uniform(2, 4))
            self._update_headers()
            logging.info(f"正在抓取第 {page_num} 页: {list_url}")

            response = self.session.get(list_url, timeout=20)
            if response.status_code != 200:
                logging.error(f"状态码异常: {response.status_code}")
                return False

            soup = BeautifulSoup(response.text, 'html.parser')

            # 定位帖子卡片 (Tailwind 类名匹配)
            post_cards = soup.find_all('div', class_=lambda
                x: x and 'tw-bg-white' in x and 'tw-mt-3' in x and 'tw-rounded-xl' in x)

            if not post_cards:
                logging.warning(f"第 {page_num} 页未找到数据 (检查Cookie或是否末页)")
                return False

            logging.info(f"📊 第 {page_num} 页解析到 {len(post_cards)} 条数据")

            for idx, card in enumerate(post_cards, 1):
                try:
                    # === 基础字段提取 ===
                    # 标题
                    title_tag = card.find('div', class_=lambda x: x and 'tw-font-bold' in x and 'tw-text-lg' in x)
                    title = title_tag.get_text(strip=True) if title_tag else "无标题"

                    # 链接
                    link_tag = title_tag.find('a') if title_tag else None
                    link = urljoin(self.base_url, link_tag['href'].split('?')[0]) if link_tag else ""

                    # 发布时间
                    time_tag = card.find('div', class_=lambda x: x and 'show-time' in x)
                    pub_time = time_tag.get_text(strip=True) if time_tag else ""

                    # 作者
                    author_tag = card.find('div', class_='user-nickname')
                    author = author_tag.get_text(strip=True) if author_tag else "匿名"

                    # === 核心要求：从整个卡片文本中解析 ===
                    # 获取卡片内所有纯文本，用于 NLP 分析
                    full_card_text = card.get_text(separator=' ', strip=True)

                    # 提取列表页展示的预览正文 (用于内容分割)
                    preview_div = card.find('div', class_='placeholder-text')
                    preview_content = preview_div.get_text(strip=True) if preview_div else ""

                    # === 智能分析 (不依赖 API JSON) ===
                    analysis = self.extract_meta_info(title, full_card_text)

                    # 组装数据
                    item = {
                        "title": title,
                        "url": link,
                        "time": pub_time,
                        "author": author,
                        "content_preview": preview_content,  # 列表页预览
                        # --- 智能提取字段 ---
                        "company": analysis['company'],  # 公司
                        "department": analysis['business'],  # 部门/业务
                        "job_type": analysis['role'],  # 岗位
                        "difficulty": analysis['difficulty'],  # 难度
                        "post_type": analysis['type'],  # 类型
                        "tags": analysis['tags']  # 标签
                    }

                    self.interview_data.append(item)
                    logging.info(
                        f"  [{analysis['company']}-{analysis['role']}] {title[:20]}... ({analysis['difficulty']})")

                except Exception as e:
                    logging.error(f"  ❌ 解析单条出错: {e}")
                    continue

            return True

        except Exception as e:
            logging.error(f"❌ 页面请求异常: {e}")
            return False

    def save_data(self, save_path='newcoder_analysis.json'):
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(self.interview_data, f, ensure_ascii=False, indent=4)
        logging.info(f"🎉 数据已保存至 {save_path}，共 {len(self.interview_data)} 条")

    def run(self, max_pages=2):
        logging.info("🚀 智能爬虫启动...")
        for page in range(1, max_pages + 1):
            if not self.parse_list_page(page):
                break
            time.sleep(1)  # 翻页间隔
        self.save_data()


if __name__ == "__main__":
    spider = NowcoderInterviewSpider()
    spider.run(max_pages=3)