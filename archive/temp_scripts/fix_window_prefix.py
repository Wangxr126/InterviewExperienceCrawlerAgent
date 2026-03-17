with open('backend/services/crawler/nowcoder_crawler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复正则表达式：添加 window. 前缀
old_pattern = r'r"__INITIAL_STATE__\s*=\s*(\{)"'
new_pattern = r'r"window\.__INITIAL_STATE__\s*=\s*(\{)"'

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    
    with open('backend/services/crawler/nowcoder_crawler.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('[OK] 已修复正则表达式！')
    print('')
    print('关键修改：')
    print('- 旧: r"__INITIAL_STATE__\\s*=\\s*(\\{)"')
    print('- 新: r"window.__INITIAL_STATE__\\s*=\\s*(\\{)"')
    print('')
    print('这是关键问题！test4.py使用的是 window.__INITIAL_STATE__')
    print('而之前的代码只搜索 __INITIAL_STATE__，导致无法匹配！')
else:
    print('[WARN] 未找到目标代码')
    print('正在搜索其他可能的模式...')
    
    # 尝试其他可能的格式
    if '__INITIAL_STATE__' in content:
        print('[INFO] 找到 __INITIAL_STATE__，手动替换...')
        content = content.replace(
            'r"__INITIAL_STATE__\\s*=\\s*(\\{)"',
            'r"window.__INITIAL_STATE__\\s*=\\s*(\\{)"'
        )
        content = content.replace(
            'r\'__INITIAL_STATE__\\s*=\\s*(\\{)\'',
            'r\'window.__INITIAL_STATE__\\s*=\\s*(\\{)\''
        )
        
        with open('backend/services/crawler/nowcoder_crawler.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print('[OK] 已修复！')
