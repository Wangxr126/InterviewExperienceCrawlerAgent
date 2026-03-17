"""
为scheduler.py添加爬取失败重试机制
"""

retry_logic = '''

def _retry_failed_tasks(max_retries: int = None, retry_delay: int = None) -> int:
    """
    重试爬取失败的任务
    
    Args:
        max_retries: 最大重试次数（不传时从配置读取）
        retry_delay: 重试间隔秒数（不传时从配置读取）
    
    Returns:
        成功重试的任务数
    """
    from backend.config.config import settings
    import time
    
    _max_retries = max_retries if max_retries is not None else settings.crawler_fetch_max_retries
    _retry_delay = retry_delay if retry_delay is not None else settings.crawler_retry_delay
    
    logger.info(f"🔄 开始重试失败任务（最大重试{_max_retries}次，间隔{_retry_delay}秒）...")
    
    # 查询需要重试的任务（状态为pending且raw_content为空的）
    failed_tasks = sqlite_service.get_tasks_by_status("pending", limit=50)
    
    if not failed_tasks:
        logger.info("✅ 没有需要重试的任务")
        return 0
    
    from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
    crawler = NowcoderCrawler(cookie=cfg.NOWCODER_COOKIE)
    
    success_count = 0
    
    for task in failed_tasks:
        task_id = task["task_id"]
        url = task["source_url"]
        title = task["post_title"] or "无标题"
        
        logger.info(f"  🔄 重试任务: {title[:40]}... | {url[:60]}")
        
        # 重试循环
        for attempt in range(1, _max_retries + 1):
            try:
                # 爬取详情页
                html = crawler._fetch_detail_html(url)
                
                if not html:
                    logger.warning(f"    ⚠️ 第{attempt}次重试失败：未获取到HTML")
                    if attempt < _max_retries:
                        time.sleep(_retry_delay)
                        continue
                    else:
                        sqlite_service.update_task_status(
                            task_id, "error", 
                            error_msg=f"重试{_max_retries}次后仍无法获取HTML"
                        )
                        break
                
                # 提取内容
                title_extracted, content = crawler._extract_content_from_initial_state_feed(html)
                
                if not content or len(content) < 50:
                    logger.warning(f"    ⚠️ 第{attempt}次重试失败：内容为空或过短")
                    if attempt < _max_retries:
                        time.sleep(_retry_delay)
                        continue
                    else:
                        sqlite_service.update_task_status(
                            task_id, "error", 
                            error_msg=f"重试{_max_retries}次后仍无法提取内容"
                        )
                        break
                
                # 提取图片
                images = crawler._extract_images_from_html(html)
                
                # 下载图片
                image_paths = []
                if images:
                    from backend.services.crawler.image_utils import download_images
                    image_paths = download_images(images, task_id)
                
                # 更新任务状态
                sqlite_service.update_task_status(
                    task_id=task_id,
                    status="fetched",
                    raw_content=content,
                    image_paths=image_paths,
                )
                
                success_count += 1
                logger.info(f"    ✅ 第{attempt}次重试成功: {len(content)}字符, {len(image_paths)}张图片")
                break
                
            except Exception as e:
                logger.error(f"    ❌ 第{attempt}次重试异常: {e}")
                if attempt < _max_retries:
                    time.sleep(_retry_delay)
                else:
                    sqlite_service.update_task_status(
                        task_id, "error", 
                        error_msg=f"重试{_max_retries}次后仍失败: {str(e)[:200]}"
                    )
        
        # 每个任务之间稍微延迟
        time.sleep(2)
    
    logger.info(f"✅ 重试完成：成功 {success_count}/{len(failed_tasks)} 个任务")
    return success_count
'''

# 读取scheduler.py
with open('backend/services/scheduler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 检查是否已经添加
if '_retry_failed_tasks' in content:
    print('[INFO] 重试函数已存在')
else:
    # 在文件末尾添加重试函数
    content += '\n' + retry_logic
    
    with open('backend/services/scheduler.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('[OK] 已添加重试函数到 scheduler.py')
    print('')
    print('使用方法：')
    print('from backend.services.scheduler import _retry_failed_tasks')
    print('_retry_failed_tasks()  # 重试失败的任务')
