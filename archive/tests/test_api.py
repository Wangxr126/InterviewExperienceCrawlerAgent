import requests

try:
    response = requests.get('http://localhost:8000/api/crawler/tasks?limit=5')
    data = response.json()
    
    print("API 返回状态:", response.status_code)
    print("\n返回的任务数量:", len(data.get('tasks', [])))
    
    if data.get('tasks'):
        print("\n第一条记录的字段:")
        first_task = data['tasks'][0]
        for key in sorted(first_task.keys()):
            value = first_task[key]
            if isinstance(value, str) and len(value) > 50:
                value = value[:50] + '...'
            print(f"  {key}: {value}")
        
        # 检查是否有 id 字段
        if 'id' in first_task:
            print(f"\n✅ API 返回了 id 字段！值为: {first_task['id']}")
        else:
            print("\n❌ API 没有返回 id 字段！")
            print("   可能原因：后端服务未重启")
    else:
        print("\n没有任务记录")
        
except requests.exceptions.ConnectionError:
    print("❌ 无法连接到后端服务，请确认后端是否在运行")
except Exception as e:
    print(f"❌ 错误: {e}")
