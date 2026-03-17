"""
验证配置是否正确
"""
import sys
sys.path.insert(0, 'backend')

try:
    from backend.config.config import settings
    
    print('[OK] 配置加载成功')
    print('')
    print('验证关键配置：')
    print(f'  backend_data_dir: {settings.backend_data_dir}')
    print(f'  post_images_dir: {settings.post_images_dir}')
    print(f'  nowcoder_output_dir: {settings.nowcoder_output_dir}')
    print(f'  ocr_method: {settings.ocr_method}')
    print(f'  mcp_ocr_server: {settings.mcp_ocr_server}')
    print('')
    print('✅ 所有配置都正常！')
    print('现在可以启动后端服务了：python run.py')
    
except Exception as e:
    print(f'[ERROR] 配置加载失败: {e}')
    import traceback
    traceback.print_exc()
