<template>
  <div class="finetune-container">
    <!-- 顶部统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card primary">
        <div class="stat-icon">📊</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total ?? '-' }}</div>
          <div class="stat-label">样本总数</div>
        </div>
      </div>
      <div class="stat-card warning">
        <div class="stat-icon">⏳</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.pending ?? '-' }}</div>
          <div class="stat-label">待标注</div>
        </div>
      </div>
      <div class="stat-card success">
        <div class="stat-icon">✅</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.labeled ?? '-' }}</div>
          <div class="stat-label">已标注</div>
        </div>
      </div>
      <div class="stat-card info">
        <div class="stat-icon">✏️</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.modified ?? '-' }}</div>
          <div class="stat-label">手动修改</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">📁</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.log_files ?? '-' }}</div>
          <div class="stat-label">日志文件</div>
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="action-bar">
      <el-button @click="loadStats" :icon="Refresh" size="large">刷新统计</el-button>
      <el-button @click="autoImportAll" :loading="autoImporting" type="primary" size="large">
        {{ autoImporting ? '同步中...' : '🔄 同步日志' }}
      </el-button>
      <el-tooltip
        content="修复 stage2 不完整样本：用 stage1 自动补齐缺失字段"
        placement="top"
      >
        <el-button @click="fixMergedSamples" :loading="fixMergedLoading" size="large">
          {{ fixMergedLoading ? '修复中...' : '🔧 修复 Stage2 合并' }}
        </el-button>
      </el-tooltip>
      <el-button type="success" @click="exportLabeled" :loading="exporting" size="large">
        导出标注数据
      </el-button>
    </div>

    <!-- 主内容区 -->
    <el-tabs v-model="activeTab" class="content-tabs" @tab-change="onTabChange">
      <!-- Tab 1: 样本列表 -->
      <el-tab-pane label="📋 样本列表" name="list">
        <div class="list-container">
          <div class="list-toolbar">
            <el-radio-group v-model="filterStatus" @change="loadSamples(1)" size="large">
              <el-radio-button value="">全部</el-radio-button>
              <el-radio-button value="pending">待标注</el-radio-button>
              <el-radio-button value="labeled">已标注</el-radio-button>
            </el-radio-group>
            <el-button :icon="Refresh" @click="loadSamples(1)" size="large">刷新</el-button>
            <span v-if="selectedSampleIds.length > 0" class="selected-tip">
              已选 <strong>{{ selectedSampleIds.length }}</strong> 条用于微调
            </span>
            <el-button v-if="selectedSampleIds.length > 0" size="small" @click="clearSampleSelection">清空选择</el-button>
            <el-button v-if="filterStatus === 'labeled' && samples.length > 0" size="small" type="primary" @click="selectAllLabeledOnPage">
              全选本页
            </el-button>
          </div>
          
          <el-table
            ref="sampleTableRef"
            :data="samples"
            class="sample-table"
            row-key="id"
            @row-click="onSampleClick"
            @selection-change="onSampleSelectionChange"
          >
            <el-table-column type="selection" width="40" align="center" :selectable="row => row.status === 'labeled'" reserve-selection />
            <el-table-column label="ID" prop="id" width="50" align="center" />
            <el-table-column label="标题" width="240">
              <template #default="{ row }">
                <div class="title-cell" :title="row.title || row.post_title || ''">
                  {{ row.title || row.post_title || '—' }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="面经内容">
              <template #default="{ row }">
                <div class="content-cell">{{ getBodyPreview(row.content_preview) }}</div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status === 'labeled' ? 'success' : 'warning'" size="large">
                  {{ row.status === 'labeled' ? '已标注' : '待标注' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="手动修改" width="96" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_modified" type="danger" size="large">已修改</el-tag>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" prop="created_at" width="146" class-name="time-col" />
            <el-table-column label="修改时间" prop="modified_at" width="146" class-name="time-col" />
            <el-table-column label="操作" width="72" align="center" fixed="right">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click.stop="deleteSample(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          
          <el-pagination 
            class="pagination"
            background 
            layout="prev, pager, next, total"
            :total="pagerTotal" 
            :page-size="pageSize"
            :current-page="currentPage" 
            @current-change="loadSamples" 
          />
        </div>
      </el-tab-pane>

      <!-- Tab 2: 标注编辑器 -->
      <el-tab-pane label="✏️ 标注编辑" name="editor">
        <div class="editor-container" v-if="currentSample">
          <!-- 编辑器头部 -->
          <div class="editor-header" ref="editorHeaderRef">
            <div class="header-left">
              <span class="sample-id">样本 #{{ currentSample.id }}</span>
              <el-tag :type="currentSample.status === 'labeled' ? 'success' : 'warning'" size="large">
                {{ currentSample.status === 'labeled' ? '已标注' : '待标注' }}
              </el-tag>
              <el-tag v-if="isModified" type="danger" size="large">已修改</el-tag>
            </div>
            <div class="header-right">
              <span class="time-info">创建：{{ currentSample.created_at }}</span>
              <span v-if="currentSample.modified_at" class="time-info">修改：{{ currentSample.modified_at }}</span>
              <span v-if="currentSample.labeled_at" class="time-info">标注：{{ currentSample.labeled_at }}</span>
            </div>
          </div>

          <!-- 帖子信息 -->
          <div class="post-info" v-if="currentSample.title || currentSample.post_title || currentSample.source_url || currentSample.url" ref="postInfoRef">
            <div class="post-info-title" v-if="currentSample.title || currentSample.post_title">
              <span class="post-info-label">标题</span>
              <span class="post-info-text" :title="currentSample.title || currentSample.post_title">
                {{ currentSample.title || currentSample.post_title }}
              </span>
            </div>
            <div class="post-info-url" v-if="currentSample.source_url || currentSample.url">
              <a
                :href="currentSample.source_url || currentSample.url"
                target="_blank"
                class="post-info-link"
                :title="currentSample.source_url || currentSample.url"
              >
                🔗 原帖 URL
              </a>
            </div>
          </div>

          <!-- 导航按钮（移到顶部） -->
          <div class="navigation-actions-top">
            <el-button @click="gotoPrevSample" :disabled="!hasPrevSample" size="large">
              ← 上一题
            </el-button>
            <span class="sample-progress">{{ currentSampleIndex + 1 }} / {{ samples.length }}</span>
            <el-button @click="gotoNextSample" :disabled="!hasNextSample" size="large">
              下一题 →
            </el-button>
          </div>

          <!-- 三栏布局 -->
          <div class="editor-grid">
            <!-- 左栏：原始面经 -->
            <div class="editor-panel">
              <div class="panel-header">
                <span class="panel-title">① 原始面经原文</span>
              </div>
              
              <div class="panel-content content-auto-height">
                <el-input 
                  type="textarea" 
                  :model-value="currentSample.raw_content || currentSample.content || ''"
                  readonly 
                  :autosize="{ minRows: 20, maxRows: 50 }"
                  class="content-textarea"
                />
              </div>
            </div>

            <!-- 中栏：Stage1 粗提取（MINER_REMOTE，如火山 qwen）（Stage2 内容默认填入③编辑区） -->
            <div class="editor-panel">
              <div class="panel-header">
                <span class="panel-title">② Stage1 粗提取（远程）</span>
                <span class="panel-subtitle">（{{ stage1QuestionCount }} 道题）</span>
                <el-button @click="copyStage1" size="small" style="margin-left: auto;">
                  📋 复制
                </el-button>
              </div>
              <div class="panel-content json-viewer">
                <vue-json-pretty 
                  :data="parseJson(currentSample.stage1_output)"
                  :deep="99"
                  :showLength="true"
                  :showLine="true"
                />
              </div>
            </div>

            <!-- 右栏：标注编辑 + 大模型辅助 -->
            <div class="editor-panel">
              <div class="panel-header">
                <span class="panel-title">③ 标注编辑
                  <el-tag
                    :type="currentSample?.final_output ? 'warning' : 'info'"
                    size="small"
                  >{{ currentSample?.final_output ? '已修改内容' : (currentSample?.stage2_output ? 'Stage2 豆包生成' : 'Stage1 粗提取') }}</el-tag>
                  <span class="panel-subtitle">（{{ editQuestionCount }} 道题）</span>
                </span>
                <el-button 
                  type="primary" 
                  @click="callAssist"
                  :loading="assisting" 
                  size="large"
                >
                  {{ assisting ? '生成中...' : '调用大模型' }}
                </el-button>
              </div>

              <!-- 操作按钮（移到顶部） -->
              <div class="editor-actions-top">
                <el-button type="success" @click="confirmLabel" :loading="labeling" size="large">
                  ✅ 确认标注
                </el-button>
                <el-button type="info" @click="confirmNoChange" :loading="labeling" size="large">
                  ✔️ 无需修改
                </el-button>
              </div>

              <!-- 查找/替换工具栏（Ctrl+F 也可打开编辑器内置搜索） -->
              <div class="find-replace-bar">
                <div class="find-replace-row">
                  <label class="find-replace-label">查找：</label>
                  <el-input
                    v-model="findText"
                    placeholder="输入要查找的内容"
                    size="small"
                    clearable
                    @keyup.enter="doReplace"
                  />
                </div>
                <div class="find-replace-row">
                  <label class="find-replace-label">替换：</label>
                  <el-input
                    v-model="replaceText"
                    placeholder="输入替换内容"
                    size="small"
                    clearable
                    @keyup.enter="doReplace"
                  />
                  <el-button size="small" @click="doReplace">替换</el-button>
                  <el-button size="small" @click="doReplaceAll">全部替换</el-button>
                </div>
              </div>
              <!-- 可编辑的 JSON 编辑器（语法高亮 + 查找替换） -->
              <div class="panel-content json-editor-wrap" @paste="onEditAreaPaste">
                <CodeMirror
                  v-model="editOutput"
                  :basic="true"
                  :tab="true"
                  :wrap="true"
                  :lang="jsonLang"
                  :extensions="[oneDark]"
                  placeholder="在此编辑JSON..."
                  class="json-codemirror"
                />
              </div>
            </div>
          </div>
        </div>
        
        <div v-else class="editor-empty-state">
          <el-empty description="请在「样本列表」中点击一条记录进入编辑" :image-size="180" />
          <el-button type="primary" @click="activeTab = 'list'" size="large">前往样本列表</el-button>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 日志文件 -->
      <el-tab-pane label="📂 导入日志" name="logs">
        <div class="logs-container">
          <!-- 日志文件列表 -->
          <div class="logs-section">
            <div class="section-title">📋 日志文件列表</div>
            <div class="section-subtitle">两阶段对比数据导入（同一题目的 Stage1 Qwen3 vs Stage2 豆包）</div>
            <el-table :data="logFiles" class="logs-table">
              <el-table-column label="模型" prop="model" width="180" />
              <el-table-column label="文件名" prop="filename" />
              <el-table-column label="条数" prop="line_count" width="100" align="center" />
              <el-table-column label="修改时间" prop="mtime" width="200" />
              <el-table-column label="操作" width="260" align="center">
                <template #default="{ row }">
                  <el-button size="large" @click.stop="previewLog(row)">查看</el-button>
                  <el-button size="large" type="primary" @click.stop="importLog(row)">导入</el-button>
                  <el-button size="large" type="danger" link @click.stop="deleteLogFile(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="tip-text">
              💡 预览（「查看」）直接读取 <code>微调/llm_logs/</code> 的 JSONL 文件，不写入数据库；<br />
              导入（「导入」/「导入全部」）会把样本写入 SQLite 表 <code>finetune_samples</code>，并把本次统计写入 <code>finetune_import_logs</code>；重复记录自动跳过
            </div>
          </div>

          <!-- 导入历史 -->
          <div class="logs-section" style="margin-top: 32px;">
            <div class="section-title">📊 导入历史</div>
            <div class="section-subtitle">追踪每次导入的详细信息和失败样本</div>
            <el-table :data="importLogs" class="import-logs-table" max-height="400">
              <el-table-column label="导入ID" prop="import_log_id" width="140" show-overflow-tooltip />
              <el-table-column label="文件名" prop="filename" width="180" show-overflow-tooltip />
              <el-table-column label="成功" prop="imported" width="80" align="center">
                <template #default="{ row }">
                  <el-tag type="success">{{ row.imported }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="跳过" prop="skipped" width="80" align="center">
                <template #default="{ row }">
                  <el-tag type="info">{{ row.skipped }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="失败" prop="failed" width="80" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.failed > 0" type="danger">{{ row.failed }}</el-tag>
                  <span v-else class="text-muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="导入时间" prop="created_at" width="180" />
              <el-table-column label="操作" width="200" align="center">
                <template #default="{ row }">
                  <el-button size="small" @click.stop="viewImportLogDetail(row)">详情</el-button>
                  <el-button size="small" type="danger" link @click.stop="deleteImportLog(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 4: 上传 FAQ -->
      <el-tab-pane label="📤 上传FAQ" name="faq">
        <div class="faq-upload-container">
          <div class="section-title">上传 FAQ 文件（问题+答案）</div>
          <div class="faq-upload-desc">
            支持 CSV / JSON / JSONL / TXT 格式。每行或每条为「问题 + 答案」。
            CSV 列名可为 question/answer、question_text/answer_text、问题/答案。
          </div>
          <el-checkbox v-model="faqSaveToBank" class="faq-checkbox">保存到题库（SQLite + Neo4j）</el-checkbox>
          <el-checkbox v-model="faqSaveToFinetune" class="faq-checkbox">写入微调样本（用于模型 SFT）</el-checkbox>
          <el-upload
            ref="faqUploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="onFaqFileChange"
            :show-file-list="true"
            accept=".csv,.json,.jsonl,.txt"
            drag
          >
            <UploadFilled class="el-icon--upload" />
            <div class="el-upload__text">将文件拖到此处，或<em>点击上传</em></div>
            <template #tip>
              <div class="el-upload__tip">支持 .csv, .json, .jsonl, .txt</div>
            </template>
          </el-upload>
          <el-button
            v-if="faqSelectedFile"
            type="primary"
            size="large"
            :loading="faqUploading"
            @click="submitFaqUpload"
            class="faq-submit-btn"
          >
            {{ faqUploading ? '上传中...' : '上传并导入' }}
          </el-button>
          <div v-if="faqResult" class="faq-result">
            <el-alert
              :title="`解析 ${faqResult.parsed} 条，题库 ${faqResult.bank_saved} 条，微调 ${faqResult.finetune_saved} 条`"
              :type="faqResult.errors?.length ? 'warning' : 'success'"
              show-icon
            />
            <div v-if="faqResult.errors?.length" class="faq-errors">
              <div v-for="(err, i) in faqResult.errors" :key="i">{{ err }}</div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 5: 一键微调 -->
      <el-tab-pane name="oneclick">
        <template #label>
          <span class="tab-label-lora">
            <img src="@/assets/icons/lora-finetune.svg" alt="LoRA" class="lora-tab-icon" />
            一键微调
          </span>
        </template>
        <div class="oneclick-container">
          <!-- 顶部标签：避免左侧窄列导致换行错乱、问号与文字重叠 -->
          <el-form :model="runConfig" label-position="top" class="one-click-form">
            <section class="oneclick-section">
              <h3 class="oneclick-section-title">基础配置</h3>
            <div class="oneclick-fields-grid oneclick-fields-grid--2">
              <el-form-item>
                <template #label>
                  <span class="label-with-help">基座模型<el-tooltip content="Ollama 本地模型名或 HuggingFace 模型 ID。训练时 Unsloth 会使用 unsloth/Qwen3-4B 作为基座，与 Ollama 的 qwen3:4b 架构一致。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input v-model="runConfig.base_model" placeholder="qwen3:4b" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">输出名称<el-tooltip content="训练完成后 LoRA 适配器的保存目录名，将保存在 微调/lora_output/ 下。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input v-model="runConfig.output_name" placeholder="qwen3-4b-miner-lora" />
              </el-form-item>
            </div>
            <el-form-item class="oneclick-form-item--full oneclick-form-item--radio">
              <template #label>
                <span class="label-with-help">微调方式<el-tooltip content="LoRA 使用 16bit 精度，效果更好但显存约 10GB；QLoRA 使用 4bit 量化，省显存但略慢。Qwen3 推荐 LoRA。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
              </template>
              <el-radio-group v-model="runConfig.method" class="oneclick-radio-group">
                <el-radio value="lora">LoRA（16bit，更准，显存约 10GB）</el-radio>
                <el-radio value="qlora">QLoRA（4bit，省显存，略慢）</el-radio>
              </el-radio-group>
            </el-form-item>
            </section>

            <section class="oneclick-section">
              <h3 class="oneclick-section-title">LoRA 参数</h3>
            <div class="oneclick-fields-grid oneclick-fields-grid--2">
              <el-form-item>
                <template #label>
                  <span class="label-with-help">LoRA Rank (r)<el-tooltip content="低秩矩阵的秩。越大表达能力越强但显存越高、训练越慢。推荐 8 或 16。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input-number v-model="runConfig.lora_r" :min="4" :max="128" :step="4" class="oneclick-input-number" controls-position="right" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">LoRA Alpha<el-tooltip content="LoRA 更新的缩放因子。建议设为 rank 的 2 倍，如 r=16 则 alpha=32。影响学习强度。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input-number v-model="runConfig.lora_alpha" :min="4" :max="256" :step="4" class="oneclick-input-number" controls-position="right" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">LoRA Dropout<el-tooltip content="训练时随机丢弃 LoRA 激活的比例，用于防止过拟合。0 可加速训练，0.05 可提升泛化。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input-number v-model="runConfig.lora_dropout" :min="0" :max="0.5" :step="0.01" class="oneclick-input-number" controls-position="right" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">rsLoRA<el-tooltip content="Rank-Stabilized LoRA，使用 alpha/sqrt(r) 缩放，可提升高 rank 时的稳定性。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <div class="oneclick-switch-row">
                  <el-switch v-model="runConfig.use_rslora" />
                  <span class="form-tip-inline oneclick-switch-hint">启用可提升稳定性</span>
                </div>
              </el-form-item>
            </div>
            <el-form-item class="oneclick-form-item--full oneclick-form-item--modules">
              <template #label>
                <span class="label-with-help">目标模块</span>
              </template>
              <div class="module-select-wrapper">
                <el-select
                  v-model="runConfig.lora_target_modules_arr"
                  class="oneclick-module-select"
                  popper-class="oneclick-module-grey-popper"
                  multiple
                  collapse-tags
                  :max-collapse-tags="6"
                  collapse-tags-tooltip
                  placeholder="选择模块（可多选）"
                >
                  <el-option
                    v-for="m in TARGET_MODULE_OPTIONS"
                    :key="m.value"
                    :label="`${m.value}（${m.shortTitle}）`"
                    :value="m.value"
                  />
                </el-select>
                <p class="module-hint-after">
                  注意力：<code>q_proj</code> / <code>k_proj</code> / <code>v_proj</code>；输出：<code>o_proj</code>；FFN：<code>gate_proj</code> / <code>up_proj</code> / <code>down_proj</code>。全选效果通常最好；减少模块可省显存。
                </p>
                <div class="module-expression-footer">
                  <el-input
                    v-model="targetModuleExpr"
                    placeholder="批量表达式：all · attention · ffn · 或 q_proj,k_proj,..."
                    clearable
                    @keyup.enter="applyTargetModuleExpr"
                  />
                  <el-button type="primary" class="oneclick-apply-modules" @click="applyTargetModuleExpr">应用到选择</el-button>
                </div>
              </div>
            </el-form-item>
            </section>

            <section class="oneclick-section">
              <h3 class="oneclick-section-title">训练参数</h3>
            <div class="oneclick-fields-grid oneclick-fields-grid--2">
              <el-form-item>
                <template #label>
                  <span class="label-with-help">学习率<el-tooltip content="梯度更新步长。LoRA 推荐 2e-4，DPO/RL 等推荐 5e-6。过大易发散，过小收敛慢。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input v-model="runConfig.learning_rate" placeholder="2e-4" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">训练轮数<el-tooltip content="完整遍历数据集的次数。1-3 轮通常足够，过多易过拟合、记忆训练集。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input-number v-model="runConfig.num_epochs" :min="1" :max="10" class="oneclick-input-number" controls-position="right" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">Batch Size<el-tooltip content="每步处理的样本数。越大显存越高，通常设为 1-4。配合梯度累积达到有效 batch size。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input-number v-model="runConfig.per_device_train_batch_size" :min="1" :max="16" class="oneclick-input-number" controls-position="right" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">梯度累积步数<el-tooltip content="累积多少步再更新权重。有效 batch = batch_size × 梯度累积。推荐 8-16 达到稳定训练。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input-number v-model="runConfig.gradient_accumulation_steps" :min="1" :max="64" class="oneclick-input-number" controls-position="right" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">最大序列长度<el-tooltip content="单条样本截断/填充的上限（token），本页最高 8192。越长越吃显存；长 JSON 输出建议 4096 起，仍截断可 8192 并减小每卡 batch。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input-number v-model="runConfig.max_seq_length" :min="256" :max="8192" :step="256" class="oneclick-input-number" controls-position="right" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">Warmup 比例<el-tooltip content="训练初期学习率从 0 线性升到目标值的步数占比。0.1 表示前 10% 步数 warmup。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input-number v-model="runConfig.warmup_ratio" :min="0" :max="0.5" :step="0.05" class="oneclick-input-number" controls-position="right" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">Weight Decay<el-tooltip content="L2 正则化系数，防止权重过大。0.01 为常用值。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-input-number v-model="runConfig.weight_decay" :min="0" :max="0.2" :step="0.01" class="oneclick-input-number" controls-position="right" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-help">训练精度<el-tooltip content="BF16：BFloat16，省约 50% 显存，推荐。FP16：半精度，兼容性好。4bit：仅 QLoRA 时可用，最省显存。FP32：全精度，显存最高、最慢。" placement="bottom"><QuestionFilled class="param-help" /></el-tooltip></span>
                </template>
                <el-select v-model="runConfig.precision" placeholder="选择训练精度" class="oneclick-select-block">
                  <el-option label="BF16（推荐，省显存）" value="bf16" />
                  <el-option label="FP16（兼容性好）" value="fp16" />
                  <el-option label="4bit（仅 QLoRA）" value="4bit" :disabled="runConfig.method !== 'qlora'" />
                  <el-option label="FP32（全精度）" value="fp32" />
                </el-select>
              </el-form-item>
            </div>
            </section>
          </el-form>

          <div class="oneclick-data-tip" v-if="selectedSampleIds.length > 0">
            <InfoFilled />
            已从样本列表选择 <strong>{{ selectedSampleIds.length }}</strong> 条用于本次训练
          </div>
          <div class="oneclick-data-tip muted" v-else>
            <InfoFilled />
            未选择样本时，将使用「导出标注数据」生成的全部数据。可在样本列表中勾选已标注样本以指定训练数据。
          </div>
          <div class="oneclick-actions">
            <el-button @click="saveRunConfig">保存配置</el-button>
            <el-button type="primary" @click="generateTraining" :loading="generating">
              {{ generating ? '准备训练…' : '生成并训练' }}
            </el-button>
            <el-checkbox v-model="onlyGenerateScript" class="only-script-checkbox">
              仅生成脚本（不启动训练）
            </el-checkbox>
          </div>

          <!-- 训练记录 -->
          <div class="train-runs-section">
            <div class="train-runs-header">
              <span>训练记录</span>
              <el-button :icon="Refresh" @click="loadTrainRuns" size="small">刷新</el-button>
            </div>
            <el-table :data="trainRuns" class="train-runs-table" max-height="280">
              <el-table-column label="ID" prop="id" width="60" align="center" />
              <el-table-column label="创建时间" prop="created_at" width="170" />
              <el-table-column label="状态" width="90" align="center">
                <template #default="{ row }">
                  <el-tag
                    :type="row.status === 'generated' ? 'info' : row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'"
                    size="small"
                  >
                    {{
                      row.status === 'generated'
                        ? '已生成'
                        : row.status === 'completed'
                          ? '已完成'
                          : row.status === 'running'
                            ? '训练中'
                            : row.status === 'failed'
                              ? '失败'
                              : row.status || '-'
                    }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="样本数" prop="sample_count" width="80" align="center" />
              <el-table-column label="输出目录" prop="output_dir" min-width="200" show-overflow-tooltip />
              <el-table-column label="脚本路径" prop="script_path" min-width="180" show-overflow-tooltip />
            </el-table>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 日志预览对话框 -->
    <el-dialog 
      v-model="previewDialogVisible" 
      :title="`日志预览：${previewLogFile?.filename || ''}`"
      width="90%"
      top="5vh"
    >
      <div v-if="previewLoading" class="preview-loading">
        <Loading class="is-loading" />
        <span>加载中...</span>
      </div>
      <div v-else-if="previewData.samples && previewData.samples.length > 0" class="preview-container">
        <div class="preview-stats">
          显示前 {{ previewData.showing }} 条，共 {{ previewData.total }} 条记录
        </div>
        <div v-for="(sample, idx) in previewData.samples" :key="idx" class="preview-sample">
          <div class="preview-sample-header">
            <span class="preview-sample-index">案例 #{{ idx + 1 }}</span>
            <span class="preview-sample-time">{{ sample.ts }}</span>
          </div>
          
          <div class="preview-sample-title" v-if="sample.title">
            📝 {{ sample.title }}
          </div>
          
          <a 
            v-if="sample.source_url" 
            :href="sample.source_url" 
            target="_blank" 
            class="preview-sample-link"
          >
            🔗 查看原帖
          </a>
          
          <div class="preview-section">
            <div class="preview-section-title">原始面经内容</div>
            <div class="preview-content">{{ sample.content }}</div>
          </div>
          
          <div class="preview-section" v-if="sample.llm_raw_obj">
            <div class="preview-section-title">
              Stage1 粗提取（远程）
              <span class="preview-question-count" v-if="Array.isArray(sample.llm_raw_obj)">
                （{{ sample.llm_raw_obj.length }} 道题）
              </span>
            </div>
            <vue-json-pretty 
              :data="sample.llm_raw_obj"
              :deep="99"
              :showLength="false"
              :showLine="false"
              :showDoubleQuotes="false"
              :highlightMouseoverNode="true"
              :collapsedOnClickBrackets="true"
            />
          </div>
          <div class="preview-section" v-if="sample.stage2_obj">
            <div class="preview-section-title">
              Stage2 豆包 API
              <span class="preview-question-count" v-if="Array.isArray(sample.stage2_obj)">
                （{{ sample.stage2_obj.length }} 道题）
              </span>
            </div>
            <vue-json-pretty 
              :data="sample.stage2_obj"
              :deep="99"
              :showLength="false"
              :showLine="false"
              :showDoubleQuotes="false"
              :highlightMouseoverNode="true"
              :collapsedOnClickBrackets="true"
            />
          </div>
        </div>
      </div>
      <el-empty v-else description="没有数据" />
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onActivated } from 'vue'
import { Refresh, Loading, UploadFilled, QuestionFilled, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import CodeMirror from 'vue-codemirror6'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'

const jsonLang = json()

const BASE = '/api/finetune'
const api = {
  get: (url) => fetch(url).then(r => r.json()),
  post: (url, body) => fetch(url, { 
    method: 'POST', 
    headers: { 'Content-Type': 'application/json' }, 
    body: JSON.stringify(body) 
  }).then(r => r.json()),
}

// FAQ 上传
const faqSaveToBank = ref(true)
const faqSaveToFinetune = ref(true)
const faqUploadRef = ref(null)
const faqSelectedFile = ref(null)
const faqUploading = ref(false)
const faqResult = ref(null)

const onFaqFileChange = (file) => {
  faqSelectedFile.value = file.raw
  faqResult.value = null
}

const submitFaqUpload = async () => {
  if (!faqSelectedFile.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  faqUploading.value = true
  faqResult.value = null
  try {
    const form = new FormData()
    form.append('file', faqSelectedFile.value)
    form.append('save_to_bank', faqSaveToBank.value)
    form.append('save_to_finetune', faqSaveToFinetune.value)
    const res = await fetch(`${BASE}/upload-faq`, {
      method: 'POST',
      body: form,
    })
    const data = await res.json()
    if (!res.ok) {
      ElMessage.error(data.detail || '上传失败')
      return
    }
    faqResult.value = data
    if (data.parsed > 0) {
      ElMessage.success(`导入完成：题库 ${data.bank_saved} 条，微调 ${data.finetune_saved} 条`)
      faqSelectedFile.value = null
      faqUploadRef.value?.clearFiles()
      await loadStats()
      await loadSamples(1)
    }
  } catch (e) {
    ElMessage.error('上传失败：' + e.message)
  } finally {
    faqUploading.value = false
  }
}

// 统计数据
const stats = ref({})
const loadStats = async () => { stats.value = await api.get(`${BASE}/stats`) }

// 自动导入
const autoImporting = ref(false)
const autoImportAll = async () => {
  autoImporting.value = true
  try {
    const res = await api.post(`${BASE}/import-all`, {})
    if (res.imported > 0) {
      ElMessage.success(`自动导入完成：新增 ${res.imported} 条，跳过 ${res.skipped} 条`)
    }
    await loadStats()
    await loadSamples(1)
  } catch (e) {
    ElMessage.error('导入失败：' + e.message)
  } finally {
    autoImporting.value = false
  }
}

// 修复 Stage2 合并（对 stage2 不完整的样本，用 stage1 补齐）
const fixMergedLoading = ref(false)
const fixMergedSamples = async () => {
  fixMergedLoading.value = true
  try {
    const res = await api.post(`${BASE}/fix-merged`, {})
    if (res.fixed > 0) {
      ElMessage.success(`已修复 ${res.fixed} 条，跳过 ${res.skipped} 条`)
      if (currentSample.value) {
        currentSample.value = await api.get(`${BASE}/samples/${currentSample.value.id}`)
      }
      await loadStats()
    } else {
      ElMessage.info(res.skipped > 0 ? '无需修复，所有样本已完整' : '没有可修复的样本')
    }
  } catch (e) {
    ElMessage.error('修复失败：' + e.message)
  } finally {
    fixMergedLoading.value = false
  }
}

// 日志文件
const logFiles = ref([])
const loadLogFiles = async () => { logFiles.value = await api.get(`${BASE}/log-files`) }

// 导入历史
const importLogs = ref([])
const loadImportLogs = async () => { 
  try {
    importLogs.value = await api.get(`${BASE}/import-logs`)
  } catch (e) {
    console.warn('加载导入历史失败', e)
    importLogs.value = []
  }
}

const viewImportLogDetail = async (row) => {
  try {
    const detail = await api.get(`${BASE}/import-log/${row.import_log_id}`)
    const duplicateCount = detail.duplicate_count ?? detail.duplicated ?? detail.skipped ?? 0
    const reasonSummary = detail.error_summary || {}
    const reasonText = Object.keys(reasonSummary).length
      ? `失败原因统计: ${Object.entries(reasonSummary).map(([k, v]) => `${k}(${v})`).join('；')}`
      : ''
    ElMessage.info(`
导入ID: ${detail.import_log_id}
文件: ${detail.filename}
成功: ${detail.imported} | 重复(跳过): ${duplicateCount} | 失败: ${detail.failed}
时间: ${detail.created_at}
${reasonText}
${detail.failed_samples?.length ? '失败样本: ' + detail.failed_samples.map(s => `行${s.line}: ${s.reason || '异常'} - ${s.error}`).join('; ') : ''}
    `.trim())
  } catch (e) {
    ElMessage.error('获取详情失败: ' + e.message)
  }
}

const deleteImportLog = async (row) => {
  if (!confirm(`确定删除导入记录「${row.import_log_id}」及其 ${row.imported + row.skipped + row.failed} 条样本？此操作不可恢复。`)) return
  try {
    const res = await fetch(`${BASE}/import-log/${row.import_log_id}`, { method: 'DELETE' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || data.message || '删除失败')
    ElMessage.success(`已删除 ${data.deleted_samples} 条样本`)
    await loadImportLogs()
    await loadStats()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.message || e))
  }
}

const importLog = async (row) => {
  const res = await api.post(`${BASE}/import`, { log_path: row.path })
  const duplicateCount = res.duplicated ?? res.skipped ?? 0
  const reasonSummary = res.details?.error_summary || {}
  const reasonText = Object.keys(reasonSummary).length
    ? Object.entries(reasonSummary).map(([k, v]) => `${k}(${v})`).join('；')
    : ''
  ElMessage.success(`导入完成：新增 ${res.imported} 条，重复(跳过) ${duplicateCount} 条${res.failed ? '，失败 ' + res.failed + ' 条' : ''}`)
  if (res.failed > 0) {
    const failedLinesText = res.details?.failed_samples?.length
      ? res.details.failed_samples.map(s => `行${s.line}: ${s.reason || '异常'} - ${s.error}`).join('\n')
      : '无失败样本详情'
    await ElMessageBox.alert(
      `文件：${res.details?.file || row.filename || ''}\n` +
      `新增：${res.imported} 条\n` +
      `重复(跳过)：${duplicateCount} 条\n` +
      `失败：${res.failed} 条\n` +
      `${reasonText ? `失败原因统计：${reasonText}\n` : ''}` +
      `失败样本（最多10条）：\n${failedLinesText}`,
      '导入结果（含失败原因）',
      { confirmButtonText: '我知道了' }
    )
  }
  await loadStats()
  await loadSamples(1)
  await loadImportLogs()  // 刷新导入历史
  activeTab.value = 'list'
}

const deleteLogFile = async (row) => {
  if (!confirm(`确定删除日志文件「${row.filename}」？此操作不可恢复。`)) return
  try {
    const res = await fetch(`${BASE}/delete-log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ log_path: row.path }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || data.message || '删除失败')
    ElMessage.success(data.message || '已删除')
    activeTab.value = 'logs'
    await loadLogFiles()
    await loadStats()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.message || e))
  }
}

const deleteSample = async (row) => {
  if (!confirm(`确定删除样本 #${row.id}？`)) return
  try {
    const res = await fetch(`${BASE}/samples/${row.id}`, { method: 'DELETE' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '删除失败')
    ElMessage.success('已删除')
    if (currentSample.value?.id === row.id) currentSample.value = null
    selectedSampleIds.value = selectedSampleIds.value.filter(id => id !== row.id)
    await loadStats()
    await loadSamples(currentPage.value)
    activeTab.value = 'list'
  } catch (e) {
    ElMessage.error('删除失败：' + (e.message || e))
  }
}

// 日志预览
const previewDialogVisible = ref(false)
const previewLoading = ref(false)
const previewLogFile = ref(null)
const previewData = ref({ samples: [], total: 0, showing: 0 })

const previewLog = async (row) => {
  previewLogFile.value = row
  previewDialogVisible.value = true
  previewLoading.value = true
  previewData.value = { samples: [], total: 0, showing: 0 }
  
  try {
    const res = await api.post(`${BASE}/preview-log`, { 
      log_path: row.path,
      limit: row.line_count  // 使用文件的实际条数
    })
    if (res.error) {
      ElMessage.error('预览失败：' + res.error)
      previewDialogVisible.value = false
    } else {
      previewData.value = res
    }
  } catch (e) {
    ElMessage.error('预览失败：' + e.message)
    previewDialogVisible.value = false
  } finally {
    previewLoading.value = false
  }
}

// 样本列表
const samples = ref([])
const filterStatus = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const pagerTotal = ref(0)
const activeTab = ref('list')
const sampleTableRef = ref(null)
const selectedSampleIds = ref([])
const editorHeaderRef = ref(null)
const postInfoRef = ref(null)

const isScrollable = (el) => {
  if (!el) return false
  const style = window.getComputedStyle(el)
  const overflowY = style.overflowY
  return (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') && el.scrollHeight > el.clientHeight
}

const getScrollableAncestors = (el) => {
  const ancestors = []
  let node = el?.parentElement
  while (node) {
    if (isScrollable(node)) ancestors.push(node)
    node = node.parentElement
  }
  return ancestors
}

// 预留页面顶部空间，确保“标题 + 上/下一题”都能完整露出
const EDITOR_TOP_OFFSET = 72

const getAbsoluteTop = (el) => {
  let top = 0
  let node = el
  while (node) {
    top += node.offsetTop || 0
    node = node.offsetParent
  }
  return top
}

const scrollToEditorAnchor = () => {
  const anchorEl = postInfoRef.value || editorHeaderRef.value
  if (!anchorEl) return
  // 本应用主滚动条在 App.vue 的 main.content 上，不是 window
  const mainEl = document.querySelector('main.content')
  if (mainEl && typeof mainEl.scrollTo === 'function') {
    const top =
      anchorEl.getBoundingClientRect().top -
      mainEl.getBoundingClientRect().top +
      mainEl.scrollTop -
      EDITOR_TOP_OFFSET
    mainEl.scrollTo({ top: Math.max(0, top), behavior: 'auto' })
    return
  }
  const scrollParents = getScrollableAncestors(anchorEl)
  scrollParents.forEach((parent) => {
    const targetTop =
      anchorEl.getBoundingClientRect().top -
      parent.getBoundingClientRect().top +
      parent.scrollTop -
      EDITOR_TOP_OFFSET
    parent.scrollTo({
      top: Math.max(0, targetTop),
      behavior: 'auto',
    })
  })
  const top = getAbsoluteTop(anchorEl) - EDITOR_TOP_OFFSET
  window.scrollTo({
    top: Math.max(0, top),
    behavior: 'auto',
  })
}

// 切换样本 / 复制后 CodeMirror 等会在下一帧抢焦点并 scrollIntoView，需延后补偿滚动
const scheduleScrollToEditorAnchor = () => {
  nextTick(() => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        scrollToEditorAnchor()
        setTimeout(() => scrollToEditorAnchor(), 80)
      })
    })
  })
}

// 从 Stage1 复制后粘贴到③时，编辑器常会 scrollIntoView 把主区域拉到底部
const onEditAreaPaste = () => {
  nextTick(() => scheduleScrollToEditorAnchor())
}

const onSampleSelectionChange = (selection) => {
  const idsOnPage = samples.value.map(r => r.id)
  const selectedOnPage = selection.map(r => r.id)
  selectedSampleIds.value = [
    ...selectedSampleIds.value.filter(id => !idsOnPage.includes(id)),
    ...selectedOnPage,
  ]
}

const selectAllLabeledOnPage = () => {
  if (!sampleTableRef.value) return
  const labeled = samples.value.filter(r => r.status === 'labeled')
  labeled.forEach(row => sampleTableRef.value.toggleRowSelection(row, true))
}

const clearSampleSelection = () => {
  selectedSampleIds.value = []
  sampleTableRef.value?.clearSelection()
}

const loadSamples = async (page = currentPage.value) => {
  currentPage.value = page
  const params = new URLSearchParams({ 
    page, 
    page_size: pageSize.value,
    order: 'asc'  // 按ID从小到大排序
  })
  if (filterStatus.value) params.set('status', filterStatus.value)
  const res = await api.get(`${BASE}/samples?${params}`)
  samples.value = (res.items || []).map(item => ({
    ...item,
    // 确保 content_preview 是完整的 content（不截断）
    content_preview: item.content || ''
  }))
  pagerTotal.value = res.total || 0
  nextTick(() => {
    const toSelect = samples.value.filter(r => selectedSampleIds.value.includes(r.id))
    toSelect.forEach(row => sampleTableRef.value?.toggleRowSelection(row, true))
  })
}

const getBodyPreview = (text) => {
  const raw = (text || '').trim()
  if (!raw) return ''

  // 统一换行，便于跨行正则
  const normalized = raw.replace(/\r\n?/g, '\n')

  // 1) 优先从“正文标记”后截取：支持 [正文] / 【正文】 / 正文:
  const bodyMarker = normalized.match(/(?:\[\s*正文\s*\]|【\s*正文\s*】|^\s*正文\s*[：:])\s*([\s\S]*)$/m)
  if (bodyMarker?.[1]) return bodyMarker[1].trim()

  // 2) 没有正文标记时，先删除“标题段”：支持 [标题] / 【标题】 / 标题:
  let stripped = normalized
    .replace(/(?:\[\s*标题\s*\]|【\s*标题\s*】|^\s*标题\s*[：:])\s*[^\n]*\n?/gm, '')
    .trim()

  // 3) 删除残留的单独标记行（有些数据会把标签单独占一行）
  stripped = stripped
    .replace(/^\s*(?:\[\s*标题\s*\]|【\s*标题\s*】|\[\s*正文\s*\]|【\s*正文\s*】)\s*$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()

  return stripped
}

const onSampleClick = async (row, column, event) => {
  if (event?.target?.closest?.('.el-checkbox')) return
  const detail = await api.get(`${BASE}/samples/${row.id}`)
  currentSample.value = detail
  // 预填：final_output > assist_output > stage2_output（豆包结果）
  const prefill = detail.final_output || detail.assist_output || detail.stage2_output || ''
  editOutput.value = prefill ? formatJson(prefill) : ''
  activeTab.value = 'editor'
  scheduleScrollToEditorAnchor()
}

// 导航功能
const currentSampleIndex = computed(() => {
  if (!currentSample.value || !samples.value.length) return -1
  return samples.value.findIndex(s => s.id === currentSample.value.id)
})

const hasPrevSample = computed(() => currentSampleIndex.value > 0)
const hasNextSample = computed(() => currentSampleIndex.value >= 0 && currentSampleIndex.value < samples.value.length - 1)

const gotoNextSample = async () => {
  if (hasNextSample.value) {
    clearFindReplace()
    await onSampleClick(samples.value[currentSampleIndex.value + 1])
  }
}

const gotoPrevSample = async () => {
  if (hasPrevSample.value) {
    clearFindReplace()
    await onSampleClick(samples.value[currentSampleIndex.value - 1])
  }
}

const clearFindReplace = () => {
  findText.value = ''
  replaceText.value = ''
}

// 标注编辑器
const currentSample = ref(null)
const editOutput = ref('')
const assisting = ref(false)
const labeling = ref(false)
const exporting = ref(false)
const findText = ref('')
const replaceText = ref('')

// 自动格式化防抖计时器
let autoFormatTimer = null

// 智能自动格式化：检测到完整 JSON 时自动格式化
const autoFormatJson = () => {
  if (autoFormatTimer) clearTimeout(autoFormatTimer)
  
  autoFormatTimer = setTimeout(() => {
    const text = editOutput.value.trim()
    if (!text) return
    
    // 只在看起来像完整 JSON 时才尝试格式化
    // 检查：以 { 或 [ 开头，以 } 或 ] 结尾
    if ((text.startsWith('{') && text.endsWith('}')) || 
        (text.startsWith('[') && text.endsWith(']'))) {
      try {
        const parsed = JSON.parse(text)
        const formatted = JSON.stringify(parsed, null, 2)
        // 只在格式确实改变时才更新（避免不必要的重排）
        if (formatted !== text) {
          editOutput.value = formatted
        }
      } catch (e) {
        // JSON 无效，不格式化，保持原样
      }
    }
  }, 800) // 800ms 防抖延迟，用户停止输入后才格式化
}

// 监听 editOutput 变化，触发自动格式化
watch(editOutput, () => {
  autoFormatJson()
})

const doReplace = () => {
  if (!findText.value) { ElMessage.warning('请输入查找内容'); return }
  const idx = editOutput.value.indexOf(findText.value)
  if (idx === -1) { ElMessage.info('未找到匹配内容'); return }
  editOutput.value = editOutput.value.replace(findText.value, replaceText.value)
  ElMessage.success('已替换 1 处')
  scheduleScrollToEditorAnchor()
}

const doReplaceAll = () => {
  if (!findText.value) { ElMessage.warning('请输入查找内容'); return }
  const parts = editOutput.value.split(findText.value)
  const count = parts.length - 1
  if (count === 0) { ElMessage.info('未找到匹配内容'); return }
  editOutput.value = parts.join(replaceText.value)
  ElMessage.success(`已全部替换 ${count} 处`)
  scheduleScrollToEditorAnchor()
}

const isModified = computed(() => {
  if (!editOutput.value.trim()) return false
  // 以 final_output（上次保存的修改内容）为基准，若没有则以 stage2_output 为基准
  const baseline = currentSample.value?.final_output || currentSample.value?.assist_output || currentSample.value?.stage2_output || ''
  if (!baseline) return true
  // 比较时忽略格式差异（都格式化成 JSON 再比较）
  const normalizeJson = (s) => { try { return JSON.stringify(JSON.parse(s)) } catch { return s.trim() } }
  return normalizeJson(editOutput.value) !== normalizeJson(baseline)
})

const parseJson = (str) => {
  if (!str) return {}
  try { return JSON.parse(str) } catch { return { error: '无效JSON', raw: str } }
}

// 将后端输出的 JSON 字符串格式化为可读的缩进文本。
// 若不是合法 JSON，则保持原样，避免点击/跳转时直接报错。
const formatJson = (str) => {
  if (str === null || str === undefined) return ''
  if (typeof str !== 'string') {
    try { return JSON.stringify(str, null, 2) } catch { return String(str) }
  }
  const s = str.trim()
  if (!s) return ''
  try {
    return JSON.stringify(JSON.parse(s), null, 2)
  } catch {
    return str
  }
}

// Stage1 题目数量
const stage1QuestionCount = computed(() => {
  const raw = currentSample.value?.stage1_output
  if (!raw) return 0
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.length : 0
  } catch { return 0 }
})

// 编辑区题目数量（当前编辑的JSON中的题目数）
const editQuestionCount = computed(() => {
  if (!editOutput.value) return 0
  try {
    const parsed = JSON.parse(editOutput.value)
    return Array.isArray(parsed) ? parsed.length : 0
  } catch { return 0 }
})
// 解析编辑输出：如果是list，去掉首尾括号展示为对象数组
const parsedEditOutput = computed(() => {
  if (!editOutput.value) return []
  try {
    const parsed = JSON.parse(editOutput.value)
    // 如果是数组，直接返回（vue-json-pretty会自动展示）
    if (Array.isArray(parsed)) {
      return parsed
    }
    return parsed
  } catch {
    return { error: '无效JSON', raw: editOutput.value }
  }
})

// 当JSON编辑器内容改变时
const onEditOutputChange = (newData) => {
  editOutput.value = JSON.stringify(newData, null, 2)
}



const callAssist = async () => {
  if (!currentSample.value) return
  assisting.value = true
  try {
    const body = { sample_id: currentSample.value.id, content: currentSample.value.content }
    const res = await api.post(`${BASE}/assist`, body)
    if (res.error) { ElMessage.error('大模型调用失败：' + res.error); return }
    editOutput.value = formatJson(res.output)
    ElMessage.success(`大模型（${res.model}）生成完成`)
  } finally {
    assisting.value = false
    scheduleScrollToEditorAnchor()
  }
}

const confirmLabel = async () => {
  if (!editOutput.value.trim()) {
    ElMessage.warning('标注内容不能为空')
    scheduleScrollToEditorAnchor()
    return
  }
  labeling.value = true
  try {
    const res = await api.post(`${BASE}/label`, {
      sample_id: currentSample.value.id,
      final_output: editOutput.value.trim(),
      is_modified: isModified.value,
    })
    if (res.status === 'ok') {
      ElMessage.success('标注已保存 ✅')
      currentSample.value.status = 'labeled'
      currentSample.value.labeled_at = res.labeled_at
      loadStats()
      // 自动跳转到下一题
      if (hasNextSample.value) {
        setTimeout(() => gotoNextSample(), 500)
      }
    }
  } finally {
    labeling.value = false
    scheduleScrollToEditorAnchor()
  }
}

const copyStage1 = () => {
  const text = currentSample.value?.stage1_output || ''
  if (!text) { ElMessage.warning('Stage1 无内容'); return }
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制')
    scheduleScrollToEditorAnchor()
  }).catch(() => ElMessage.error('复制失败'))
}
const confirmNoChange = async () => {
  // 使用 Stage2 豆包 或 Stage1 作为最终标注
  const llmOutput = currentSample.value?.stage2_output || currentSample.value?.stage1_output
  if (!llmOutput) {
    ElMessage.warning('Stage1/Stage2 输出为空')
    scheduleScrollToEditorAnchor()
    return
  }

  labeling.value = true
  try {
    const res = await api.post(`${BASE}/label`, {
      sample_id: currentSample.value.id,
      final_output: llmOutput,
      is_modified: false,
    })
    if (res.status === 'ok') {
      ElMessage.success('已标注为无需修改 ✅')
      currentSample.value.status = 'labeled'
      currentSample.value.labeled_at = res.labeled_at
      loadStats()
      // 自动跳转到下一题
      if (hasNextSample.value) {
        setTimeout(() => gotoNextSample(), 500)
      }
    }
  } finally {
    labeling.value = false
    scheduleScrollToEditorAnchor()
  }
}

const exportLabeled = async () => {
  exporting.value = true
  try {
    const body = selectedSampleIds.value.length > 0 ? { sample_ids: selectedSampleIds.value } : {}
    const res = await api.post(`${BASE}/export`, body)
    ElMessage.success(`已导出 ${res.exported} 条 → ${res.path}`)
  } finally {
    exporting.value = false
  }
}

/** 目标模块：value 供训练脚本/API；展示为 id（功能简述） */
const TARGET_MODULE_OPTIONS = [
  { value: 'q_proj', shortTitle: 'Query 投影，注意力查询' },
  { value: 'k_proj', shortTitle: 'Key 投影，注意力键' },
  { value: 'v_proj', shortTitle: 'Value 投影，注意力值' },
  { value: 'o_proj', shortTitle: '注意力输出线性层' },
  { value: 'gate_proj', shortTitle: 'FFN 门控分支' },
  { value: 'up_proj', shortTitle: 'FFN 上投影、升维' },
  { value: 'down_proj', shortTitle: 'FFN 下投影、回残差' },
]

const ALL_MODULES = TARGET_MODULE_OPTIONS.map(m => m.value)
const ATTENTION_MODULES = ['q_proj', 'k_proj', 'v_proj', 'o_proj']
const FFN_MODULES = ['gate_proj', 'up_proj', 'down_proj']

const targetModuleExpr = ref('')

const applyTargetModuleExpr = () => {
  const expr = (targetModuleExpr.value || '').trim().toLowerCase()
  if (!expr) return
  let result = []
  if (expr === 'all' || expr === '*') {
    result = [...ALL_MODULES]
  } else if (expr === 'attention' || expr === 'qkv' || expr === 'attn') {
    result = [...ATTENTION_MODULES]
  } else if (expr === 'ffn') {
    result = [...FFN_MODULES]
  } else {
    const validSet = new Set(ALL_MODULES)
    result = expr.split(/[,，\s+]+/).map(s => s.trim()).filter(s => validSet.has(s))
  }
  if (result.length > 0) {
    runConfig.value.lora_target_modules_arr = result
    ElMessage.success(`已应用 ${result.length} 个模块`)
  } else {
    ElMessage.warning('表达式无效，支持: all | attention | ffn | q_proj,k_proj,...')
  }
}

const onTabChange = (tab) => {
  if (tab === 'list') loadSamples(1)
  else if (tab === 'logs') loadLogFiles()
  else if (tab === 'oneclick') {
    loadRunConfig()
    loadTrainRuns()
  }
}

// 一键微调
const generating = ref(false)
/** 勾选后只写 train_lora.py，不由后端拉起训练进程 */
const onlyGenerateScript = ref(false)
const runConfig = ref({
  base_model: 'qwen3:4b',
  method: 'lora',
  output_name: 'qwen3-4b-miner-lora',
  lora_r: 16,
  lora_alpha: 32,
  lora_dropout: 0.05,
  lora_target_modules: 'q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj',
  lora_target_modules_arr: ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'],
  learning_rate: '2e-4',
  num_epochs: 3,
  per_device_train_batch_size: 2,
  gradient_accumulation_steps: 8,
  max_seq_length: 4096,
  warmup_ratio: 0.1,
  weight_decay: 0.01,
  use_rslora: true,
  precision: 'bf16',
})

const trainRuns = ref([])
const loadTrainRuns = async () => {
  try {
    const list = await api.get(`${BASE}/runs`)
    trainRuns.value = list || []
  } catch (e) {
    console.warn('加载训练记录失败', e)
    trainRuns.value = []
  }
}

// 微调方式改为 LoRA 时，若精度为 4bit 则重置为 bf16（需在 runConfig 声明之后）
watch(() => runConfig.value.method, (method) => {
  if (method === 'lora' && runConfig.value.precision === '4bit') {
    runConfig.value.precision = 'bf16'
  }
})

const loadRunConfig = async () => {
  try {
    const cfg = await api.get(`${BASE}/run-config`)
    const arr = (cfg.lora_target_modules || '').split(',').map(s => s.trim()).filter(Boolean)
    const precision = cfg.precision ?? (cfg.bf16 === false ? 'fp16' : 'bf16')
    const defaultModules = TARGET_MODULE_OPTIONS.map(m => m.value)
    runConfig.value = {
      ...runConfig.value,
      ...cfg,
      lora_target_modules_arr: arr.length ? arr : defaultModules,
      precision,
    }
  } catch (e) {
    console.warn('加载配置失败', e)
  }
}

const getConfigForApi = () => {
  const arr = runConfig.value.lora_target_modules_arr || []
  return {
    ...runConfig.value,
    lora_target_modules: Array.isArray(arr) ? arr.join(',') : runConfig.value.lora_target_modules,
  }
}

const saveRunConfig = async () => {
  try {
    await api.post(`${BASE}/run-config`, getConfigForApi())
    ElMessage.success('配置已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + (e.message || e))
  }
}

const generateTraining = async () => {
  generating.value = true
  try {
    const body = {
      config: getConfigForApi(),
      run_training: !onlyGenerateScript.value,
    }
    if (selectedSampleIds.value.length > 0) body.sample_ids = selectedSampleIds.value
    const res = await api.post(`${BASE}/generate-training`, body)
    if (res.status === 'error') {
      ElMessage.warning(res.message)
      return
    }
    await loadTrainRuns()
    if (res.training_error && !res.training_started) {
      ElMessage.warning(res.message || '脚本已生成，但未启动训练')
    } else {
      ElMessage.success(res.message || '操作完成')
    }
  } catch (e) {
    ElMessage.error('生成失败：' + (e.message || e))
  } finally {
    generating.value = false
  }
}

onMounted(async () => {
  await loadStats()
  await loadLogFiles()
  await loadSamples()
  if (activeTab.value === 'oneclick') await loadRunConfig()
})

// 页面激活时重新加载数据
onActivated(async () => {
  await loadSamples()
  await loadStats()
})

</script>

<style scoped>
.finetune-container {
  min-height: 100vh;
  background: #f5f7fa;
  padding: 32px;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.stat-card {
  background: white;
  border-radius: 16px;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
}

.stat-icon {
  font-size: 40px;
  line-height: 1;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 36px;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 8px;
}

.stat-card.primary .stat-value { color: #3b82f6; }
.stat-card.warning .stat-value { color: #f59e0b; }
.stat-card.success .stat-value { color: #10b981; }
.stat-card.info .stat-value { color: #8b5cf6; }

.stat-label {
  font-size: 15px;
  color: #6b7280;
  font-weight: 500;
}

/* 操作按钮 */
.action-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.action-bar .el-button {
  font-size: 16px;
  padding: 12px 24px;
  border-radius: 12px;
  font-weight: 600;
}

/* 主内容区 */
.content-tabs {
  background: white;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  min-height: 600px;
}

.content-tabs :deep(.el-tabs__header) {
  margin-bottom: 24px;
}

.content-tabs :deep(.el-tabs__item) {
  font-size: 18px;
  font-weight: 600;
  padding: 0 24px;
  height: 50px;
  line-height: 50px;
}

/* 样本列表 */
.list-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.list-toolbar {
  display: flex;
  gap: 16px;
  align-items: center;
}

.list-toolbar .el-radio-group {
  font-size: 16px;
}

.sample-table {
  font-size: 15px;
  cursor: pointer;
}

.sample-table :deep(.el-table__header th) {
  background: #f9fafb;
  font-size: 16px;
  font-weight: 600;
}

.sample-table :deep(.el-table__row:hover) {
  background: #f0f9ff;
}

.content-cell {
  font-size: 14px;
  line-height: 1.55;
  color: #374151;
  white-space: pre-line;
  word-break: break-word;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.title-cell {
  font-size: 14px;
  color: #374151;
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sample-table :deep(.time-col .cell) {
  font-size: 12px;
  color: #6b7280;
}

.text-muted {
  color: #9ca3af;
}

.pagination {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

/* 编辑器 */
.editor-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  gap: 24px;
  padding: 40px;
}

.editor-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #f9fafb;
  border-radius: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sample-id {
  font-size: 20px;
  font-weight: 700;
  color: #111827;
}

.header-right {
  display: flex;
  gap: 16px;
}

.time-info {
  font-size: 12px;
  color: #6b7280;
}

.editor-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1.2fr;
  gap: 24px;
  min-height: 720px;
  align-items: stretch;
}

.editor-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  border: 1px solid #e5e7eb;
}

.editor-panel:last-child {
  background: linear-gradient(to bottom, #fafbfc 0%, #fff 60px);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding-bottom: 14px;
  border-bottom: 1px solid #e5e7eb;
}

.post-info {
  padding: 12px 14px;
  background: linear-gradient(180deg, #fffef5 0%, #fffdf0 100%);
  border-radius: 10px;
  margin-bottom: 16px;
  border: 1px solid #fde68a;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
}

.post-info-title {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.post-info-url {
  flex-shrink: 0;
}

.post-info-label {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: #92400e;
  background: #fef3c7;
  border: 1px solid #fcd34d;
  flex-shrink: 0;
}

.post-info-text {
  font-size: 14px;
  color: #1f2937;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.post-info-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 30px;
  font-size: 13px;
  color: #1d4ed8;
  text-decoration: none;
  padding: 0 12px;
  border-radius: 999px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  transition: all 0.2s;
  font-weight: 600;
  white-space: nowrap;
}

.post-info-link:hover {
  background: #dbeafe;
  color: #1e40af;
  border-color: #93c5fd;
  transform: translateY(-1px);
}

@media (max-width: 900px) {
  .post-info {
    flex-direction: column;
    align-items: stretch;
  }

  .post-info-url {
    align-self: flex-start;
  }
}

.post-meta {
  padding: 12px 20px;
  background: #f0f9ff;
  border-radius: 8px;
  margin-bottom: 12px;
  border-left: 4px solid #3b82f6;
}

.post-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
  line-height: 1.5;
}

.post-link {
  display: inline-block;
  font-size: 14px;
  color: #3b82f6;
  text-decoration: none;
  padding: 4px 12px;
  border-radius: 6px;
  background: white;
  transition: all 0.2s;
}

.post-link:hover {
  background: #dbeafe;
  color: #2563eb;
}

.post-link-inline {
  display: inline-flex;
  align-items: center;
  font-size: 13px;
  color: #3b82f6;
  text-decoration: none;
  padding: 3px 10px;
  border-radius: 6px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  transition: all 0.2s;
  white-space: nowrap;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-left: auto;
}

.post-link-inline:hover {
  background: #dbeafe;
  color: #2563eb;
  border-color: #93c5fd;
}

/* 原始面经URL链接 */
.source-url-link {
  display: block;
  font-size: 13px;
  color: #3b82f6;
  text-decoration: none;
  padding: 8px 12px;
  border-radius: 6px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  margin-top: 8px;
  word-break: break-all;
  transition: all 0.2s;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-weight: 500;
  line-height: 1.5;
}

.source-url-link:hover {
  background: #dbeafe;
  color: #2563eb;
  border-color: #93c5fd;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.2);
}

/* 自适应高度的内容区 */
.content-auto-height {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.content-auto-height .el-textarea {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.content-auto-height :deep(.el-textarea__inner) {
  flex: 1;
  resize: vertical;
  min-height: 300px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  letter-spacing: 0.02em;
}

.panel-subtitle {
  font-size: 13px;
  color: #6b7280;
  margin-left: 6px;
  font-weight: 500;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  background: #fafafa;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #f0f0f0;
  min-height: 0;
}

.content-textarea :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 14px;
  line-height: 1.75;
  color: #374151;
}

.find-replace-bar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  background: #f8fafc;
  border-radius: 8px;
  margin-bottom: 12px;
  border: 1px solid #e2e8f0;
}

.find-replace-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.find-replace-label {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  white-space: nowrap;
  min-width: 50px;
}

.find-replace-row .el-input {
  flex: 1;
  min-width: 200px;
}

.find-replace-row .el-button {
  white-space: nowrap;
}

.find-replace-bar .find-tip {
  font-size: 12px;
  color: #94a3b8;
  margin-left: auto;
  white-space: nowrap;
}

.auto-format-tip {
  font-size: 12px;
  color: #10b981;
  margin-left: auto;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: #f0fdf4;
  border-radius: 6px;
  border: 1px solid #bbf7d0;
  white-space: nowrap;
}

.json-editor-wrap {
  flex: 1;
  min-height: 420px;
  display: flex;
  flex-direction: column;
}

.json-codemirror {
  flex: 1;
  font-size: 14px;
  border: 1px solid #334155;
  border-radius: 8px;
  overflow: hidden;
}

.json-codemirror :deep(.cm-editor) {
  min-height: 400px;
}

.json-codemirror :deep(.cm-scroller) {
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 14px;
  line-height: 1.7;
  overflow-x: hidden !important;
}

.json-codemirror :deep(.cm-content) {
  overflow-wrap: break-word;
  padding: 12px 0;
}

.json-codemirror :deep(.cm-line) {
  padding-left: 4px;
}

/* vue-json-pretty 语法高亮 */
.json-viewer :deep(.vjs-key) {
  color: #059669 !important;
  font-weight: 600;
}

.json-viewer :deep(.vjs-value__string) {
  color: #0369a1 !important;
}

.json-viewer :deep(.vjs-value__number) {
  color: #b91c1c !important;
}

.json-viewer :deep(.vjs-value__boolean) {
  color: #7c3aed !important;
}

.json-viewer :deep(.vjs-tree__brackets) {
  color: #64748b !important;
}

.json-viewer {
  font-size: 15px;
  overflow-x: hidden;
}

.json-viewer :deep(.vjs-tree) {
  font-size: 15px;
  overflow-wrap: break-word;
  word-break: break-all;
}

.editor-actions {
  display: flex;
  gap: 12px;
  padding-top: 12px;
}

.editor-actions-top {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 14px 16px;
  background: #f0fdf4;
  border-radius: 8px;
  margin-bottom: 12px;
  border: 1px solid #bbf7d0;
}

.navigation-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
  margin-top: 12px;
}

.navigation-actions-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #f0f9ff;
  border-radius: 12px;
  margin-bottom: 20px;
  border: 2px solid #3b82f6;
}

.sample-progress {
  font-size: 16px;
  font-weight: 600;
  color: #6b7280;
}

/* 日志文件 */
.logs-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-title {
  font-size: 20px;
  font-weight: 700;
  color: #111827;
}

.logs-table {
  font-size: 15px;
  cursor: pointer;
}

.logs-table :deep(.el-table__header th) {
  background: #f9fafb;
  font-size: 16px;
  font-weight: 600;
}

.logs-table :deep(.el-table__row:hover) {
  background: #f0f9ff;
}

.tip-text {
  font-size: 15px;
  color: #6b7280;
  padding: 12px 16px;
  background: #fef3c7;
  border-radius: 8px;
  border-left: 4px solid #f59e0b;
}

/* FAQ 上传 */
.faq-upload-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 560px;
}

.faq-upload-desc {
  font-size: 14px;
  color: #6b7280;
  line-height: 1.6;
}

.faq-checkbox {
  margin-right: 16px;
}

.faq-submit-btn {
  align-self: flex-start;
}

.faq-result {
  margin-top: 16px;
}

.faq-errors {
  margin-top: 8px;
  font-size: 13px;
  color: #b45309;
}

/* 日志预览对话框 */
.preview-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px;
  gap: 16px;
  font-size: 16px;
  color: #6b7280;
}

.preview-loading .el-icon {
  font-size: 40px;
  color: #3b82f6;
}

.preview-container {
  max-height: 70vh;
  overflow-y: auto;
  padding: 8px;
}

.preview-stats {
  font-size: 15px;
  color: #6b7280;
  padding: 12px 16px;
  background: #f0f9ff;
  border-radius: 8px;
  margin-bottom: 20px;
  text-align: center;
  font-weight: 600;
}

.preview-sample {
  background: #f9fafb;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  border: 2px solid #e5e7eb;
}

.preview-sample-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #e5e7eb;
}

.preview-sample-index {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
}

.preview-sample-time {
  font-size: 14px;
  color: #6b7280;
}

.preview-sample-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
  padding: 12px;
  background: #fffbeb;
  border-radius: 6px;
  border-left: 4px solid #f59e0b;
}

.preview-sample-link {
  display: inline-block;
  font-size: 14px;
  color: #3b82f6;
  text-decoration: none;
  padding: 6px 12px;
  border-radius: 6px;
  background: white;
  border: 1px solid #3b82f6;
  margin-bottom: 16px;
  transition: all 0.2s;
}

.preview-sample-link:hover {
  background: #dbeafe;
  color: #2563eb;
}

.preview-section {
  margin-top: 16px;
}

.preview-section-title {
  font-size: 15px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.preview-question-count {
  font-size: 13px;
  color: #6b7280;
  font-weight: 500;
}

.preview-content {
  background: white;
  border-radius: 8px;
  padding: 16px;
  font-size: 15px;
  line-height: 1.8;
  color: #1f2937;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
}

.preview-section .vjs-tree {
  background: white;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #e5e7eb;
  max-height: 500px;
  overflow-y: auto;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 14px;
  line-height: 1.8;
}

/* 自定义 vue-json-pretty 样式 */
.preview-section :deep(.vjs-tree) {
  background: white !important;
}

.preview-section :deep(.vjs-tree .vjs-key) {
  color: #059669;
  font-weight: 600;
}

.preview-section :deep(.vjs-tree .vjs-value__string) {
  color: #1f2937;
  font-weight: 400;
}

.preview-section :deep(.vjs-tree .vjs-value__number) {
  color: #dc2626;
  font-weight: 600;
}

.preview-section :deep(.vjs-tree .vjs-value__boolean) {
  color: #7c3aed;
  font-weight: 600;
}

.preview-section :deep(.vjs-tree .vjs-tree__brackets) {
  color: #6b7280;
  font-weight: 700;
}

.preview-section :deep(.vjs-tree .vjs-tree__content) {
  padding-left: 20px;
}

.preview-section :deep(.vjs-tree .vjs-tree__node) {
  padding: 4px 0;
}

.preview-section :deep(.vjs-tree .vjs-tree__node:hover) {
  background: #f0f9ff;
  border-radius: 4px;
}

.preview-section :deep(.vjs-tree .vjs-tree__indent) {
  width: 20px;
  border-left: 1px dashed #d1d5db;
  margin-left: 8px;
}

/* 折叠/展开图标 */
.preview-section :deep(.vjs-tree .vjs-tree__brackets-left),
.preview-section :deep(.vjs-tree .vjs-tree__brackets-right) {
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}

.preview-section :deep(.vjs-tree .vjs-tree__brackets-left:hover),
.preview-section :deep(.vjs-tree .vjs-tree__brackets-right:hover) {
  color: #3b82f6;
  transform: scale(1.1);
}

/* 一键微调配置 */
.tab-label-lora {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.lora-tab-icon {
  width: 36px;
  height: 18px;
  object-fit: contain;
  vertical-align: middle;
}
.module-select-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}
.module-hint-after {
  margin: 0;
  font-size: 13px;
  color: #64748b;
  line-height: 1.6;
  padding: 10px 14px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.module-hint-after code {
  font-family: ui-monospace, 'Cascadia Code', 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #475569;
  background: #e2e8f0;
  padding: 1px 6px;
  border-radius: 4px;
}
.module-expression-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 10px;
}
.module-expression-footer .el-input {
  flex: 1;
  min-width: 200px;
}
.oneclick-apply-modules {
  flex-shrink: 0;
  padding-left: 20px;
  padding-right: 20px;
}
.oneclick-container {
  background: white;
  border-radius: 16px;
  padding: 28px 32px 36px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08);
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}
.oneclick-section {
  margin-bottom: 28px;
  padding-bottom: 8px;
}
.oneclick-section:last-of-type {
  margin-bottom: 0;
}
.oneclick-section-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 18px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e2e8f0;
  letter-spacing: 0.02em;
}
/* 顶部标签：表单项间距与标签行对齐 */
.one-click-form :deep(.el-form-item) {
  margin-bottom: 20px;
}
.one-click-form :deep(.el-form-item__label) {
  display: inline-flex !important;
  align-items: center;
  justify-content: flex-start;
  gap: 0;
  line-height: 1.60;
  padding-bottom: 8px;
  height: auto !important;
  word-break: keep-all;
  white-space: normal;
  font-weight: 600;
  color: #334155;
}
.one-click-form :deep(.el-form-item__content) {
  line-height: 1.5;
}
.oneclick-fields-grid {
  display: grid;
  row-gap: 22px;
  column-gap: 28px;
  align-items: stretch;
  margin-bottom: 8px;
}
/* 基础配置首行网格与下一表单项之间略增底距（与 .oneclick-form-item--radio 上边距叠加） */
.oneclick-section:first-of-type > .oneclick-fields-grid {
  margin-bottom: 16px;
}
.oneclick-fields-grid--2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.oneclick-fields-grid :deep(.el-form-item) {
  margin-bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  width: 100%;
  min-width: 0;
}
.oneclick-fields-grid :deep(.el-form-item__content) {
  width: 100%;
  flex: 1;
}
.oneclick-fields-grid :deep(.el-input),
.oneclick-fields-grid :deep(.el-input-number),
.oneclick-fields-grid :deep(.el-select) {
  width: 100%;
}
.oneclick-fields-grid :deep(.el-input-number .el-input__wrapper) {
  width: 100%;
}
.oneclick-form-item--full {
  width: 100%;
}
/* 基础配置：两列表单项与下方「微调方式」之间留足纵向呼吸空间 */
.oneclick-form-item--radio {
  margin-top: 36px;
  padding-top: 8px;
}
.oneclick-form-item--radio :deep(.el-form-item__content) {
  width: 100%;
}
.oneclick-form-item--modules {
  margin-top: 20px;
}
.oneclick-form-item--modules :deep(.el-form-item__content) {
  width: 100%;
}
.oneclick-input-number {
  width: 100%;
}
.oneclick-select-block {
  width: 100%;
}
.oneclick-module-select {
  width: 100%;
}
.oneclick-module-select :deep(.el-select__tags) {
  flex-wrap: wrap;
  gap: 6px;
}
/* 已选标签与框内文案：中性灰，不用高亮蓝 */
.oneclick-module-select :deep(.el-tag) {
  --el-tag-text-color: #4b5563;
  color: #4b5563;
  background-color: #f3f4f6;
  border-color: #e5e7eb;
}
.oneclick-module-select :deep(.el-tag .el-tag__content) {
  color: #4b5563;
}
.oneclick-module-select :deep(.el-select__placeholder) {
  color: #9ca3af;
}
.oneclick-module-select :deep(.el-select__selected-item) {
  color: #4b5563;
}
.oneclick-radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 14px 24px;
  align-items: center;
  width: 100%;
  padding: 14px 18px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-sizing: border-box;
}
.oneclick-radio-group :deep(.el-radio) {
  margin-right: 0;
  height: auto;
  align-items: flex-start;
}
.oneclick-radio-group :deep(.el-radio__label) {
  line-height: 1.45;
  white-space: normal;
}
.oneclick-switch-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 14px;
  min-height: 36px;
  padding: 8px 0;
}
.oneclick-switch-hint {
  margin-left: 0;
  color: #64748b;
  font-size: 13px;
}
@media (max-width: 640px) {
  .oneclick-fields-grid--2 {
    grid-template-columns: 1fr;
  }
}
.form-tip { font-size: 12px; color: #6b7280; margin-top: 4px; }
.form-tip-inline { font-size: 12px; color: #6b7280; margin-left: 8px; }
.label-with-help {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
  max-width: 100%;
  word-break: keep-all;
}
.label-with-help .param-help {
  flex-shrink: 0;
  margin-left: 0;
  color: #9ca3af;
  cursor: help;
  font-size: 15px;
  width: 1em;
  height: 1em;
  vertical-align: middle;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.label-with-help .param-help:hover { color: #3b82f6; }
.oneclick-actions {
  margin-top: 28px;
  padding-top: 22px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.oneclick-actions .el-button {
  min-width: 132px;
}
.only-script-checkbox :deep(.el-checkbox__label) {
  font-size: 13px;
  color: #64748b;
}
.train-runs-section {
  margin-top: 28px;
  padding: 20px 22px 22px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-sizing: border-box;
}
.train-runs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  font-weight: 700;
  font-size: 15px;
  color: #0f172a;
}
.train-runs-table { font-size: 13px; }
.selected-tip { margin-left: 12px; color: #16a34a; font-size: 14px; }
.selected-tip strong { color: #15803d; }
.oneclick-data-tip {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 18px;
  padding: 14px 16px;
  background: #f0fdf4;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.55;
  color: #166534;
  border: 1px solid #bbf7d0;
}
.oneclick-data-tip.muted {
  background: #f1f5f9;
  color: #475569;
  border-color: #e2e8f0;
}
.oneclick-data-tip svg { font-size: 18px; flex-shrink: 0; width: 18px; height: 18px; }

/* 原文链接徽章 */
.source-url-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: white;
  text-decoration: none;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
  white-space: nowrap;
}

.source-url-badge:hover {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
  transform: translateY(-2px);
}

.source-url-empty {
  display: inline-block;
  padding: 6px 12px;
  background: #f3f4f6;
  color: #9ca3af;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>

<!-- 目标模块下拉挂到 body，用 popper-class 统一为灰色文案 -->
<style>
.oneclick-module-grey-popper .el-select-dropdown__item {
  color: #6b7280 !important;
}
.oneclick-module-grey-popper .el-select-dropdown__item.is-hovering,
.oneclick-module-grey-popper .el-select-dropdown__item:hover {
  color: #374151 !important;
  background-color: #f9fafb !important;
}
.oneclick-module-grey-popper .el-select-dropdown__item.is-selected {
  color: #4b5563 !important;
  font-weight: 500;
  background-color: #f3f4f6 !important;
}
.oneclick-module-grey-popper li[role='option'] {
  color: #6b7280 !important;
}
.oneclick-module-grey-popper li[role='option'].is-hovering,
.oneclick-module-grey-popper li[role='option']:hover {
  color: #374151 !important;
}
</style>
