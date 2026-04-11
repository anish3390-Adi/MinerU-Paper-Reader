import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from utils.config_manager import config_manager


class Translator:
    """Calls the local md-translator API service and auto-starts it when needed."""

    def __init__(self):
        self.translation_config = config_manager.get_translation_config()
        self.node_command = config_manager.get_tool_command("node")
        self.project_dir = config_manager.get_translation_project_dir()
        self.standalone_entry = config_manager.get_translation_standalone_entry()
        self.api_url = config_manager.get_translation_api_url()
        self.request_timeout = int(os.getenv("PAPERREADER_TRANSLATE_REQUEST_TIMEOUT", self.translation_config.get("request_timeout", 7200)))
        self.start_timeout = self.translation_config.get("start_timeout", 30)
        self.host = self.translation_config.get("host", "127.0.0.1")
        self.port = config_manager.get_translation_port()
        self.chunk_char_limit = max(
            2000,
            int(os.getenv("PAPERREADER_TRANSLATE_CHUNK_CHAR_LIMIT", self.translation_config.get("chunk_char_limit", 8000))),
        )
        retry_timeout_override = os.getenv("PAPERREADER_TRANSLATE_RETRY_TIMEOUT")
        if retry_timeout_override is None:
            retry_timeout_value = max(int(self.translation_config.get("retry_timeout", 180)), 180)
        else:
            retry_timeout_value = int(retry_timeout_override)
        self.retry_timeout = max(30, retry_timeout_value)
        self.batch_size = max(
            1,
            int(os.getenv("PAPERREADER_TRANSLATE_BATCH_SIZE", self.translation_config.get("batch_size", 1))),
        )

    def translate(self, input_file, output_file, run_root=None, log_path=None):
        input_path = Path(input_file)
        output_path = Path(output_file)
        run_root = Path(run_root) if run_root else output_path.parent
        log_path = Path(log_path) if log_path else None

        if not input_path.exists():
            return False, f"输入 Markdown 文件不存在: {input_path}", None

        markdown = input_path.read_text(encoding="utf-8")
        if not markdown.strip():
            return False, "输入 Markdown 为空，无法翻译。", None

        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            start_info = self._ensure_service(run_root, log_path)
            translated_markdown = self._translate_markdown(markdown, run_root, log_path, start_info)
        except requests.RequestException as exc:
            self._write_log(log_path, error=str(exc))
            return False, f"md-translator API 调用失败: {exc}", None
        except (OSError, RuntimeError, ValueError) as exc:
            self._write_log(log_path, error=str(exc))
            return False, str(exc), None

        if not translated_markdown.strip():
            return False, "md-translator 返回为空，请检查 translator.log。", None

        output_path.write_text(translated_markdown, encoding="utf-8")
        return True, "Markdown 翻译完成。", str(output_path)

    def _build_payload(self, markdown):
        translation_config = self.translation_config
        base_url = (
            config_manager.get_env(translation_config.get("base_url_env", "DEEPSEEK_BASE_URL"))
            or translation_config.get("api_base_url")
            or "https://api.deepseek.com/v1"
        ).rstrip("/")
        api_key = config_manager.get_env(translation_config.get("api_key_env", "DEEPSEEK_API_KEY"))
        model = (
            config_manager.get_env(translation_config.get("model_env", "DEEPSEEK_MODEL"))
            or translation_config.get("model")
            or "deepseek-chat"
        )

        return {
            "text": markdown,
            "sourceLanguage": translation_config.get("source_language", "en"),
            "targetLanguage": translation_config.get("target_language", "zh"),
            "translationMethod": translation_config.get("method", "llm"),
            "retryCount": translation_config.get("retry_count", 3),
            "retryTimeout": self.retry_timeout,
            "markdownOptions": translation_config.get("markdown_options", {}),
            "config": {
                "apiKey": api_key,
                "url": f"{base_url}/chat/completions",
                "model": model,
                "batchSize": self.batch_size,
            },
        }

    def _translate_markdown(self, markdown, run_root, log_path, start_info):
        chunks = self._split_markdown_into_chunks(markdown)
        chunks_dir = run_root / "translation_chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        self._write_log(
            log_path,
            start_info=start_info,
            payload={
                "mode": "chunked",
                "chunkCount": len(chunks),
                "chunkCharLimit": self.chunk_char_limit,
                "batchSize": self.batch_size,
                "retryTimeout": self.retry_timeout,
                "chunksDir": str(chunks_dir),
            },
        )

        translated_chunks = []
        for index, chunk in enumerate(chunks, start=1):
            chunk_name = f"chunk-{index:04d}"
            source_chunk_path = chunks_dir / f"{chunk_name}.src.md"
            translated_chunk_path = chunks_dir / f"{chunk_name}.zh.md"

            if not source_chunk_path.exists():
                source_chunk_path.write_text(chunk, encoding="utf-8")

            if translated_chunk_path.exists():
                cached = translated_chunk_path.read_text(encoding="utf-8")
                if cached.strip():
                    translated_chunks.append(cached)
                    self._append_log(
                        log_path,
                        f"[chunk {index}/{len(chunks)}]\nreused {translated_chunk_path}\n",
                    )
                    continue

            payload = self._build_payload(chunk)
            self._append_log(
                log_path,
                "\n".join(
                    [
                        f"[chunk {index}/{len(chunks)} start]",
                        json.dumps(
                            {
                                "source": str(source_chunk_path),
                                "target": str(translated_chunk_path),
                                "chars": len(chunk),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "",
                    ]
                ),
            )
            response = self._local_request(
                "post",
                self.api_url,
                json=payload,
                timeout=self.request_timeout,
            )

            try:
                data = response.json()
            except ValueError:
                data = {
                    "success": False,
                    "error": response.text.strip() or f"HTTP {response.status_code}",
                }

            self._append_log(
                log_path,
                "\n".join(
                    [
                        f"[chunk {index}/{len(chunks)}]",
                        json.dumps(
                            {
                                "source": str(source_chunk_path),
                                "target": str(translated_chunk_path),
                                "chars": len(chunk),
                                "status_code": response.status_code,
                                "success": data.get("success", False),
                                "error": data.get("error"),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "",
                    ]
                ),
            )

            translated_text = data.get("translatedText", "")
            if response.status_code >= 400 or not data.get("success"):
                raise RuntimeError(f"md-translator 第 {index}/{len(chunks)} 块翻译失败: {data.get('error', '未知错误')}")
            if not translated_text.strip():
                raise RuntimeError(f"md-translator 第 {index}/{len(chunks)} 块返回为空。")

            translated_chunk_path.write_text(translated_text, encoding="utf-8")
            translated_chunks.append(translated_text)

        return "".join(translated_chunks)

    def _split_markdown_into_chunks(self, markdown):
        blocks = self._split_markdown_into_blocks(markdown)
        chunks = []
        current_blocks = []
        current_length = 0

        for block in blocks:
            oversized_parts = self._split_oversized_block(block)
            for part in oversized_parts:
                part_length = len(part)
                if current_blocks and current_length + part_length > self.chunk_char_limit:
                    chunks.append("".join(current_blocks))
                    current_blocks = []
                    current_length = 0

                current_blocks.append(part)
                current_length += part_length

        if current_blocks:
            chunks.append("".join(current_blocks))

        return chunks

    def _split_markdown_into_blocks(self, markdown):
        lines = markdown.splitlines(keepends=True)
        blocks = []
        current = []
        in_fence = False
        fence_marker = None

        for line in lines:
            stripped = line.lstrip()
            marker = None
            if stripped.startswith("```"):
                marker = "```"
            elif stripped.startswith("~~~"):
                marker = "~~~"

            if marker:
                if not in_fence and current:
                    blocks.append("".join(current))
                    current = []
                current.append(line)
                if in_fence and marker == fence_marker:
                    in_fence = False
                    fence_marker = None
                    blocks.append("".join(current))
                    current = []
                else:
                    in_fence = True
                    fence_marker = marker
                continue

            if in_fence:
                current.append(line)
                continue

            if stripped.startswith("#") and current:
                blocks.append("".join(current))
                current = []

            current.append(line)
            if line.strip() == "":
                blocks.append("".join(current))
                current = []

        if current:
            blocks.append("".join(current))

        return [block for block in blocks if block]

    def _split_oversized_block(self, block):
        if len(block) <= self.chunk_char_limit:
            return [block]

        pieces = []
        for line in block.splitlines(keepends=True):
            if len(line) <= self.chunk_char_limit:
                pieces.append(line)
                continue

            pieces.extend(self._split_long_line(line))

        merged = []
        current = ""
        for piece in pieces:
            if current and len(current) + len(piece) > self.chunk_char_limit:
                merged.append(current)
                current = piece
            else:
                current += piece
        if current:
            merged.append(current)
        return merged

    def _split_long_line(self, line):
        chunks = []
        remaining = line

        while len(remaining) > self.chunk_char_limit:
            split_at = self._find_split_index(remaining)
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip()

        if remaining:
            chunks.append(remaining)
        return chunks

    def _find_split_index(self, text):
        limit = min(len(text), self.chunk_char_limit)
        search_window = text[:limit]

        for pattern in (r"\.\s+", r"。\s*", r";\s+", r"，\s*", r",\s+", r"\s+"):
            matches = list(re.finditer(pattern, search_window))
            if matches:
                candidate = matches[-1].end()
                if candidate > max(200, limit // 2):
                    return candidate

        return limit

    def _ensure_service(self, run_root, log_path):
        if self._is_service_ready():
            return {
                "started": False,
                "api_url": self.api_url,
            }

        if not self.translation_config.get("auto_start", True):
            raise RuntimeError("md-translator 服务未启动，请先手动启动本地服务。")
        if not self.node_command:
            raise RuntimeError("未找到 Node.js 命令，无法自动启动 md-translator 服务。")
        if not self.project_dir or not self.project_dir.exists():
            raise RuntimeError("未找到 md-translator 项目目录，无法自动启动服务。")
        if not self.standalone_entry or not self.standalone_entry.exists():
            raise RuntimeError("未找到 md-translator 的 standalone 服务入口，请先执行构建。")

        logs_dir = run_root / "logs"
        server_out = logs_dir / "md-translator-server.out.log"
        server_err = logs_dir / "md-translator-server.err.log"
        logs_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["LOCAL_API_SERVER"] = "true"
        env["PORT"] = str(self.port)
        env["HOSTNAME"] = self.host

        translation_config = self.translation_config
        api_key_env = translation_config.get("api_key_env", "DEEPSEEK_API_KEY")
        base_url_env = translation_config.get("base_url_env", "DEEPSEEK_BASE_URL")
        model_env = translation_config.get("model_env", "DEEPSEEK_MODEL")
        api_key = config_manager.get_env(api_key_env)
        base_url = config_manager.get_env(base_url_env) or translation_config.get("api_base_url")
        model = config_manager.get_env(model_env) or translation_config.get("model")

        if api_key:
            env[api_key_env] = api_key
        if base_url:
            env[base_url_env] = base_url
        if model:
            env[model_env] = model

        stdout_handle = server_out.open("a", encoding="utf-8")
        stderr_handle = server_err.open("a", encoding="utf-8")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(
                [self.node_command, str(self.standalone_entry)],
                cwd=self.project_dir,
                env=env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                creationflags=creationflags,
            )
        finally:
            stdout_handle.close()
            stderr_handle.close()

        deadline = time.time() + self.start_timeout
        while time.time() < deadline:
            if process.poll() is not None:
                break
            if self._is_service_ready():
                return {
                    "started": True,
                    "pid": process.pid,
                    "api_url": self.api_url,
                    "server_out": str(server_out),
                    "server_err": str(server_err),
                }
            time.sleep(1)

        if self._is_service_ready():
            return {
                "started": True,
                "pid": process.pid,
                "api_url": self.api_url,
                "server_out": str(server_out),
                "server_err": str(server_err),
            }

        out_text = server_out.read_text(encoding="utf-8") if server_out.exists() else ""
        err_text = server_err.read_text(encoding="utf-8") if server_err.exists() else ""
        details = err_text.strip() or out_text.strip() or "服务未在预期时间内启动。"
        raise RuntimeError(f"md-translator 服务启动失败: {details}")

    def _is_service_ready(self):
        try:
            response = self._local_request("get", f"http://{self.host}:{self.port}/en", timeout=3)
            return response.ok
        except requests.RequestException:
            return False

    def _local_request(self, method, url, **kwargs):
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()

        # Never send localhost traffic through system proxies.
        if hostname in {"127.0.0.1", "localhost", self.host.lower()}:
            with requests.Session() as session:
                session.trust_env = False
                return session.request(method, url, **kwargs)

        return requests.request(method, url, **kwargs)

    def _write_log(self, log_path, start_info=None, payload=None, response_body=None, status_code=None, error=None):
        if not log_path:
            return

        log_path.parent.mkdir(parents=True, exist_ok=True)
        parts = []
        if start_info:
            parts.extend(
                [
                    "[service]",
                    json.dumps(start_info, ensure_ascii=False, indent=2),
                ]
            )
        if payload:
            safe_payload = dict(payload)
            safe_config = dict(safe_payload.get("config", {}))
            if safe_config.get("apiKey"):
                safe_config["apiKey"] = "***"
            safe_payload["config"] = safe_config
            parts.extend(
                [
                    "",
                    "[request]",
                    json.dumps(safe_payload, ensure_ascii=False, indent=2),
                ]
            )
        if status_code is not None:
            parts.extend(
                [
                    "",
                    "[response_status]",
                    str(status_code),
                ]
            )
        if response_body is not None:
            parts.extend(
                [
                    "",
                    "[response_body]",
                    json.dumps(response_body, ensure_ascii=False, indent=2),
                ]
            )
        if error:
            parts.extend(
                [
                    "",
                    "[error]",
                    str(error),
                ]
            )

        log_path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")

    def _append_log(self, log_path, text):
        if not log_path:
            return

        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(text.rstrip() + "\n")


translator = Translator()
