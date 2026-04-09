import os
import shutil
from pathlib import Path

import yaml
from dotenv import dotenv_values, load_dotenv


class ConfigError(RuntimeError):
    """Raised when the runtime configuration is incomplete."""


class ConfigManager:
    """Loads project configuration, environment variables, and runtime overrides."""

    CLOUD_MODE = "cloud_api"
    CLI_MODE = "cli"
    HTTP_CLIENT_BACKENDS = {"vlm-http-client", "hybrid-http-client"}
    METHOD_AWARE_BACKENDS = {"pipeline", "hybrid-http-client", "hybrid-auto-engine"}

    def __init__(self, config_file="config.yaml"):
        self.config_file = Path(config_file).resolve()
        self.project_root = self.config_file.parent
        self.config = {}
        self.dotenv_vars = {}
        self.env_vars = {}
        self.runtime_overrides = {}
        self._load_config()
        self._load_env_vars()
        self.ensure_directories()

    def _load_config(self):
        try:
            with self.config_file.open("r", encoding="utf-8") as handle:
                self.config = yaml.safe_load(handle) or {}
        except FileNotFoundError:
            self._set_default_config()
        except yaml.YAMLError as exc:
            raise ConfigError(f"配置文件解析失败: {exc}") from exc

    def _load_env_vars(self):
        load_dotenv()
        env_file = self.config_file.parent / ".env"
        self.dotenv_vars = {
            key: value
            for key, value in dotenv_values(env_file).items()
            if value not in (None, "")
        }
        self.env_vars = {
            "DEEPSEEK_API_KEY": self._read_env_value("DEEPSEEK_API_KEY"),
            "DEEPSEEK_BASE_URL": self._read_env_value("DEEPSEEK_BASE_URL"),
            "DEEPSEEK_MODEL": self._read_env_value("DEEPSEEK_MODEL"),
            "MINERU_MODE": self._read_env_value("MINERU_MODE"),
            "MINERU_API_KEY": self._read_env_value("MINERU_API_KEY"),
            "MINERU_API_BASE_URL": self._read_env_value("MINERU_API_BASE_URL"),
            "MINERU_MODEL_VERSION": self._read_env_value("MINERU_MODEL_VERSION"),
            "MINERU_LANGUAGE": self._read_env_value("MINERU_LANGUAGE"),
            "MINERU_ENABLE_TABLE": self._read_env_value("MINERU_ENABLE_TABLE"),
            "MINERU_ENABLE_FORMULA": self._read_env_value("MINERU_ENABLE_FORMULA"),
            "MINERU_IS_OCR": self._read_env_value("MINERU_IS_OCR"),
            "MINERU_POLL_INTERVAL": self._read_env_value("MINERU_POLL_INTERVAL"),
            "MINERU_BIN": self._read_env_value("MINERU_BIN"),
            "MINERU_BACKEND": self._read_env_value("MINERU_BACKEND"),
            "MINERU_METHOD": self._read_env_value("MINERU_METHOD"),
            "MINERU_LANG": self._read_env_value("MINERU_LANG"),
            "MINERU_SERVER_URL": self._read_env_value("MINERU_SERVER_URL"),
            "MINERU_API_URL": self._read_env_value("MINERU_API_URL"),
            "MINERU_MODEL_SOURCE": self._read_env_value("MINERU_MODEL_SOURCE"),
            "NODE_BIN": self._read_env_value("NODE_BIN"),
            "MD_TRANSLATOR_DIR": self._read_env_value("MD_TRANSLATOR_DIR"),
            "MD_TRANSLATOR_PORT": self._read_env_value("MD_TRANSLATOR_PORT"),
            "LOG_LEVEL": self._read_env_value("LOG_LEVEL", "INFO"),
        }

    def _read_env_value(self, key, default=None):
        if key in self.dotenv_vars:
            return self.dotenv_vars[key]
        return os.getenv(key, default)

    def _set_default_config(self):
        self.config = {
            "tools": {
                "mineru_mode": "cloud_api",
                "mineru_api_base_url": "https://mineru.net/api/v4",
                "mineru_model_version": "vlm",
                "mineru_language": "en",
                "mineru_enable_table": True,
                "mineru_enable_formula": True,
                "mineru_is_ocr": False,
                "mineru_poll_interval": 5,
                "mineru": "mineru",
                "mineru_backend": "pipeline",
                "mineru_parse_method": "auto",
                "mineru_lang": "en",
                "mineru_server_url": "",
                "mineru_api_url": "",
                "mineru_timeout": 1800,
                "node": "node",
            },
            "translation": {
                "request_timeout": 1800,
                "output_filename": "zh.md",
                "api_key_env": "DEEPSEEK_API_KEY",
                "base_url_env": "DEEPSEEK_BASE_URL",
                "model_env": "DEEPSEEK_MODEL",
                "api_base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-chat",
                "method": "llm",
                "api_url": "http://127.0.0.1:3000/api/translate",
                "host": "127.0.0.1",
                "port": 3000,
                "auto_start": True,
                "start_timeout": 30,
                "retry_count": 3,
                "retry_timeout": 60,
                "project_dir": "./external/md-translator",
                "standalone_entry": ".next/standalone/server.js",
                "source_language": "en",
                "target_language": "zh",
                "markdown_options": {
                    "translateFrontmatter": False,
                    "translateMultilineCode": False,
                    "translateLatex": False,
                    "translateLinkText": True,
                },
            },
            "paths": {
                "temp_dir": "./temp",
                "runs_dir": "./temp/runs",
            },
            "app": {
                "max_file_size": 50,
            },
        }

    def ensure_directories(self):
        for key in ("paths.temp_dir", "paths.runs_dir"):
            self.get_path(key).mkdir(parents=True, exist_ok=True)

    def set_runtime_override(self, key, value):
        if value is None or value == "":
            self.runtime_overrides.pop(key, None)
        else:
            self.runtime_overrides[key] = value

    def clear_runtime_override(self, key):
        self.runtime_overrides.pop(key, None)

    def get_runtime_override(self, key):
        value = self.runtime_overrides.get(key)
        if isinstance(value, str):
            value = value.strip()
        return value or None

    def get(self, key, default=None):
        value = self.config
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def get_env(self, key, default=None):
        override = self.get_runtime_override(key)
        if override is not None:
            return override

        value = self.env_vars.get(key, default)
        if isinstance(value, str):
            value = value.strip()
        return value or default

    def get_bool_env(self, key, default=None):
        value = self.get_env(key)
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def get_path(self, key):
        raw_value = self.get(key)
        if raw_value is None:
            raise ConfigError(f"缺少路径配置: {key}")
        return self._resolve_path(raw_value)

    def get_translation_config(self):
        return self.get("translation", {})

    def get_tool_command(self, tool_name):
        if tool_name == "mineru":
            configured_name = self.get_env("MINERU_BIN") or self.get("tools.mineru")
            return self._resolve_command(configured_name)

        if tool_name == "node":
            configured_name = self.get_env("NODE_BIN") or self.get("tools.node")
            return self._resolve_command(configured_name)

        configured_name = self.get(f"tools.{tool_name}")
        return self._resolve_command(configured_name)

    def get_mineru_mode(self):
        return self.get_env("MINERU_MODE") or self.get("tools.mineru_mode", self.CLOUD_MODE)

    def is_mineru_cloud_mode(self):
        return self.get_mineru_mode() == self.CLOUD_MODE

    def get_mineru_api_key(self):
        return self.get_env("MINERU_API_KEY")

    def get_mineru_api_base_url(self):
        return self.get_env("MINERU_API_BASE_URL") or self.get("tools.mineru_api_base_url", "https://mineru.net/api/v4")

    def get_mineru_model_version(self):
        return self.get_env("MINERU_MODEL_VERSION") or self.get("tools.mineru_model_version", "vlm")

    def get_mineru_language(self):
        return self.get_env("MINERU_LANGUAGE") or self.get("tools.mineru_language", "en")

    def get_mineru_enable_table(self):
        configured = self.get_bool_env("MINERU_ENABLE_TABLE")
        return configured if configured is not None else self.get("tools.mineru_enable_table", True)

    def get_mineru_enable_formula(self):
        configured = self.get_bool_env("MINERU_ENABLE_FORMULA")
        return configured if configured is not None else self.get("tools.mineru_enable_formula", True)

    def get_mineru_is_ocr(self):
        configured = self.get_bool_env("MINERU_IS_OCR")
        return configured if configured is not None else self.get("tools.mineru_is_ocr", False)

    def get_mineru_poll_interval(self):
        raw_value = self.get_env("MINERU_POLL_INTERVAL") or self.get("tools.mineru_poll_interval", 5)
        return max(1, int(raw_value))

    def get_mineru_backend(self):
        return self.get_env("MINERU_BACKEND") or self.get("tools.mineru_backend", "pipeline")

    def get_mineru_parse_method(self):
        return self.get_env("MINERU_METHOD") or self.get("tools.mineru_parse_method", "auto")

    def get_mineru_lang(self):
        return self.get_env("MINERU_LANG") or self.get("tools.mineru_lang", "en")

    def get_mineru_server_url(self):
        return self.get_env("MINERU_SERVER_URL") or self.get("tools.mineru_server_url")

    def get_mineru_api_url(self):
        return self.get_env("MINERU_API_URL") or self.get("tools.mineru_api_url")

    def get_mineru_model_source(self):
        return self.get_env("MINERU_MODEL_SOURCE")

    def backend_requires_server_url(self, backend=None):
        backend = backend or self.get_mineru_backend()
        return backend in self.HTTP_CLIENT_BACKENDS

    def backend_supports_parse_method(self, backend=None):
        backend = backend or self.get_mineru_backend()
        return backend in self.METHOD_AWARE_BACKENDS

    def get_translation_project_dir(self):
        raw_value = self.get_env("MD_TRANSLATOR_DIR") or self.get("translation.project_dir")
        return self._resolve_path(raw_value) if raw_value else None

    def get_translation_port(self):
        raw_value = self.get_env("MD_TRANSLATOR_PORT") or self.get("translation.port", 3000)
        return int(raw_value)

    def get_translation_api_url(self):
        configured = self.get("translation.api_url")
        if configured:
            return configured

        host = self.get("translation.host", "127.0.0.1")
        port = self.get_translation_port()
        return f"http://{host}:{port}/api/translate"

    def get_translation_standalone_entry(self):
        project_dir = self.get_translation_project_dir()
        standalone_entry = self.get("translation.standalone_entry", ".next/standalone/server.js")
        if not project_dir:
            return None
        return (project_dir / standalone_entry).resolve()

    def _resolve_command(self, command_name):
        if not command_name:
            return None

        command_path = Path(command_name)
        if command_path.exists():
            return str(command_path.resolve())

        return shutil.which(command_name)

    def _resolve_path(self, raw_value):
        path = Path(raw_value).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def get_runtime_summary(self):
        translation_config = self.get_translation_config()
        project_dir = self.get_translation_project_dir()

        return {
            "mineru_mode": self.get_mineru_mode(),
            "mineru_command": self.get_tool_command("mineru") or "未找到",
            "mineru_api_base_url": self.get_mineru_api_base_url(),
            "mineru_model_version": self.get_mineru_model_version(),
            "mineru_backend": self.get_mineru_backend() or "未配置",
            "mineru_server_url": self.get_mineru_server_url() or "未配置",
            "mineru_api_url": self.get_mineru_api_url() or "未配置",
            "translator_api_url": self.get_translation_api_url(),
            "translator_project_dir": str(project_dir.resolve()) if project_dir else "未配置",
            "node_command": self.get_tool_command("node") or "未找到",
            "deepseek_model": self.get_env("DEEPSEEK_MODEL")
            or translation_config.get("model", "deepseek-chat"),
            "deepseek_base_url": self.get_env("DEEPSEEK_BASE_URL")
            or translation_config.get("api_base_url", "https://api.deepseek.com/v1"),
        }

    def get_runtime_issues(self):
        issues = []

        if self.is_mineru_cloud_mode():
            if not self.get_mineru_api_key():
                issues.append("当前 MinerU 处于官方云 API 模式，必须设置 `MINERU_API_KEY`。")
        else:
            if not self.get_tool_command("mineru"):
                issues.append(
                    "当前 MinerU 处于本地 CLI 模式，但未找到 `mineru` 命令。请安装 MinerU，或切回云 API 模式。"
                )

            backend = self.get_mineru_backend()
            if self.backend_requires_server_url(backend) and not self.get_mineru_server_url():
                issues.append(
                    f"当前 MinerU 后端 `{backend}` 需要设置 `MINERU_SERVER_URL`，用于指向 OpenAI 兼容的远程模型服务。"
                )

        if not self.get_tool_command("node"):
            issues.append("未找到 Node.js 命令。请确保 `node` 或配置的 `NODE_BIN` 可直接执行。")

        project_dir = self.get_translation_project_dir()
        if not project_dir:
            issues.append("未配置 md-translator 项目目录，请设置 `translation.project_dir` 或 `MD_TRANSLATOR_DIR`。")
        elif not project_dir.exists():
            issues.append(f"md-translator 项目目录不存在: {project_dir}")

        standalone_entry = self.get_translation_standalone_entry()
        if standalone_entry is None or not standalone_entry.exists():
            issues.append(
                "未找到 md-translator 的 `.next/standalone/server.js`。请先在 `external/md-translator` 下执行服务模式构建。"
            )

        api_key_env = self.get("translation.api_key_env", "DEEPSEEK_API_KEY")
        if not self.get_env(api_key_env):
            issues.append(f"未设置 `{api_key_env}`，翻译阶段无法调用 DeepSeek。")

        return issues

    def validate_runtime(self):
        issues = self.get_runtime_issues()
        if issues:
            raise ConfigError("\n".join(issues))


config_manager = ConfigManager()
