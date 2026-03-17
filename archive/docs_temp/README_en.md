# MCP Content Fetcher

A Model Context Protocol (MCP) server for fetching and parsing content from URLs, with specialized support for Nowcoder (牛客网) interview questions and Xiaohongshu (小红书) posts.

## Features

- **URL Content Fetching**: Fetch and parse content from any URL
- **Platform Detection**: Automatically detects and optimizes parsing for:
  - Nowcoder (牛客网) - Interview questions and discussions
  - Xiaohongshu (小红书) - Social media posts
  - Generic web pages
- **Metadata Extraction**: Extracts platform-specific metadata (author, likes, views, etc.)
- **Batch Processing**: Fetch multiple URLs in a single request
- **Error Handling**: Graceful error handling with detailed error messages
- **Production Quality**: TypeScript strict mode, ESLint checks, Jest unit tests

## Installation

```bash
npm install
```

## Development

```bash
npm run dev
```

## Build

```bash
npm run build
```

## Usage

### As an MCP Server

Start the server:
```bash
npm start
```

### Tools Available

#### `fetch_content`
Fetch and parse content from a single URL.

**Parameters:**
- `url` (string, required): The URL to fetch content from

**Returns:**
```json
{
  "url": "https://...",
  "title": "Content Title",
  "content": "Full content text...",
  "platform": "nowcoder|xiaohongshu|generic",
  "fetchedAt": "2024-03-12T10:30:00.000Z",
  "metadata": {
    "author": "...",
    "views": "...",
    "likes": "..."
  }
}
```

#### `fetch_multiple_contents`
Fetch and parse content from multiple URLs in batch.

**Parameters:**
- `urls` (array of strings, required): Array of URLs to fetch

**Returns:**
Array of content objects (same format as `fetch_content`)

## Examples

### Fetch a Nowcoder Interview Question
```
fetch_content(url="https://www.nowcoder.com/discuss/...")
```

### Fetch Multiple Xiaohongshu Posts
```
fetch_multiple_contents(urls=[
  "https://www.xiaohongshu.com/explore/...",
  "https://www.xiaohongshu.com/explore/..."
])
```

## Project Structure

```
mcp-content-fetcher/
├── src/
│   ├── index.ts                 # MCP server main file
│   └── content-fetcher.ts       # Content fetching and parsing logic
├── tests/
│   └── content-fetcher.test.ts  # Unit tests
├── package.json                 # npm configuration
├── tsconfig.json                # TypeScript configuration
├── jest.config.js               # Jest test configuration
├── .eslintrc.json               # ESLint configuration
├── README.md                    # Chinese documentation
├── README_en.md                 # English documentation (this file)
└── Other configuration files
```

## Technology Stack

| Technology | Purpose |
|-----------|---------|
| **TypeScript** | Type-safe JavaScript |
| **MCP SDK** | Model Context Protocol implementation |
| **axios** | HTTP client library |
| **cheerio** | HTML parsing library (jQuery-style) |
| **Jest** | Unit testing framework |
| **ESLint** | Code quality checking |
| **ts-node** | Run TypeScript directly |

## Core Features

### Platform Auto-Detection

The server automatically identifies the platform based on URL:

```typescript
private detectPlatform(url: string): string {
  if (url.includes('nowcoder.com')) return 'nowcoder';
  if (url.includes('xiaohongshu.com') || url.includes('xhs.com')) return 'xiaohongshu';
  return 'generic';
}
```

### Platform-Specific Parsing

Each platform has a dedicated parser optimized for its HTML structure:

- **Nowcoder Parser**: Extracts interview questions, discussion content, author info, etc.
- **Xiaohongshu Parser**: Extracts post content, author, interaction data, etc.
- **Generic Parser**: Uses common selectors to extract title and content

### Batch Processing

Supports parallel processing of multiple URLs for improved efficiency:

```typescript
const results = await Promise.all(
  urls.map(url => contentFetcher.fetchContent(url))
);
```

### Error Handling

- Network timeout control (10 seconds)
- URL validation (Zod schema)
- Error isolation in batch processing
- Detailed error messages

## Usage Examples

### Get a Single Nowcoder Interview Question

```bash
# Using MCP tool
fetch_content(url="https://www.nowcoder.com/discuss/123")
```

### Batch Fetch Xiaohongshu Posts

```bash
# Using MCP tool
fetch_multiple_contents(urls=[
  "https://www.xiaohongshu.com/explore/123",
  "https://www.xiaohongshu.com/explore/456"
])
```

## Environment Variables

Currently, the project doesn't require special environment variables. If needed, you can configure them in a `.env` file:

```
# .env
TIMEOUT=10000
MAX_RETRIES=3
```

## Performance Metrics

- **Request Timeout**: 10 seconds (configurable)
- **Batch Processing**: Parallel requests with no serialization delay
- **Memory Usage**: Lightweight, suitable for long-running operations
- **HTML Parsing**: Using cheerio, fast and efficient

## Error Handling

The server gracefully handles various error scenarios:

| Error Type | Handling |
|-----------|----------|
| Network Timeout | Returns timeout error message |
| Invalid URL | Zod validation failure |
| Parsing Failure | Fallback to generic parser |
| Batch Processing Failure | Individual failures don't affect other URLs |

## Testing

The project includes comprehensive unit tests:

```bash
# Run all tests
npm test

# Run specific test file
npx jest tests/content-fetcher.test.ts --no-cache

# View test coverage
npm test -- --coverage
```

## Code Quality

### TypeScript Configuration
- `strict` mode enabled
- Complete type definitions
- Interface and type exports

### ESLint Checks
```bash
npm run lint
```

### Code Style
- Clear variable names
- Complete function documentation
- Appropriate code comments

## Supported Platforms

### Nowcoder (牛客网)
- Interview questions
- Discussion posts
- Extracts: title, content, author, views, likes

### Xiaohongshu (小红书)
- Social media posts
- Notes and articles
- Extracts: title, content, author, likes, comments, shares

### Generic Web Pages
- Any URL
- Extracts: title, content, meta description, keywords

## License

MIT

## Author

Created for portfolio demonstration of MCP server development and web content integration.

## Related Documentation

- [Quick Start Guide](QUICKSTART.md) - Get started quickly
- [Project Summary](PROJECT_SUMMARY.md) - Project completion summary
- [Resume Description](RESUME.md) - Resume project description
- [Development Guide](CLAUDE.md) - Claude development guide
- [Completion Checklist](CHECKLIST.md) - Project completion checklist
- [Delivery Report](DELIVERY_REPORT.md) - Project delivery report

## FAQ

### Q: How do I use this MCP Server in my Agent?
A: Add this MCP Server's path to your Agent configuration, then you can call its tools.

### Q: Which platforms are supported?
A: Currently supports Nowcoder, Xiaohongshu, and generic web pages. Easy to extend for more platforms.

### Q: How do you handle website anti-scraping mechanisms?
A: The project is configured with reasonable User-Agent and timeout controls. For more complex anti-scraping, you can add proxy support.

### Q: Can I modify the project?
A: Absolutely! This is an open-source project, feel free to fork and modify.

### Q: How can I contribute code?
A: Welcome to submit Pull Requests or Issues.

## Future Improvements

Possible future improvements:

- [ ] Add caching mechanism (Redis)
- [ ] Implement rate limiting and proxy support
- [ ] Support more platforms (LeetCode, GitHub, Medium, etc.)
- [ ] Database storage and query functionality
- [ ] Web UI management interface
- [ ] Docker containerization
- [ ] Publish to npm

## Contact

If you have any questions or suggestions, feel free to contact us through:

- GitHub Issues: [Submit Issue](https://github.com/Wangxr126/mcp-content-fetcher/issues)
- GitHub Discussions: [Discussions](https://github.com/Wangxr126/mcp-content-fetcher/discussions)

---

**Thank you for using MCP Content Fetcher!** 🚀
