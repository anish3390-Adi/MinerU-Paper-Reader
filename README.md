# PaperReader

一个把英文论文 PDF 转成中文 Markdown 的本地工具。

处理流程：

```text
英文 PDF
  -> MinerU 提取英文 Markdown
  -> md-translator 翻译为中文 Markdown
  -> 页面中同时查看英文原文和中文译文
```

## 适合谁用

- 想快速阅读英文论文的人
- 想把论文整理成 Markdown 的人
- 没有高性能显卡，也希望顺畅使用的人

## 功能

- 上传英文论文 PDF
- 自动提取英文 Markdown
- 自动翻译成中文 Markdown
- 页面双栏预览英文原文和中文译文
- 下载英文 Markdown、中文 Markdown 和运行日志

## 工作原理

项目由两段流程组成：

### 1. PDF 提取阶段

- `MinerU` 负责把英文论文 PDF 转成结构化英文 Markdown
- 你可以选择两种来源：
  - `cloud_api`：调用 MinerU 官方云 API
  - `cli`：调用本地 `mineru` 命令

### 2. Markdown 翻译阶段

- `md-translator` 负责把英文 Markdown 翻译成中文 Markdown
- `md-translator` 内部通过你配置的 `DeepSeek API` 完成翻译

整体上可以理解为：

```text
MinerU 负责提取
md-translator 负责翻译
Streamlit 负责展示和下载
```

## 项目结构

```text
PaperReader/
├─ app.py
├─ config.yaml
├─ requirements.txt
├─ .env.example
├─ start.bat
├─ scripts/
│  └─ start.ps1
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

最重要的部分：

- `app.py`：页面入口
- `utils/pdf_processor.py`：调用 MinerU 做 PDF 提取
- `utils/translator.py`：调用 md-translator 做 Markdown 翻译
- `external/md-translator/`：本地翻译服务
- `temp/runs/`：每次运行的输出结果

## 两种使用模式

项目支持两种 MinerU 模式，通过 `MINERU_MODE` 选择：

### 1. 官方云 API 模式

推荐优先使用：

- 更适合普通电脑
- 不需要本地部署 MinerU 模型
- 只需要配置 `MINERU_API_KEY`

对应配置：

```env
MINERU_MODE=cloud_api
```

### 2. 本地 CLI 模式

适合这些情况：

- 你已经安装好了本地 `mineru`
- 你希望完全本地运行
- 你想继续使用自己的 `pipeline` / `vlm-http-client`

对应配置：

```env
MINERU_MODE=cli
```

## 快速开始

### 1. 安装依赖

需要先准备：

- Python 3.10+
- Node.js
- corepack

然后安装 Python 依赖：

```powershell
pip install -r requirements.txt
```

### 2. 准备 md-translator

项目默认使用：

```text
external/md-translator
```

首次使用前需要构建：

```powershell
cd .\external\md-translator
$env:LOCAL_API_SERVER='true'
corepack yarn install
corepack yarn build
cd ..\..
```

### 3. 配置 `.env`

复制模板：

```powershell
Copy-Item .env.example .env
```

然后按你的使用方式填写。

## 推荐配置

### 方案 A：官方云 API 模式

这是最适合新用户的配置：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

MINERU_MODE=cloud_api
MINERU_API_KEY=your_mineru_api_key
MINERU_API_BASE_URL=https://mineru.net/api/v4
MINERU_MODEL_VERSION=vlm
MINERU_LANGUAGE=en
MINERU_ENABLE_TABLE=true
MINERU_ENABLE_FORMULA=true
MINERU_IS_OCR=false
MINERU_POLL_INTERVAL=5

NODE_BIN=node
MD_TRANSLATOR_DIR=
MD_TRANSLATOR_PORT=3000
LOG_LEVEL=INFO
```

代理注意事项：

- `cloud_api` 模式下，MinerU 官方接口会先返回一个阿里云 OSS 的临时上传地址，再上传 PDF、下载结果压缩包
- 如果系统代理、VPN、SSL 检查会干扰 `*.aliyuncs.com`，可能出现 `SSLEOFError`、上传失败、下载失败
- 实际测试中，关闭代理后云模式可以恢复正常
- 如果必须保留代理，建议至少让这些域名直连：
  - `mineru.net`
  - `mineru.oss-cn-shanghai.aliyuncs.com`
  - `*.aliyuncs.com`

### 方案 B：本地 CLI 模式

如果你已经装好了本地 MinerU，可以这样配置：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

MINERU_MODE=cli
MINERU_BIN=mineru
MINERU_BACKEND=pipeline
MINERU_API_URL=
MINERU_SERVER_URL=
MINERU_METHOD=auto
MINERU_LANG=en
MINERU_MODEL_SOURCE=local

NODE_BIN=node
MD_TRANSLATOR_DIR=
MD_TRANSLATOR_PORT=3000
LOG_LEVEL=INFO
```

## 启动项目

### 方式 1：双击启动

直接双击：

```text
start.bat
```

### 方式 2：命令行启动

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

### 方式 3：手动启动

```powershell
python -m streamlit run app.py --server.headless=true
```

启动后访问：

```text
http://localhost:8501
```

## 怎么用

1. 打开页面
2. 在左侧确认当前 `MinerU 模式`
3. 上传英文论文 PDF
4. 等待自动处理完成
5. 查看英文原文和中文译文
6. 下载结果文件

## 配置优先级

项目读取配置的优先级是：

```text
页面内切换 > .env > 系统环境变量 > config.yaml
```

这意味着：

- 新用户只需要把自己的 Key 粘贴到 `.env`
- 不需要额外配置系统环境变量

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
│  ├─ .../*.md
│  └─ zh.md
├─ logs/
│  ├─ mineru.log
│  └─ translator.log
└─ runtime/
```

其中最常用的是：

- 英文 Markdown：`output/` 下的 `.md` 文件
- 中文 Markdown：`output/zh.md`
- MinerU 日志：`logs/mineru.log`
- 翻译日志：`logs/translator.log`

## 常见问题

### 1. 推荐用哪种模式

如果你只是想稳定使用，优先选：

```env
MINERU_MODE=cloud_api
```

### 2. 云 API 模式下为什么会报 SSL 或上传失败

MinerU 官方云 API 会返回阿里云 OSS 的临时上传/下载地址。  
如果你的系统代理、VPN 或 SSL 检查会干扰 `*.aliyuncs.com`，可能出现上传失败、下载失败或 `SSLEOFError`。

遇到这种情况，优先尝试：

- 关闭代理/VPN
- 或让下面这些域名直连：
  - `mineru.net`
  - `mineru.oss-cn-shanghai.aliyuncs.com`
  - `*.aliyuncs.com`

## 致谢

本项目基于以下优秀开源项目完成核心能力整合：

- [MinerU](https://github.com/opendatalab/MinerU)
- [md-translator](https://github.com/rockbenben/md-translator)

PaperReader 的目标不是替代这些项目，而是在英文论文阅读场景下，将 PDF 解析与 Markdown 翻译串成一条更容易直接使用的工作流。
