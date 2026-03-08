"""
测试牛客帖子图片下载功能
目标：从牛客帖子中提取图片URL并下载到本地
"""
import os
import requests
import logging
from pathlib import Path
from backend.services.crawler.nowcoder_crawler import NowcoderCrawler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def download_image(url: str, save_dir: str, filename: str) -> bool:
    """
    下载单张图片到本地
    
    Args:
        url: 图片URL
        save_dir: 保存目录
        filename: 文件名
    
    Returns:
        bool: 是否下载成功
    """
    try:
        # 确保目录存在
        os.makedirs(save_dir, exist_ok=True)
        
        # 下载图片
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.nowcoder.com/"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # 保存图片
        filepath = os.path.join(save_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"✅ 图片下载成功: {filename} ({len(response.content)} bytes)")
        return True
        
    except Exception as e:
        logger.error(f"❌ 图片下载失败 {url}: {e}")
        return False

def test_download_images_from_post(post_url: str):
    """
    测试从指定帖子下载图片
    
    Args:
        post_url: 牛客帖子URL
    """
    logger.info(f"开始测试帖子: {post_url}")
    
    # 初始化爬虫
    crawler = NowcoderCrawler()
    
    # 获取帖子内容和图片URL
    content, image_urls = crawler.fetch_post_content_full(post_url)
    
    logger.info(f"帖子内容长度: {len(content)} 字符")
    logger.info(f"发现图片数量: {len(image_urls)} 张")
    
    if not image_urls:
        logger.warning("⚠️ 未发现图片，无法测试下载")
        return
    
    # 打印所有图片URL
    logger.info("\n图片URL列表:")
    for idx, url in enumerate(image_urls, 1):
        logger.info(f"  {idx}. {url}")
    
    # 创建保存目录
    save_dir = "牛客图片测试"
    logger.info(f"\n开始下载图片到目录: {save_dir}")
    
    # 下载所有图片
    success_count = 0
    for idx, url in enumerate(image_urls, 1):
        # 从URL中提取文件扩展名
        ext = url.split('.')[-1].split('?')[0]
        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            ext = 'jpg'  # 默认扩展名
        
        filename = f"image_{idx}.{ext}"
        if download_image(url, save_dir, filename):
            success_count += 1
    
    logger.info(f"\n下载完成: {success_count}/{len(image_urls)} 张图片成功")

if __name__ == "__main__":
    # 测试URL - 使用牛客搜索"面经"关键词，找到包含图片的帖子
    logger.info("=" * 60)
    logger.info("牛客图片下载测试")
    logger.info("=" * 60)
    
    # 先爬取一个真实的帖子URL
    from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
    crawler = NowcoderCrawler()
    
    logger.info("正在搜索包含图片的牛客帖子...\n")
    
    # 尝试多个帖子，找到包含图片的
    found_images = False
    for page in range(1, 4):  # 尝试前3页
        posts = crawler.discover_page("面经", page)
        
        if not posts:
            logger.warning(f"第{page}页未找到帖子")
            continue
        
        for post in posts[:5]:  # 每页尝试前5个帖子
            test_url = post["source_url"]
            logger.info(f"检查帖子: {post['title'][:30]}...")
            
            # 快速检查是否有图片
            content, image_urls = crawler.fetch_post_content_full(test_url)
            
            if image_urls:
                logger.info(f"✅ 找到包含{len(image_urls)}张图片的帖子！")
                logger.info(f"标题: {post['title']}")
                logger.info(f"URL: {test_url}\n")
                
                test_download_images_from_post(test_url)
                found_images = True
                break
            else:
                logger.info(f"   该帖子无图片，继续搜索...\n")
        
        if found_images:
            break
    
    if not found_images:
        logger.warning("未找到包含图片的帖子，请手动指定URL测试")
    
    logger.info("\n测试完成！请检查 '牛客图片测试' 目录中的图片")
