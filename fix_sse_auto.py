#!/usr/bin/env python3
"""
SSE 流式一键修复脚本
自动检测问题并应用修复
"""
import sys
from pathlib import Path
import re

def fix_vite_config():
    """修复 Vite 代理配置"""
    print("\n" + "="*60)
    print("🔧 修复 Vite 代理配置")
    print("="*60)
    
    vite_config = Path("web/vite.config.js")
    if not vite_config.exists():
        print("❌ web/vite.config.js 不存在")
        return False
    
    content = vite_config.read_text(encoding='utf-8')
    
    # 检查是否已经有正确的配置
    if "timeout: 0" in content and "proxyTimeout: 0" in content:
        print("✅ Vite 代理配置已正确")
        return True
    
    # 查找 proxy 配置块
    if "'/api/chat/stream'" not in content:
        print("⚠️ 未找到 SSE 代理配置，需要手动添加")
        print("\n请在 web/vite.config.js 的 proxy 配置中添加：")
        print("""
    '/api/chat/stream': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      timeout: 0,
      proxyTimeout: 0,
      configure: (proxy) => {
        proxy.on('proxyRes', (proxyRes, req, res) => {
          proxyRes.headers['cache-control'] = 'no-cache, no-transform'
          proxyRes.headers['x-accel-buffering'] = 'no'
          proxyRes.headers['connection'] = 'keep-alive'
        })
      },
    },
        """)
        return False
    
    # 修复 timeout 配置
    if "timeout: 0" not in content:
        content = re.sub(
            r"('/api/chat/stream':\s*\{[^}]*?)(?=\n\s*\})",
            r"\1,\n      timeout: 0",
            content,
            flags=re.DOTALL
        )
        print("✅ 添加 timeout: 0")
    
    if "proxyTimeout: 0" not in content:
        content = re.sub(
            r"('/api/chat/stream':\s*\{[^}]*?)(?=\n\s*\})",
            r"\1,\n      proxyTimeout: 0",
            content,
            flags=re.DOTALL
        )
        print("✅ 添加 proxyTimeout: 0")
    
    vite_config.write_text(content, encoding='utf-8')
    print("✅ Vite 代理配置已修复")
    return True


def check_backend_sse():
    """检查后端 SSE 配置"""
    print("\n" + "="*60)
    print("🔍 检查后端 SSE 配置")
    print("="*60)
    
    main_py = Path("backend/main.py")
    if not main_py.exists():
        print("❌ backend/main.py 不存在")
        return False
    
    content = main_py.read_text(encoding='utf-8')
    
    checks = [
        ("StreamingResponse 导入", "from fastapi.responses import StreamingResponse"),
        ("chat/stream 接口", '@app.post("/api/chat/stream")'),
        ("text/event-stream 媒体类型", 'media_type="text/event-stream"'),
        ("no-cache 头", '"Cache-Control": "no-cache, no-transform"'),
        ("keep-alive 头", '"Connection": "keep-alive"'),
        ("X-Accel-Buffering 头", '"X-Accel-Buffering": "no"'),
    ]
    
    all_ok = True
    for check_name, check_str in checks:
        if check_str in content:
            print(f"✅ {check_name}")
        else:
            print(f"❌ {check_name} - 缺失")
            all_ok = False
    
    return all_ok


def check_frontend_api():
    """检查前端 API 配置"""
    print("\n" + "="*60)
    print("🔍 检查前端 API 配置")
    print("="*60)
    
    api_js = Path("web/src/api.js")
    if not api_js.exists():
        print("❌ web/src/api.js 不存在")
        return False
    
    content = api_js.read_text(encoding='utf-8')
    
    checks = [
        ("chatStream 方法", "async chatStream(payload, signal)"),
        ("text/event-stream Accept 头", "'Accept': 'text/event-stream'"),
        ("返回 Response 对象", "return fetch"),
    ]
    
    all_ok = True
    for check_name, check_str in checks:
        if check_str in content:
            print(f"✅ {check_name}")
        else:
            print(f"❌ {check_name} - 缺失")
            all_ok = False
    
    return all_ok


def check_frontend_chatview():
    """检查前端 ChatView 配置"""
    print("\n" + "="*60)
    print("🔍 检查前端 ChatView 配置")
    print("="*60)
    
    chat_view = Path("web/src/views/ChatView.vue")
    if not chat_view.exists():
        print("❌ web/src/views/ChatView.vue 不存在")
        return False
    
    content = chat_view.read_text(encoding='utf-8')
    
    checks = [
        ("SSE 流处理", "res.body.getReader()"),
        ("TextDecoder", "new TextDecoder()"),
        ("事件分割", "split('\\n\\n')"),
        ("handleEvent 函数", "const handleEvent = (payload)"),
        ("llm_chunk 处理", "evType === 'llm_chunk'"),
        ("agent_finish 处理", "evType === 'agent_finish'"),
    ]
    
    all_ok = True
    for check_name, check_str in checks:
        if check_str in content:
            print(f"✅ {check_name}")
        else:
            print(f"❌ {check_name} - 缺失")
            all_ok = False
    
    return all_ok


def main():
    print("\n" + "="*60)
    print("🚀 SSE 流式一键修复")
    print("="*60)
    
    # 检查所有配置
    backend_ok = check_backend_sse()
    frontend_api_ok = check_frontend_api()
    frontend_chatview_ok = check_frontend_chatview()
    
    # 尝试修复 Vite 配置
    vite_ok = fix_vite_config()
    
    print("\n" + "="*60)
    print("📊 修复结果")
    print("="*60)
    
    results = [
        ("后端 SSE 配置", backend_ok),
        ("前端 API 配置", frontend_api_ok),
        ("前端 ChatView 配置", frontend_chatview_ok),
        ("Vite 代理配置", vite_ok),
    ]
    
    for name, ok in results:
        status = "✅" if ok else "❌"
        print(f"{status} {name}")
    
    all_ok = all(ok for _, ok in results)
    
    if all_ok:
        print("\n✅ 所有配置都正确！")
        print("\n📝 后续步骤：")
        print("1. 重启后端: python run.py")
        print("2. 重启前端: cd web && npm run dev")
        print("3. 打开浏览器: http://localhost:5173")
        print("4. 清除浏览器缓存（Ctrl+Shift+Delete）")
        print("5. 发送消息测试流式输出")
        print("6. 如果仍不工作，在控制台运行: diagnoseSseStream()")
    else:
        print("\n⚠️ 发现配置问题")
        print("\n📝 需要手动修复的项目：")
        for name, ok in results:
            if not ok:
                print(f"  - {name}")
        print("\n查看 SSE_COMPLETE_FIX.md 获取详细说明")
    
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
