/**
 * Bilibili 视频搜索包装器
 * 
 * 直接调用 @wangshunnn/bilibili-mcp-server 的搜索函数，
 * 绕过 MCP JSON-RPC 协议，消除 stdio 通信的复杂性。
 * 
 * 用法: node search.mjs <keyword> [count]
 * 输出: JSON 数组
 */

const keyword = process.argv[2];
const count = parseInt(process.argv[3], 10) || 3;

if (!keyword) {
  console.log(JSON.stringify({ error: 'keyword is required' }));
  process.exit(1);
}

// 从全局 node_modules 定位 bilibili-mcp-server
const GLOBAL_MODULES_PATHS = [
  '/opt/homebrew/Cellar/node/25.9.0_1/lib/node_modules',
  '/usr/local/lib/node_modules',
  '/usr/lib/node_modules',
  '/opt/homebrew/lib/node_modules',
];

async function findBilibiliUtils() {
  const { access } = await import('node:fs/promises');
  const { resolve } = await import('node:path');
  for (const base of GLOBAL_MODULES_PATHS) {
    const candidate = resolve(base, '@wangshunnn/bilibili-mcp-server/dist/common/utils.js');
    try {
      await access(candidate);
      return candidate;
    } catch {
      continue;
    }
  }
  // 尝试 NODE_PATH 环境变量
  const nodePath = process.env.NODE_PATH;
  if (nodePath) {
    const { resolve } = await import('node:path');
    for (const p of nodePath.split(':')) {
      const candidate = resolve(p.trim(), '@wangshunnn/bilibili-mcp-server/dist/common/utils.js');
      try {
        await access(candidate);
        return candidate;
      } catch {}
    }
  }
  throw new Error('找不到 @wangshunnn/bilibili-mcp-server 模块，请执行: npm install -g @wangshunnn/bilibili-mcp-server');
}

async function main() {
  const utilsPath = await findBilibiliUtils();
  const { searchVideos } = await import(utilsPath);

  try {
    const searchResult = await searchVideos(keyword, 1);
    if (!searchResult?.result || searchResult.result.length === 0) {
      console.log(JSON.stringify([]));
      return;
    }

    const videoResults = searchResult.result
      .filter((item) => item.result_type === 'video')?.[0]
      ?.data?.slice(0, count) || [];

    const videos = videoResults.map((video) => ({
      title: video.title?.replace(/<[^>]+>/g, '') || '',
      thumbnail: video.pic || '',
      url: `https://www.bilibili.com/video/${video.bvid}`,
      source: 'bilibili',
      views: video.play || 0,
      author: video.author || '',
      duration: formatDuration(video.duration),
    }));

    console.log(JSON.stringify(videos));
  } catch (err) {
    console.log(JSON.stringify({ error: err.message }));
    process.exit(1);
  }
}

function formatDuration(duration) {
  if (!duration || duration === '0:00') return '';
  if (typeof duration === 'number') {
    const m = Math.floor(duration / 60);
    const s = duration % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  }
  return String(duration);
}

main();
