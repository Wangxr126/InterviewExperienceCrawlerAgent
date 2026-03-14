# MCP Content Fetcher 部署错误排查

本文档汇总 mcp-content-fetcher 在 Render 部署过程中遇到的所有错误及解决方案。

---

## 错误 1：TypeScript 编译失败 - 找不到模块

### 现象

```
src/content-fetcher.ts(1,38): error TS2307: Cannot find module 'axios' or its corresponding type declarations.
src/index.ts(2,27): error TS2307: Cannot find module '@modelcontextprotocol/sdk/server/mcp.js' or its corresponding type declarations.
...
src/index.ts(9,30): error TS2307: Cannot find module 'fs' or its corresponding type declarations.
src/index.ts(84,14): error TS2580: Cannot find name 'process'. Do you need to install type definitions for node?
```

### 原因

1. `tsconfig.json` 未配置 Node 类型，导致 `process`、`console`、`__dirname`、`fs`、`path` 等 Node 内置对象未定义
2. 回调参数缺少类型注解，触发 `noImplicitAny` 报错

### 解决方案

1. **tsconfig.json**：添加 `"types": ["node"]`（后因 Render 环境问题改为移除，见错误 2）
2. **content-fetcher.ts**：为 map 回调添加类型
   ```ts
   // 之前: (_, el) =>
   // 之后: (_: number, el: unknown) =>
   ```
3. **index.ts**：为工具回调、Express 请求/响应添加类型
   ```ts
   async (args: { url: string }) => { ... }
   async (req: Request, res: Response) => { ... }
   ```

---

## 错误 2：找不到 Node 类型定义文件

### 现象

```
error TS2688: Cannot find type definition file for 'node'.
  The file is in the program because:
    Entry point of type library 'node' specified in compilerOptions
```

### 原因

- `tsconfig.json` 中 `"types": ["node"]` 要求安装 `@types/node`
- Render 在构建时可能使用 `NODE_ENV=production`，跳过 `devDependencies`，导致 `@types/node` 未安装

### 解决方案

**方案 A**：将 `@types/node` 移到 `dependencies`（生产依赖）

```json
"dependencies": {
  "@types/node": "^20.10.0",
  ...
}
```

**方案 B**：移除 `tsconfig.json` 中的 `"types": ["node"]`，让 TypeScript 自动发现 `node_modules/@types` 中的类型

---

## 错误 3：JavaScript 堆内存溢出 (OOM)

### 现象

```
FATAL ERROR: Ineffective mark-compacts near heap limit Allocation failed - JavaScript heap out of memory
```

### 原因

- Render 免费实例内存约 512MB
- TypeScript 编译器 (tsc) 内存占用高，构建时超出限制

### 解决方案

**用 esbuild 替代 tsc**：

1. 添加 `esbuild` 到 `dependencies`
2. 创建 `build.mjs`：

```javascript
import * as esbuild from 'esbuild';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(join(__dirname, 'package.json'), 'utf-8'));
const external = [...Object.keys(pkg.dependencies || {}), ...Object.keys(pkg.peerDependencies || {})];

await esbuild.build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  platform: 'node',
  target: 'node16',
  outfile: 'dist/index.js',
  external,
  format: 'cjs',
});
```

3. 修改 `package.json` build 脚本：

```json
"build": "node build.mjs && node -e \"require('fs').chmodSync('dist/index.js', '755')\""
```

---

## 错误 4：找不到 esbuild 模块

### 现象

```
Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'esbuild' imported from /opt/render/project/src/build.mjs
```

### 原因

1. `esbuild` 在 `devDependencies` 中，Render 可能跳过 dev 依赖
2. Render 的 Build Command 可能未先执行 `npm install`，导致 `node_modules` 为空

### 解决方案

1. **将 esbuild 移到 dependencies**：

```json
"dependencies": {
  "esbuild": "^0.24.0",
  ...
}
```

2. **在 build 脚本中显式执行 npm install**：

```json
"build": "npm install && node build.mjs && node -e \"require('fs').chmodSync('dist/index.js', '755')\""
```

---

## 总结

| 错误类型 | 根本原因 | 解决方式 |
|----------|----------|----------|
| 找不到模块/类型 | tsconfig 缺少 Node 类型、参数未显式类型 | 添加类型、移除/调整 types 配置 |
| 找不到 @types/node | devDependencies 被跳过 | 移到 dependencies 或移除 types |
| OOM | tsc 内存占用高 | 用 esbuild 替代 tsc |
| 找不到 esbuild | dev 依赖未安装、构建前未 install | 移到 dependencies + build 中 npm install |

---

## 最终有效配置

- **package.json**：`esbuild` 在 `dependencies`，build 脚本含 `npm install`
- **tsconfig.json**：移除 `declaration`/`declarationMap`/`sourceMap`，移除 `types` 显式配置
- **build.mjs**：使用 esbuild 打包，external 依赖不打包进产物
