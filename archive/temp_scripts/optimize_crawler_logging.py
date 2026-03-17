import sys
import io

# 设置UTF-8输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1. 优化nowcoder_crawler.py的日志
with open('backend/services/crawler/nowcoder_crawler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 将详细的info日志改为debug
replacements = [
    # 列表页请求日志
    ('logger.info(f"牛客 请求列表页: keyword={keyword!r}, page={page}")',
     'logger.debug(f"牛客 请求列表页: keyword={keyword!r}, page={page}")'),
    
    # 列表页发现日志（每页都打印）
    ('logger.info(f"牛客 [{page}/20] 列表页发现: 本页 {len(records)} 条")',
     'logger.debug(f"牛客 [{page}/20] 列表页发现: 本页 {len(records)} 条")'),
    
    # 单条帖子发现日志（每条都打印）
    ('logger.info(f"牛客 [{idx}/{len(records)}] 列表页发现: {title[:30]}... | {post_url}")',
     'logger.debug(f"牛客 [{idx}/{len(records)}] 列表页发现: {title[:30]}... | {post_url}")'),
    
    # 每个关键词的统计（保留，但简化）
    ('logger.info(f"牛客 keyword={keyword!r} 发现 {len(results)} 条")',
     'logger.debug(f"牛客 keyword={keyword!r} 发现 {len(results)} 条")'),
    
    ('logger.info(f"牛客 keyword={keyword} page={page} 发现 {len(results)} 条")',
     'logger.debug(f"牛客 keyword={keyword} page={page} 发现 {len(results)} 条")'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('backend/services/crawler/nowcoder_crawler.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] 已优化 nowcoder_crawler.py 的日志级别')
print('  - 列表页请求日志: INFO → DEBUG')
print('  - 单条帖子发现日志: INFO → DEBUG')
print('  - 每页统计日志: INFO → DEBUG')

# 2. 优化scheduler.py的日志
with open('backend/services/scheduler.py', 'r', encoding='utf-8') as f:
    content = f.read()

scheduler_replacements = [
    # 每个帖子的处理日志
    ('logger.info(f"  📄 正在处理帖子: {post_title[:60]}...")',
     'logger.debug(f"  📄 正在处理帖子: {post_title[:60]}...")'),
    
    # 提取完成日志（每个帖子都打印）
    ('logger.info(f"  ✅ 提取完成(正文) [{post_title[:40]}]: {count} 道题目入库")',
     'logger.debug(f"  ✅ 提取完成(正文) [{post_title[:40]}]: {count} 道题目入库")'),
    
    ('logger.info(f"  ✅ 提取完成(图片) [{post_title[:40]}]: {count} 道题目入库")',
     'logger.debug(f"  ✅ 提取完成(图片) [{post_title[:40]}]: {count} 道题目入库")'),
]

for old, new in scheduler_replacements:
    if old in content:
        content = content.replace(old, new)

with open('backend/services/scheduler.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('\n[OK] 已优化 scheduler.py 的日志级别')
print('  - 单个帖子处理日志: INFO → DEBUG')
print('  - 提取完成日志: INFO → DEBUG')

print('\n✅ 优化完成！现在只会显示汇总信息：')
print('  - 发现任务开始/完成')
print('  - 处理任务开始/完成')
print('  - 错误和警告信息')
print('\n如需查看详细日志，可以调整日志级别为DEBUG')
