"""
为BrowseView添加isActive监听
"""

with open('web/src/views/BrowseView.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 添加isActive prop
old_props = """const props = defineProps({
  meta: { type: Object, default: () => ({}) }
})"""

new_props = """const props = defineProps({
  meta: { type: Object, default: () => ({}) },
  isActive: { type: Boolean, default: false }
})"""

content = content.replace(old_props, new_props)

# 2. 在onMounted后添加watch
old_mounted = """onMounted(loadQuestions)

// 页面激活时重新加载数据（解决删除后切换页面数据不刷新的问题）
onActivated(loadQuestions)"""

new_mounted = """onMounted(loadQuestions)

// 监听isActive变化，当页面激活时重新加载数据
watch(() => props.isActive, (newVal, oldVal) => {
  if (newVal && !oldVal) {
    // 从非激活变为激活，重新加载数据
    loadQuestions()
  }
})"""

content = content.replace(old_mounted, new_mounted)

with open('web/src/views/BrowseView.vue', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] 已为 BrowseView 添加 isActive 监听')
print('修改：')
print('1. 添加 isActive prop')
print('2. 用 watch 替换 onActivated')
print('3. 当页面激活时自动重新加载数据')
