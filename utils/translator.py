import json
import os
import subprocess
import time
from pathlib import Path

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
        self.request_timeout = self.translation_config.get("request_timeout", 1800)
        self.start_timeout = self.translation_config.get("start_timeout", 30)
        self.host = self.translation_config.get("host", "127.0.0.1")
        self.port = config_manager.get_translation_port()

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
            payload = self._build_payload(markdown)
            response = requests.post(
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
            self._write_log(
                log_path,
                start_info=start_info,
                payload=payload,
                response_body=data,
                status_code=response.status_code,
            )
        except requests.RequestException as exc:
            self._write_log(log_path, error=str(exc))
            return False, f"md-translator API 调用失败: {exc}", None
        except (OSError, RuntimeError, ValueError) as exc:
            self._write_log(log_path, error=str(exc))
            return False, str(exc), None

        translated_markdown = data.get("translatedText", "")
        if response.status_code >= 400 or not data.get("success"):
            return False, f"md-translator 翻译失败: {data.get('error', '未知错误')}", None
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
            "retryTimeout": translation_config.get("retry_timeout", 60),
            "markdownOptions": translation_config.get("markdown_options", {}),
            "config": {
                "apiKey": api_key,
                "url": f"{base_url}/chat/completions",
                "model": model,
            },
        }

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
            response = requests.get(f"http://{self.host}:{self.port}/en", timeout=3)
            return response.ok
        except requests.RequestException:
            return False

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


translator = Translator()
