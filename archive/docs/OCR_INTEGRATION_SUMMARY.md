# 牛客图片下载与OCR集成总结

## 完成的工作

### 1. 图片下载测试 ✅

创建了测试文件 `测试牛客图片下载.py`，实现了以下功能：

- **自动搜索包含图片的帖子**：遍历牛客搜索结果，找到包含图片的面经帖子
- **图片下载功能**：从牛客帖子中提取图片URL并下载到本地
- **测试结果**：成功下载了1张图片到 `牛客图片测试` 目录

**测试文件位置**：`e:\Agent\AgentProject\wxr_agent\测试牛客图片下载.py`

**下载的图片**：`e:\Agent\AgentProject\wxr_agent\牛客图片测试\image_1.jpg`

### 2. OCR集成方案设计 ✅

项目中已经存在两个OCR服务：

1. **ocr_service.py** - 使用 EasyOCR 本地识别
2. **ocr_service_mcp.py** - 使用 MCP 协议调用 OCR 服务（支持 Claude Vision API）

### 3. 需要集成的位置

在 `backend/services/crawler/question_extractor.py` 的 `extract_questions_from_post` 函数中添加OCR回退机制：

**集成逻辑**：
```python
1. 正常提取题目（使用LLM从正文提取）
2. 如果提取失败（返回空或解析错误）
3. 检查是否有图片路径（image_paths参数）
4. 如果有图片，调用OCR服务识别图片内容
5. 将OCR结果追加到原始内容
6. 使用增强后的内容重新调用LLM提取题目
7. 标记提取来源为"ocr"
```

## 需要修改的代码

### 修改1：`extract_questions_from_post` 函数签名

**文件**：`backend/services/crawler/question_extractor.py`

**位置**：约第430行

**修改内容**：添加 `image_paths` 参数

```python
def extract_questions_from_post(
    content: str,
    platform: str = "nowcoder",
    company: str = "",
    position: str = "",
    business_line: str = "",
    difficulty: str = "",
    source_url: str = "",
    post_title: str = "",
    extraction_source: str = "content",
    image_paths: List[str] = None,  # 新增参数
) -> Tuple[List[Dict], str]:
```

### 修改2：添加OCR回退逻辑

**文件**：`backend/services/crawler/question_extractor.py`

**位置**：约第475行，在重试循环的else分支中

**修改内容**：在 `return [], status` 之前添加OCR回退逻辑

```python
else:
    logger.error(f"提取失败，已达最大重试次数 {max_retries}: {source_url}")
    if not items:
        logger.warning(f"LLM 未提取到题目: {source_url}")
        if raw:
            logger.info(f"LLM 原始返回（前500字）: {raw[:500]}")
        
        # ═══ OCR 回退机制 ═══
        if image_paths and len(image_paths) > 0:
            logger.info(f"🔍 正文提取失败，尝试 OCR 识别图片内容（共 {len(image_paths)} 张图片）")
            try:
                from backend.services.crawler.ocr_service_mcp import ocr_images_to_text
                
                # 调用 OCR 服务识别图片
                ocr_text = ocr_images_to_text(image_paths, task_id=source_url)
                
                if ocr_text and len(ocr_text.strip()) > 20:
                    logger.info(f"✅ OCR 识别成功，识别到 {len(ocr_text)} 字符")
                    
                    # 将 OCR 结果追加到原始内容
                    enhanced_content = f"{full_content}\n\n## 图片内容（OCR识别）\n{ocr_text}"
                    enhanced_user_prompt = format_miner_user_prompt(enhanced_content)
                    
                    # 使用增强后的内容再次尝试提取
                    logger.info("🔄 使用 OCR 增强内容重新提取题目...")
                    t0 = time.perf_counter()
                    raw_ocr = _call_llm(enhanced_user_prompt)
                    llm_response_time_sec = time.perf_counter() - t0
                    
                    items_ocr, status_ocr = _parse_json_from_llm(raw_ocr, user_prompt_for_debug=enhanced_user_prompt)
                    
                    _append_llm_log_to_csv(enhanced_user_prompt, raw_ocr or "", llm_response_time_sec, 
                                           source=platform, title=f"[OCR增强] {post_title}", source_url=source_url)
                    
                    if status_ocr == "ok" and items_ocr:
                        logger.info(f"🎉 OCR 增强提取成功！提取到 {len(items_ocr)} 道题目")
                        items = items_ocr
                        status = status_ocr
                        extraction_source = "ocr"  # 标记为 OCR 提取
                    else:
                        logger.warning(f"OCR 增强提取仍然失败，状态: {status_ocr}")
                else:
                    logger.warning("OCR 未识别到有效文字内容")
            except Exception as e:
                logger.error(f"OCR 回退机制执行失败: {e}", exc_info=True)
        
        # 如果 OCR 也失败了，返回空结果
        if not items:
            return [], status
```

### 修改3：调用方传递图片路径

**需要修改的文件**：所有调用 `extract_questions_from_post` 的地方

**主要位置**：
- `backend/main.py` - 爬虫接口
- `backend/services/scheduler.py` - 定时任务
- 其他调用该函数的地方

**修改示例**：
```python
# 原来的调用
questions, status = extract_questions_from_post(
    content=content,
    platform="nowcoder",
    company=post["company"],
    position=post["position"],
    source_url=post["source_url"],
    post_title=post["title"],
)

# 修改后的调用（传递图片路径）
questions, status = extract_questions_from_post(
    content=content,
    platform="nowcoder",
    company=post["company"],
    position=post["position"],
    source_url=post["source_url"],
    post_title=post["title"],
    image_paths=image_urls,  # 传递图片URL列表
)
```

## 配置要求

### OCR服务配置

在 `backend/config/config.py` 中需要配置：

```python
# OCR 方法选择：'claude_vision' 或 'mcp' 或 'easyocr'
ocr_method: str = "claude_vision"  # 默认使用 Claude Vision API

# Claude API Key（用于 Vision OCR）
anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

# MCP OCR 服务器名称（如果使用 MCP）
mcp_ocr_server: str = os.getenv("MCP_OCR_SERVER", "ocr-server")

# 图片存储目录
post_images_dir: Path = PROJECT_ROOT / "post_images"
```

## 使用流程

1. **爬取帖子时下载图片**：
   - 牛客爬虫已经支持提取图片URL（`fetch_post_content_full` 返回图片列表）
   - 需要将图片下载到本地并保存路径

2. **提取题目时传递图片路径**：
   - 调用 `extract_questions_from_post` 时传递 `image_paths` 参数
   - 图片路径格式：相对路径列表，如 `["TASK_XXX/0.jpg", "TASK_XXX/1.png"]`

3. **自动OCR回退**：
   - 当正文提取失败时，自动调用OCR识别图片
   - OCR结果追加到正文后重新提取
   - 提取成功的题目标记为 `extraction_source="ocr"`

## 测试建议

1. **单元测试**：测试OCR回退机制是否正常工作
2. **集成测试**：使用包含图片的真实牛客帖子测试完整流程
3. **性能测试**：测试OCR识别的速度和准确率

## 注意事项

1. **API成本**：Claude Vision API 按图片数量计费，需要控制成本
2. **识别准确率**：OCR可能无法100%准确识别，需要人工审核
3. **图片格式**：支持 jpg、png、gif、webp 等常见格式
4. **图片大小**：Claude Vision API 对图片大小有限制（通常5MB以内）
5. **并发控制**：OCR识别可能较慢，需要合理控制并发数

## 下一步工作

1. ✅ 完成图片下载测试
2. ⏳ 修改 `question_extractor.py` 添加OCR回退逻辑
3. ⏳ 修改调用方传递图片路径
4. ⏳ 配置OCR服务（Claude API Key）
5. ⏳ 端到端测试
6. ⏳ 部署上线

## 相关文件

- `测试牛客图片下载.py` - 图片下载测试脚本
- `backend/services/crawler/nowcoder_crawler.py` - 牛客爬虫（已支持图片提取）
- `backend/services/crawler/question_extractor.py` - 题目提取器（需要添加OCR回退）
- `backend/services/crawler/ocr_service.py` - EasyOCR 服务
- `backend/services/crawler/ocr_service_mcp.py` - MCP OCR 服务（支持 Claude Vision）
- `backend/agents/miner_agent.py` - Miner Agent（题目提取Agent）
- `backend/prompts/miner_prompt.py` - Miner Prompt（题目提取提示词）
