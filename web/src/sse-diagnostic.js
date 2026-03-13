/**
 * SSE 流式诊断工具
 * 在浏览器控制台运行，检查前端是否正确接收 SSE 数据
 */

export async function diagnoseSseStream() {
  console.log('\n' + '='.repeat(60))
  console.log('🔍 SSE 流式诊断工具')
  console.log('='.repeat(60))

  const payload = {
    user_id: 'test_user',
    message: '出一道 Python 面试题',
    session_id: `test_${Date.now()}`
  }

  console.log('\n📤 发送请求到 /api/chat/stream')
  console.log('payload:', payload)
  console.log('⏳ 等待响应...\n')

  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream'
      },
      body: JSON.stringify(payload)
    })

    console.log('📊 HTTP 状态:', res.status)
    console.log('📋 响应头:')
    console.log('  content-type:', res.headers.get('content-type'))
    console.log('  cache-control:', res.headers.get('cache-control'))
    console.log('  connection:', res.headers.get('connection'))
    console.log('  x-accel-buffering:', res.headers.get('x-accel-buffering'))

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }

    if (!res.body) {
      throw new Error('响应无 body，无法读取流')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let eventCount = 0
    let chunkCount = 0
    let startTime = Date.now()

    console.log('\n🔄 开始接收流式数据...\n')

    while (true) {
      const { done, value } = await reader.read()

      if (done) {
        console.log(`\n✅ 流完成！`)
        console.log(`   总事件数: ${eventCount}`)
        console.log(`   总 chunk 数: ${chunkCount}`)
        console.log(`   耗时: ${Date.now() - startTime}ms`)
        break
      }

      // 解码数据块
      const chunk = decoder.decode(value, { stream: true })
      buffer += chunk

      console.log(`[接收块] 大小=${chunk.length}字节, 缓冲=${buffer.length}字节`)

      // 按 \n\n 分割事件
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const eventBlock of lines) {
        if (!eventBlock.trim()) continue

        eventCount++
        console.log(`\n[事件 #${eventCount}]`)
        console.log(`  原始块: ${eventBlock.substring(0, 80)}...`)

        // 解析 SSE 格式
        let eventType = ''
        let dataLine = ''

        for (const line of eventBlock.split('\n')) {
          const trimmed = line.trim()
          if (trimmed.startsWith('event: ')) {
            eventType = trimmed.slice(7)
          } else if (trimmed.startsWith('data: ')) {
            dataLine = trimmed.slice(6)
          }
        }

        if (!dataLine) {
          console.log('  ⚠️ 无 data 字段')
          continue
        }

        try {
          const payload = JSON.parse(dataLine)
          const type = payload.type || eventType

          console.log(`  事件类型: ${type}`)

          if (type === 'llm_chunk') {
            const chunk = payload.data?.chunk || payload.data?.content || ''
            if (chunk) {
              chunkCount++
              console.log(`  📝 Chunk #${chunkCount}: "${chunk.substring(0, 50)}${chunk.length > 50 ? '...' : ''}"`)
            }
          } else if (type === 'agent_finish') {
            const result = payload.data?.result || ''
            console.log(`  ✅ 完成: "${result.substring(0, 100)}${result.length > 100 ? '...' : ''}"`)
          } else if (type === 'step_start') {
            console.log(`  🎬 步骤开始`)
          } else if (type === 'tool_call_finish') {
            const toolName = payload.data?.tool_name || ''
            console.log(`  🔧 工具完成: ${toolName}`)
          } else if (type === 'error') {
            console.log(`  ❌ 错误: ${payload.data?.error || '未知'}`)
          } else {
            console.log(`  📌 数据: ${JSON.stringify(payload.data).substring(0, 100)}`)
          }
        } catch (e) {
          console.warn(`  ❌ JSON 解析失败: ${e.message}`)
          console.warn(`  原始数据: ${dataLine.substring(0, 100)}`)
        }

        if (eventCount >= 30) {
          console.log(`\n... (已显示前 30 个事件，继续接收中...)`)
          // 继续接收但不打印
          continue
        }
      }
    }
  } catch (err) {
    console.error('❌ 诊断失败:', err)
    console.error('错误类型:', err.name)
    console.error('错误消息:', err.message)
    console.error('堆栈:', err.stack)
  }
}

// 导出给控制台使用
window.diagnoseSseStream = diagnoseSseStream

console.log('✅ SSE 诊断工具已加载')
console.log('在控制台运行: diagnoseSseStream()')
