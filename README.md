# PaperReader

一个把英文论文 PDF 转成中文 Markdown 的本地工具。

处理流程：

```text
英文 PDF
  -> MinerU 提取英文 Markdown
  -> md-translator 翻译为中文 Markdown
  -> 页面中同时查看英文原文和中文译文
```

## 功能

- 上传英文论文 PDF
- 自动提取英文 Markdown
- 自动翻译成中文 Markdown
- 页面双栏预览英文原文和中文译文
- 下载英文 Markdown、中文 Markdown 和运行日志
- 对大 Markdown 自动分块翻译，避免单次请求超时
- 对已有 `full.md` 支持续跑，不必重复执行 MinerU

## 工作原理

项目由两段流程组成：

### 1. PDF 提取阶段

- `MinerU` 负责把英文论文 PDF 转成结构化英文 Markdown
- 可以选择两种来源：
  - `cloud_api`：调用 MinerU 官方云 API
  - `cli`：调用本地 `mineru` 命令

### 2. Markdown 翻译阶段

- `md-translator` 负责把英文 Markdown 翻译成中文 Markdown
- 对超大 Markdown 会自动切成多个块逐块翻译，并把中间结果保存在 `translation_chunks/`
- 本地 `127.0.0.1` 调用会绕过系统代理，避免本地翻译服务被代理误拦截

## 项目结构

```text
PaperReader/
├─ app.py
├─ config.yaml
├─ requirements.txt
├─ .env.example
├─ start.bat
├─ start.command
├─ scripts/
│  ├─ start.ps1
│  ├─ setup_macos.sh
│  ├─ start_macos.sh
│  └─ resume_translation.sh
├─ external/
│  └─ md-translator/
├─ utils/
│  ├─ config_manager.py
│  ├─ pdf_processor.py
│  ├─ translator.py
│  ├─ image_processor.py
│  └─ error_handler.py
└─ temp/
   └─ runs/
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js
- corepack

### 安装依赖

```bash
pip install -r requirements.txt
```

### 构建 md-translator

```bash
cd external/md-translator
corepack yarn install
LOCAL_API_SERVER=true corepack yarn build
cd ../..
```

### 配置 `.env`

复制模板：

```bash
cp .env.example .env
```

然后填写：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
MINERU_API_KEY=your_mineru_api_key
```

## 启动项目

### Windows

```text
start.bat
```

### macOS

首次初始化：

```bash
./scripts/setup_macos.sh
```

启动：

```bash
./scripts/start_macos.sh
```

也可以直接双击：

```text
start.command
```

### 手动启动

```bash
python -m streamlit run app.py --server.headless=true
```

启动后访问：

```text
http://127.0.0.1:8501
```

## 续跑翻译

如果 MinerU 已经完成并产出了 `output/full.md`，但翻译阶段失败，可以直接续跑翻译而不重复执行 MinerU：

```bash
./scripts/resume_translation.sh /absolute/path/to/temp/runs/<timestamp>-<paper-name>
```

输出仍会写回同一个运行目录下的：

```text
output/zh.md
```

分块翻译的中间结果会保存在：

```text
translation_chunks/
```

再次执行时会自动复用已完成的块。

## 输出结果在哪里

每次运行的结果会保存在：

```text
temp/runs/<timestamp>-<paper-name>/
```

典型结构如下：

```text
temp/runs/<timestamp>-<paper-name>/
├─ input/
│  └─ paper.pdf
├─ output/
│  ├─ full.md
│  └─ zh.md
├─ logs/
│  ├─ mineru.log
│  ├─ translator.log
│  ├─ md-translator-server.out.log
│  └─ md-translator-server.err.log
├─ runtime/
└─ translation_chunks/
```

## 常见问题

### 1. `user authenticate failed`

说明当前 `MINERU_API_KEY` 没有通过 MinerU 云 API 认证。  
请确认填写的是 MinerU 官方云 API 可用的正式 key，而不是网页登录态 token。

### 2. `md-translator 服务启动失败`，但日志里显示服务已经 Ready

如果系统配置了 HTTP 代理，本地 `127.0.0.1` 请求可能被错误地送进代理。  
当前版本已经对本地翻译服务绕过代理处理。

### 3. `This operation was aborted`

通常是单次翻译内容过大或耗时过长。  
当前版本会自动分块翻译，并在失败后支持续跑。

## 致谢

本项目基于以下优秀开源项目完成核心能力整合：

- [MinerU](https://github.com/opendatalab/MinerU)
- [md-translator](https://github.com/rockbenben/md-translator)
