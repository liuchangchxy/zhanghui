#!/usr/bin/env bash
# 新书项目从零开始的初始化脚本。
#
# 用法：./new_book_project.sh <新书项目绝对路径> <书名> <流派>
# 例：./new_book_project.sh ~/Desktop/新小说 "新书名" "玄幻"
#
# 做了 4 件事：
# 1. 创建书项目目录
# 2. 在 claude 里跑 /webnovel-init 建 .webnovel/ 骨架
# 3. 从已有项目（默认 ~/Desktop/根源牌序）复制 .env（API key）
# 4. 打印下一步指引

set -euo pipefail

if [ $# -lt 3 ]; then
    echo "Usage: $0 <book_project_path> <title> <genre>"
    echo "Example: $0 ~/Desktop/新小说 \"新书名\" \"玄幻\""
    exit 1
fi

BOOK_PATH="$1"
TITLE="$2"
GENRE="$3"
SOURCE_ENV="${4:-$HOME/Desktop/根源牌序/.env}"

echo "=== new book project setup ==="
echo "target:   $BOOK_PATH"
echo "title:    $TITLE"
echo "genre:    $GENRE"
echo "source .env: $SOURCE_ENV"
echo ""

# 1. 创建目录
echo "[1/4] Creating book directory..."
mkdir -p "$BOOK_PATH"
echo "  ✓ $BOOK_PATH created"

# 2. 跑 webnovel init 建 .webnovel/ 骨架
echo "[2/4] Running webnovel init..."
WEBNOVEL_PY="/Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts/webnovel.py"
if [ ! -f "$WEBNOVEL_PY" ]; then
    echo "  ERROR: webnovel.py 不存在：$WEBNOVEL_PY"
    echo "  请先跑 ./setup_dev_env.sh"
    exit 1
fi
python3 -X utf8 "$WEBNOVEL_PY" --project-root "$BOOK_PATH" init "$BOOK_PATH" "$TITLE" "$GENRE" 2>&1 | tail -10
echo "  ✓ init 完成"

# 3. 复制 .env（API key）
echo "[3/4] Copying .env from source..."
if [ -f "$SOURCE_ENV" ]; then
    cp "$SOURCE_ENV" "$BOOK_PATH/.env"
    echo "  ✓ .env 已从 $SOURCE_ENV 复制"
else
    echo "  ⚠️  $SOURCE_ENV 不存在，跳过 .env 复制"
    echo "  请手动从已有书项目复制 .env，或跑 setup_env.sh 创建"
fi

# 4. 复制 .gitignore（如果 dev 有）
echo "[4/4] Copying .gitignore (if available)..."
GITIGNORE_SRC="$(dirname "$0")/../../../../.gitignore"
if [ -f "$GITIGNORE_SRC" ]; then
    cp "$GITIGNORE_SRC" "$BOOK_PATH/.gitignore"
    echo "  ✓ .gitignore 已复制"
else
    echo "  (no .gitignore template found, skipping)"
fi

echo ""
echo "=== new book project ready ==="
echo "  path:  $BOOK_PATH"
echo "  title: $TITLE"
echo "  genre: $GENRE"
echo ""
echo "下一步："
echo "  cd $BOOK_PATH"
echo "  claude                          # 启动 Claude Code session"
echo "  /webnovel-doctor                # 验证 plugin 加载成功"
echo "  /webnovel-write 1               # 开始写第 1 章"
echo ""
echo "  （slash commands 来自 zhanghui plugin，不需要任何 .claude/ 在书项目里）"
