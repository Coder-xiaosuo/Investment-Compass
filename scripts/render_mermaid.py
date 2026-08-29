from playwright.sync_api import sync_playwright
import sys
import os

def render_mermaid(mmd_path, output_path, width=1200, height=800, dark=False):
    with open(mmd_path, 'r', encoding='utf-8') as f:
        mmd_content = f.read()
    
    bg_color = '#0a0e17' if dark else '#ffffff'
    theme = 'dark' if dark else 'default'
    
    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Mermaid Render</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
body {{ margin: 0; padding: 40px; background: {bg_color}; }}
.mermaid {{ font-family: 'JetBrains Mono', 'Noto Sans SC', sans-serif; }}
</style>
</head>
<body>
<div class="mermaid">
{mmd_content}
</div>
<script>
mermaid.initialize({{ 
    theme: '{theme}', 
    fontFamily: 'JetBrains Mono, Noto Sans SC, sans-serif',
    fontSize: 12 
}});
</script>
</body>
</html>
"""
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': width, 'height': height})
        page.set_content(html_content)
        page.wait_for_timeout(3000)
        
        element = page.locator('.mermaid svg')
        if element.count() > 0:
            element.screenshot(path=output_path)
            print(f"Successfully rendered to {output_path}")
        else:
            page.screenshot(path=output_path)
            print(f"SVG not found, took full page screenshot to {output_path}")
        
        browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python render_mermaid.py <input.mmd> <output.png> [--dark]")
        sys.exit(1)
    
    mmd_path = sys.argv[1]
    output_path = sys.argv[2]
    dark = '--dark' in sys.argv[3:] if len(sys.argv) > 3 else False
    
    if not os.path.exists(mmd_path):
        print(f"File not found: {mmd_path}")
        sys.exit(1)
    
    render_mermaid(mmd_path, output_path, dark=dark)
