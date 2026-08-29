#!/usr/bin/env node
/**
 * Bilibili 视频搜索包装器 (CommonJS)
 * 
 * 通过 stdio JSON-RPC 协议与 @wangshunnn/bilibili-mcp-server 通信。
 * 保持 stdio 监听器活跃直到收到 tools/call 响应。
 * 
 * 用法: node search.cjs <keyword> [count]
 * 输出: JSON 数组
 */
const { spawn } = require('node:child_process');
const path = require('node:path');

const keyword = process.argv[2];
const count = parseInt(process.argv[3], 10) || 3;

if (!keyword) {
  console.error('[ERROR] keyword is required');
  process.exit(1);
}

// 查找 MCP 服务器入口
const GLOBAL_PATHS = [
  '/opt/homebrew/Cellar/node/25.9.0_1/lib/node_modules',
  '/usr/local/lib/node_modules',
  '/usr/lib/node_modules',
  '/opt/homebrew/lib/node_modules',
];

function findMcpEntry() {
  const fs = require('node:fs');
  for (const base of GLOBAL_PATHS) {
    const p = path.join(base, '@wangshunnn/bilibili-mcp-server', 'dist', 'index.js');
    if (fs.existsSync(p)) return p;
  }
  // 尝试 NODE_PATH
  const nodePath = process.env.NODE_PATH;
  if (nodePath) {
    for (const p of nodePath.split(':')) {
      const candidate = path.join(p.trim(), '@wangshunnn/bilibili-mcp-server', 'dist', 'index.js');
      if (fs.existsSync(candidate)) return candidate;
    }
  }
  return null;
}

const entryPoint = findMcpEntry();
if (!entryPoint) {
  console.error('[ERROR] 找不到 @wangshunnn/bilibili-mcp-server，请执行: npm install -g @wangshunnn/bilibili-mcp-server');
  process.exit(1);
}

const proc = spawn(process.execPath, [entryPoint], {
  stdio: ['pipe', 'pipe', 'pipe'],
  env: { ...process.env },
});

let stderrBuf = '';
proc.stderr.on('data', (chunk) => { stderrBuf += chunk.toString(); });

let responseData = null;
let buffer = '';
let msgCount = 0;

proc.stdout.on('data', (chunk) => {
  buffer += chunk.toString();
  const lines = buffer.split('\n');
  buffer = lines.pop() || '';
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const msg = JSON.parse(trimmed);
      msgCount++;
      // tools/call 响应
      if (msg.id && msg.result) {
        responseData = msg;
      }
    } catch {
      // JSON 不完整，继续累积
    }
  }
});

// 发送 initialize
proc.stdin.write(JSON.stringify({
  jsonrpc: '2.0',
  id: 1,
  method: 'initialize',
  params: {
    protocolVersion: '2024-11-05',
    capabilities: {},
    clientInfo: { name: 'bilibili-search', version: '1.0.0' },
  },
}) + '\n');

// 等待 200ms 再发 initialized 通知 + tools/call
setTimeout(() => {
  proc.stdin.write(JSON.stringify({
    jsonrpc: '2.0',
    method: 'notifications/initialized',
  }) + '\n');

  proc.stdin.write(JSON.stringify({
    jsonrpc: '2.0',
    id: 2,
    method: 'tools/call',
    params: {
      name: 'search_videos',
      arguments: { keyword, page: 1, count },
    },
  }) + '\n');
}, 200);

// 等待结果
setTimeout(async () => {
  proc.stdin.end();

  if (!responseData) {
    console.error('[ERROR] MCP 无响应, stderr:', stderrBuf.slice(0, 500));
    process.exit(1);
  }

  if (responseData.error) {
    console.error('[ERROR] MCP error:', responseData.error.message);
    process.exit(1);
  }

  const textContent = responseData.result?.content?.[0]?.text || '';
  if (!textContent) {
    console.log(JSON.stringify([]));
    proc.kill();
    return;
  }

  const lines = textContent.split('\n');
  const videos = [];
  let currentVideo = null;

  for (const line of lines) {
    const titleMatch = line.match(/^\d+\.\s+"(.+)"\s*-\s*(.+)$/);
    if (titleMatch) {
      if (currentVideo && currentVideo.title) videos.push(currentVideo);
      currentVideo = {
        title: titleMatch[1].replace(/<[^>]+>/g, ''),
        author: titleMatch[2].trim(),
        thumbnail: '',
        url: '',
        source: 'bilibili',
        views: 0,
        duration: '',
      };
      continue;
    }
    if (!currentVideo) continue;

    const bv = line.match(/BV\s*ID:\s*(\w+)/);
    if (bv) {
      currentVideo.url = `https://www.bilibili.com/video/${bv[1]}`;
      currentVideo.bvid = bv[1];
    }

    const vw = line.match(/Views:\s*([\d,]+)/);
    if (vw) currentVideo.views = parseInt(vw[1].replace(/,/g, ''), 10);

    const dr = line.match(/Duration:\s*(.+)/);
    if (dr) currentVideo.duration = dr[1].trim();
  }

  if (currentVideo && currentVideo.title) videos.push(currentVideo);

  // 补充分享图
  for (const v of videos) {
    if (v.bvid) {
      try {
        const res = await fetch(`https://api.bilibili.com/x/web-interface/view?bvid=${v.bvid}`, {
          signal: AbortSignal.timeout(3000),
          headers: {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://www.bilibili.com',
          },
        });
        if (res.ok) {
          const json = await res.json();
          if (json.code === 0 && json.data?.pic) {
            v.thumbnail = json.data.pic.replace(/^http:\/\//i, 'https://');
          }
        }
      } catch {
        // 封面获取失败不影响主流程
      }
    }
  }

  console.log(JSON.stringify(videos));
  proc.kill();
}, 20000); // 20s 超时（含缩略图获取）
