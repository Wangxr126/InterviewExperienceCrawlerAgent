#!/usr/bin/env node
/**
 * MCP Server: mcp-speech-to-text
 * 通过 OpenAI Whisper API 将音频文件/URL/base64 转换为文字
 * 注册为 MCP tool，供 Agent 在对话链路中调用
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js'
import * as fs from 'fs'
import * as path from 'path'
import * as https from 'https'
import * as http from 'http'
import { createReadStream } from 'fs'
import FormData from 'form-data'
import * as os from 'os'

// ── 环境配置 ──────────────────────────────────────────────────────────────
const OPENAI_API_KEY  = process.env.OPENAI_API_KEY  || ''
const OPENAI_BASE_URL = (process.env.OPENAI_BASE_URL || 'https://api.openai.com').replace(/\/$/, '')
const WHISPER_MODEL   = process.env.WHISPER_MODEL   || 'whisper-1'
const MAX_FILE_SIZE   = parseInt(process.env.MAX_AUDIO_SIZE || '26214400') // 25 MB

const SUPPORTED_FORMATS = new Set(['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.ogg', '.flac'])

// ── MCP Server ────────────────────────────────────────────────────────────
const server = new Server(
  { name: 'mcp-speech-to-text', version: '1.0.0' },
  { capabilities: { tools: {} } }
)

// ── 工具列表 ──────────────────────────────────────────────────────────────
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: 'transcribe_audio_file',
      description:
        '将本地音频文件转为文字（Whisper API）。支持 mp3/wav/m4a/webm/flac/ogg，文件 ≤25MB。',
      inputSchema: {
        type: 'object',
        properties: {
          file_path: { type: 'string', description: '本地音频文件的绝对路径' },
          language:  { type: 'string', description: '语言代码（zh/en/ja 等），留空自动检测', default: 'zh' },
          prompt:    { type: 'string', description: '提示词，帮助识别专有名词（如技术术语）' },
        },
        required: ['file_path'],
      },
    },
    {
      name: 'transcribe_audio_url',
      description: '下载远程音频 URL 并转为文字（Whisper API）。',
      inputSchema: {
        type: 'object',
        properties: {
          url:      { type: 'string', description: '音频 HTTP/HTTPS URL' },
          language: { type: 'string', description: '语言代码，留空自动检测', default: 'zh' },
          prompt:   { type: 'string', description: '可选提示词' },
        },
        required: ['url'],
      },
    },
    {
      name: 'transcribe_audio_base64',
      description:
        '将 base64 编码的音频转为文字（Whisper API）。适合直接传递录音内容，无需落盘。',
      inputSchema: {
        type: 'object',
        properties: {
          audio_base64: { type: 'string', description: 'base64 音频数据（不含 data URI 前缀）' },
          format:       { type: 'string', description: '音频格式：mp3/wav/webm/m4a', default: 'webm' },
          language:     { type: 'string', description: '语言代码，留空自动检测', default: 'zh' },
          prompt:       { type: 'string', description: '可选提示词' },
        },
        required: ['audio_base64'],
      },
    },
  ],
}))

// ── 工具调用 ──────────────────────────────────────────────────────────────
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params
  if (!OPENAI_API_KEY) {
    return err('未配置 OPENAI_API_KEY 环境变量，无法调用 Whisper API')
  }
  try {
    switch (name) {
      case 'transcribe_audio_file':   return await doFile(args as any)
      case 'transcribe_audio_url':    return await doUrl(args as any)
      case 'transcribe_audio_base64': return await doBase64(args as any)
      default: return err(`未知工具: ${name}`)
    }
  } catch (e: any) {
    return err(`调用失败: ${e.message}`)
  }
})

// ── 处理本地文件 ──────────────────────────────────────────────────────────
async function doFile(args: { file_path: string; language?: string; prompt?: string }) {
  const fp = args.file_path
  if (!fs.existsSync(fp)) return err(`文件不存在: ${fp}`)

  const ext = path.extname(fp).toLowerCase()
  if (!SUPPORTED_FORMATS.has(ext)) return err(`不支持的音频格式: ${ext}，支持: ${[...SUPPORTED_FORMATS].join('/')}`)

  const stat = fs.statSync(fp)
  if (stat.size > MAX_FILE_SIZE) return err(`文件过大: ${(stat.size / 1024 / 1024).toFixed(1)}MB，限制 25MB`)

  const text = await callWhisper(createReadStream(fp), path.basename(fp), args.language, args.prompt)
  return ok(text, { source: fp, size_bytes: stat.size })
}

// ── 处理 URL ──────────────────────────────────────────────────────────────
async function doUrl(args: { url: string; language?: string; prompt?: string }) {
  const tmpFile = path.join(os.tmpdir(), `mcp_audio_${Date.now()}${path.extname(new URL(args.url).pathname) || '.mp3'}`)
  try {
    await downloadFile(args.url, tmpFile)
    const stat = fs.statSync(tmpFile)
    if (stat.size > MAX_FILE_SIZE) {
      fs.unlinkSync(tmpFile)
      return err(`下载文件过大: ${(stat.size / 1024 / 1024).toFixed(1)}MB，限制 25MB`)
    }
    const text = await callWhisper(createReadStream(tmpFile), path.basename(tmpFile), args.language, args.prompt)
    return ok(text, { source: args.url, size_bytes: stat.size })
  } finally {
    if (fs.existsSync(tmpFile)) fs.unlinkSync(tmpFile)
  }
}

// ── 处理 base64 ──────────────────────────────────────────────────────────
async function doBase64(args: { audio_base64: string; format?: string; language?: string; prompt?: string }) {
  const fmt = (args.format || 'webm').replace(/^[.]+/, '')
  const buf = Buffer.from(args.audio_base64, 'base64')
  if (buf.length > MAX_FILE_SIZE) return err(`base64 数据过大: ${(buf.length / 1024 / 1024).toFixed(1)}MB，限制 25MB`)

  const tmpFile = path.join(os.tmpdir(), `mcp_audio_${Date.now()}.${fmt}`)
  try {
    fs.writeFileSync(tmpFile, buf)
    const text = await callWhisper(createReadStream(tmpFile), `audio.${fmt}`, args.language, args.prompt)
    return ok(text, { source: 'base64', size_bytes: buf.length })
  } finally {
    if (fs.existsSync(tmpFile)) fs.unlinkSync(tmpFile)
  }
}

// ── Whisper API 调用 ──────────────────────────────────────────────────────
function callWhisper(
  stream: fs.ReadStream,
  filename: string,
  language?: string,
  prompt?: string
): Promise<string> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', stream, { filename })
    form.append('model', WHISPER_MODEL)
    if (language) form.append('language', language)
    if (prompt)   form.append('prompt', prompt)
    form.append('response_format', 'json')

    const endpoint = `${OPENAI_BASE_URL}/v1/audio/transcriptions`
    const urlObj   = new URL(endpoint)
    const lib      = urlObj.protocol === 'https:' ? https : http
    const headers  = {
      ...form.getHeaders(),
      Authorization: `Bearer ${OPENAI_API_KEY}`,
    }

    const req = lib.request(
      { hostname: urlObj.hostname, port: urlObj.port, path: urlObj.pathname, method: 'POST', headers },
      (res) => {
        let body = ''
        res.on('data', (c) => (body += c))
        res.on('end', () => {
          if (res.statusCode && res.statusCode >= 400) {
            reject(new Error(`Whisper API 返回 ${res.statusCode}: ${body}`))
            return
          }
          try {
            const json = JSON.parse(body)
            resolve(json.text || '')
          } catch {
            reject(new Error(`解析响应失败: ${body}`))
          }
        })
      }
    )
    req.on('error', reject)
    form.pipe(req)
  })
}

// ── 下载文件 ─────────────────────────────────────────────────────────────
function downloadFile(url: string, dest: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest)
    const lib  = url.startsWith('https') ? https : http
    lib.get(url, (res) => {
      if (res.statusCode && res.statusCode >= 400) {
        reject(new Error(`下载失败 HTTP ${res.statusCode}`))
        return
      }
      res.pipe(file)
      file.on('finish', () => file.close(() => resolve()))
    }).on('error', (e) => {
      fs.unlinkSync(dest)
      reject(e)
    })
  })
}

// ── 响应工具 ─────────────────────────────────────────────────────────────
function ok(text: string, meta: object) {
  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify({ success: true, transcript: text, ...meta, model: WHISPER_MODEL }),
      },
    ],
  }
}

function err(msg: string) {
  return {
    content: [{ type: 'text', text: JSON.stringify({ success: false, error: msg }) }],
    isError: true,
  }
}

// ── 启动 ─────────────────────────────────────────────────────────────────
async function main() {
  const transport = new StdioServerTransport()
  await server.connect(transport)
  console.error('[mcp-speech-to-text] MCP server running on stdio')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
