# Cursor/VSCode UTF-8 编码配置指南

## 问题背景

Windows 系统默认使用 GBK 编码，这会导致：
1. 中文注释乱码
2. Emoji 字符无法显示
3. 文件保存时编码错误

## 解决方案

### 1. 项目级配置（推荐）✅

已为你创建 `.vscode/settings.json`，包含以下配置：

```json
{
  "files.encoding": "utf8",
  "files.autoGuessEncoding": false,
  "[python]": {
    "files.encoding": "utf8"
  },
  // ... 其他语言配置
  "files.eol": "\n",
  "terminal.integrated.profiles.windows": {
    "PowerShell": {
      "source": "PowerShell",
      "args": ["-NoExit", "-Command", "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8"]
    }
  }
}
```

**作用**：
- 所有文件默认使用 UTF-8 编码
- 禁用自动猜测编码（避免误判为 GBK）
- 终端输出使用 UTF-8
- 换行符统一为 LF（`\n`）

### 2. 全局用户配置（可选）

如果想让所有项目都使用 UTF-8：

1. 打开 Cursor
2. 按 `Ctrl + ,` 打开设置
3. 搜索 `files.encoding`
4. 设置为 `utf8`
5. 搜索 `files.autoGuessEncoding`
6. 取消勾选

或者直接编辑用户配置文件：
- Windows: `%APPDATA%\Cursor\User\settings.json`
- 添加上述配置

### 3. Windows 系统级配置（可选，影响所有程序）

#### 方法 A：设置系统区域（推荐）

1. 打开 "控制面板" → "时钟和区域" → "区域"
2. 点击 "管理" 标签
3. 点击 "更改系统区域设置"
4. 勾选 "Beta: 使用 Unicode UTF-8 提供全球语言支持"
5. 重启电脑

**注意**：这会影响所有程序，某些老旧软件可能不兼容。

#### 方法 B：设置 PowerShell 默认编码

在 PowerShell 配置文件中添加：

```powershell
# 查看配置文件路径
$PROFILE

# 编辑配置文件（如果不存在会创建）
notepad $PROFILE

# 添加以下内容：
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 > $null
```

### 4. Python 脚本配置

在 Python 文件开头添加编码声明：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
```

并在代码中明确指定编码：

```python
# 读取文件
with open('file.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# 写入文件
with open('file.txt', 'w', encoding='utf-8') as f:
    f.write(content)
```

### 5. Git 配置

确保 Git 也使用 UTF-8：

```bash
git config --global core.quotepath false
git config --global gui.encoding utf-8
git config --global i18n.commit.encoding utf-8
git config --global i18n.logoutputencoding utf-8
```

## 验证配置

### 1. 检查 Cursor 编码设置

1. 打开任意文件
2. 查看右下角状态栏
3. 应该显示 "UTF-8"

### 2. 测试终端编码

在 Cursor 终端中运行：

```powershell
# PowerShell
[Console]::OutputEncoding
# 应该显示: UTF8

# 测试中文和 emoji
echo "测试中文 ✅ 🎉"
```

### 3. 测试 Python 编码

```python
# test_encoding.py
print("测试中文 ✅ 🎉")
print("编码:", __import__('sys').stdout.encoding)
```

运行：
```bash
python test_encoding.py
```

应该正常显示中文和 emoji。

## 常见问题

### Q1: 已有文件是 GBK 编码怎么办？

**方案 1：使用 Cursor 转换**
1. 打开文件
2. 点击右下角的编码（如 "GBK"）
3. 选择 "通过编码重新打开" → "UTF-8"
4. 保存文件

**方案 2：批量转换**
```python
# convert_to_utf8.py
import os
import chardet

def convert_file(filepath):
    with open(filepath, 'rb') as f:
        raw = f.read()
    
    # 检测编码
    detected = chardet.detect(raw)
    encoding = detected['encoding']
    
    if encoding and encoding.lower() != 'utf-8':
        try:
            # 解码并重新编码为 UTF-8
            content = raw.decode(encoding)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'✓ {filepath}: {encoding} → UTF-8')
        except Exception as e:
            print(f'✗ {filepath}: {e}')

# 转换所有 Python 文件
for root, dirs, files in os.walk('.'):
    for file in files:
        if file.endswith('.py'):
            convert_file(os.path.join(root, file))
```

### Q2: 终端还是显示乱码？

**临时解决**：
```powershell
# 在终端中运行
chcp 65001
```

**永久解决**：
使用 Windows Terminal 代替 PowerShell：
1. 安装 Windows Terminal（Microsoft Store）
2. 在 Cursor 设置中选择 Windows Terminal 作为默认终端

### Q3: Git 提交时出现编码警告？

```bash
# 设置 Git 使用 UTF-8
git config --global core.autocrlf false
git config --global core.safecrlf false
```

## 推荐配置组合

### 最小配置（已完成）✅
- `.vscode/settings.json` 中设置 UTF-8
- Python 文件开头添加编码声明

### 标准配置
- 最小配置 +
- PowerShell 配置文件设置 UTF-8
- Git 全局配置 UTF-8

### 完整配置
- 标准配置 +
- Windows 系统区域设置为 UTF-8
- 使用 Windows Terminal

## 总结

✅ **已为你完成**：
- 创建了 `.vscode/settings.json`，项目级强制使用 UTF-8
- 配置了终端使用 UTF-8 输出

🔧 **建议额外配置**：
- PowerShell 配置文件（如果经常使用终端）
- Git 全局配置（如果使用 Git）

📝 **最佳实践**：
- 所有新文件都会自动使用 UTF-8
- 打开旧文件时检查右下角编码，必要时转换
- Python 代码中明确指定 `encoding='utf-8'`

现在你的项目已经配置好了，以后不会再出现 GBK 编码问题！
