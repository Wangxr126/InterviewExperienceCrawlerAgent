import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

files = [
    'web/src/views/CollectView.vue',
    'web/src/views/BrowseView.vue', 
    'web/src/views/FinetuneView.vue'
]

for file in files:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        print(f'\n=== {file} ===')
        
        # 查找onMounted
        if 'onMounted' in content:
            print('[OK] 有 onMounted')
        else:
            print('[MISS] 没有 onMounted')
            
        # 查找onActivated
        if 'onActivated' in content:
            print('[OK] 有 onActivated')
        else:
            print('[MISS] 没有 onActivated - 需要添加！')
            
        # 查找watch
        if 'watch(' in content:
            print('[OK] 有 watch')
        else:
            print('[INFO] 没有 watch')
            
    except Exception as e:
        print(f'读取失败: {e}')

print('\n\n解决方案：')
print('需要在每个页面添加 onActivated 钩子，在页面激活时重新加载数据')
print('onActivated 会在 keep-alive 组件激活时触发')
