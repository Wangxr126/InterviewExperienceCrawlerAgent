# UTF-8 编码配置 - 快速参考

## ✅ 已完成配置

### 1. 项目级配置
已创建 `.vscode/settings.json`，包含：
- 所有文件强制使用 UTF-8
- 禁用自动编码猜测
- 终端使用 UTF-8 输出
- 换行符统一为 LF

**生效范围**：当前项目（`wxr_agent`）

## 🔧 可选配置

### 2. 全局用户配置（所有项目生效）

**方法 1：通过 UI**
1. `Ctrl + ,` 打开设置
2. 搜索 `files.encoding` → 设置为 `utf8`
3. 搜索 `files.autoGuessEncoding` → 取消勾选

**方法 2：编辑配置文件**
```bash
# 打开用户配置
code %APPDATA%\Cursor\User\settings.json

# 添加：
{
  "files.encoding": "utf8",
  "files.autoGuessEncoding": false
}
```

### 3. PowerShell 配置（终端不乱码）

```powershell
# 1. 查看配置文件路径
$PROFILE

# 2. 创建/编辑配置文件
notepad $PROFILE

# 3. 添加以下内容并保存：
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 > $null
```

### 4. Git 配置（避免提交警告）

```bash
git config --global core.quotepath false
git config --global gui.encoding utf-8
git config --global i18n.commit.encoding utf-8
git config --global i18n.logoutputencoding utf-8
```

## 📋 检查清单

- [x] 项目配置（`.vscode/settings.json`）✅ 已完成
- [ ] 全局用户配置（可选，推荐）
- [ ] PowerShell 配置（可选，如果经常用终端）
- [ ] Git 配置（可选，如果使用 Git）

## 🚀 快速验证

### 检查 Cursor 编码
打开任意文件，查看右下角状态栏，应显示 "UTF-8"

### 测试终端
```powershell
echo "测试中文 ✅ 🎉"
```

### 测试 Python
```python
print("测试中文 ✅ 🎉")
```

## 🔥 常见问题速查

### 问题：旧文件还是乱码
**解决**：
1. 点击右下角编码
2. "通过编码重新打开" → "UTF-8"
3. 保存

### 问题：终端还是乱码
**临时**：`chcp 65001`
**永久**：配置 PowerShell（见上方）

### 问题：Git 提交警告
**解决**：运行 Git 配置命令（见上方）

## 📚 详细文档

查看 `UTF8_ENCODING_GUIDE.md` 获取完整说明。

---

**总结**：项目级配置已完成，以后在这个项目中不会再有 GBK 问题！如果想让所有项目都生效，按照上面的"全局用户配置"操作即可。
