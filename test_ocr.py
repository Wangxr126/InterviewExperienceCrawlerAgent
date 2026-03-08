"""
测试 OCR 功能是否正常工作
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_easyocr_import():
    """测试 easyocr 是否能正常导入"""
    print("=" * 60)
    print("测试 1: 检查 easyocr 模块导入")
    print("=" * 60)
    try:
        import easyocr
        print("✅ easyocr 导入成功")
        print(f"   版本: {easyocr.__version__ if hasattr(easyocr, '__version__') else '未知'}")
        return True
    except ImportError as e:
        print(f"❌ easyocr 导入失败: {e}")
        print("   请运行: pip install easyocr")
        return False
    except Exception as e:
        print(f"❌ easyocr 导入异常: {e}")
        return False


def test_ocr_service():
    """测试 OCR 服务初始化"""
    print("\n" + "=" * 60)
    print("测试 2: 检查 OCR 服务初始化")
    print("=" * 60)
    try:
        from backend.services.crawler.ocr_service import _get_reader
        print("正在初始化 EasyOCR Reader（首次运行会下载模型）...")
        reader = _get_reader()
        print("✅ OCR Reader 初始化成功")
        return True
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ocr_on_sample():
    """测试 OCR 识别功能（如果有测试图片）"""
    print("\n" + "=" * 60)
    print("测试 3: 测试 OCR 识别功能")
    print("=" * 60)
    
    from pathlib import Path
    from backend.config.config import settings
    
    # 查找任意一张测试图片
    post_images_dir = settings.post_images_dir
    if not post_images_dir.exists():
        print(f"⚠️  图片目录不存在: {post_images_dir}")
        return False
    
    # 查找第一张图片
    image_files = list(post_images_dir.rglob("*.jpg")) + list(post_images_dir.rglob("*.png"))
    if not image_files:
        print(f"⚠️  未找到测试图片，跳过识别测试")
        return False
    
    test_image = image_files[0]
    print(f"使用测试图片: {test_image}")
    
    try:
        from backend.services.crawler.ocr_service import ocr_images_to_text
        
        # 构造相对路径
        rel_path = str(test_image.relative_to(post_images_dir))
        print(f"相对路径: {rel_path}")
        
        result = ocr_images_to_text([rel_path], task_id="TEST")
        
        if result:
            print("✅ OCR 识别成功")
            print(f"识别结果（前200字符）:\n{result[:200]}")
            return True
        else:
            print("⚠️  OCR 未识别到文字（可能图片中无文字）")
            return False
            
    except Exception as e:
        print(f"❌ OCR 识别失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "=" * 60)
    print("面经 Agent - OCR 功能测试")
    print("=" * 60)
    print(f"Python 解释器: {sys.executable}")
    print(f"Python 版本: {sys.version}")
    print()
    
    results = []
    
    # 测试 1: 模块导入
    results.append(("easyocr 模块导入", test_easyocr_import()))
    
    # 测试 2: OCR 服务初始化
    if results[0][1]:  # 只有导入成功才继续
        results.append(("OCR 服务初始化", test_ocr_service()))
        
        # 测试 3: OCR 识别
        if results[1][1]:  # 只有初始化成功才继续
            results.append(("OCR 识别功能", test_ocr_on_sample()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status} - {name}")
    
    all_passed = all(r[1] for r in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有测试通过！OCR 功能正常")
    else:
        print("⚠️  部分测试失败，请检查上述错误信息")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
