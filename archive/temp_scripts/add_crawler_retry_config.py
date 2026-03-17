with open('思路/.env', 'r', encoding='utf-8') as f:
    content = f.read()

# 在EXTRACTOR_MAX_RETRIES后添加爬虫重试配置
if 'CRAWLER_FETCH_MAX_RETRIES' not in content:
    # 找到EXTRACTOR_MAX_RETRIES的位置
    lines = content.split('\n')
    new_lines = []
    
    for line in lines:
        new_lines.append(line)
        if line.startswith('EXTRACTOR_MAX_RETRIES='):
            # 在这一行后添加爬虫重试配置
            new_lines.append('')
            new_lines.append('# 爬虫重试配置')
            new_lines.append('CRAWLER_FETCH_MAX_RETRIES=3')
            new_lines.append('CRAWLER_RETRY_DELAY=5')
    
    content = '\n'.join(new_lines)
    
    with open('思路/.env', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('[OK] 已添加爬虫重试配置到 思路/.env')
else:
    print('[INFO] 配置已存在')

print('\n配置说明：')
print('- CRAWLER_FETCH_MAX_RETRIES=3  # 爬取失败最大重试3次')
print('- CRAWLER_RETRY_DELAY=5        # 重试间隔5秒')
