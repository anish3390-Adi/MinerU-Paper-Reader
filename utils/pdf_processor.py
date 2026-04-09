import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from utils.config_manager import config_manager


class PDFProcessor:
    """Runs MinerU through either the official cloud API or the local CLI."""

    TERMINAL_STATES = {"done", "failed"}

    def __init__(self):
        self.mineru_command = config_manager.get_tool_command("mineru")
        self.default_runs_dir = config_manager.get_path("paths.runs_dir")
        self.temp_root = config_manager.get_path("paths.temp_dir")
        self.timeout = config_manager.get("tools.mineru_timeout", 1800)

    def create_run_workspace(self, original_filename):
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(original_filename).stem).strip("-")
        safe_name = safe_name or "paper"
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_root = self.default_runs_dir / f"{run_id}-{safe_name}"
        input_dir = run_root / "input"
        output_dir = run_root / "output"
        logs_dir = run_root / "logs"
        runtime_dir = run_root / "runtime"

        input_dir.mkdir(parents=True, exist_ok=False)
        output_dir.mkdir(parents=True, exist_ok=False)
        logs_dir.mkdir(parents=True, exist_ok=False)
        runtime_dir.mkdir(parents=True, exist_ok=False)

        return {
            "run_root": run_root,
            "input_dir": input_dir,
            "output_dir": output_dir,
            "logs_dir": logs_dir,
            "runtime_dir": runtime_dir,
        }

    def process(self, pdf_path, output_dir, runtime_temp_dir=None, log_path=None):
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        runtime_temp_dir = Path(runtime_temp_dir) if runtime_temp_dir else self.temp_root / "mineru-runtime"
        log_path = Path(log_path) if log_path else None

        if not pdf_path.exists():
            return False, f"PDF 文件不存在: {pdf_path}", None

        output_dir.mkdir(parents=True, exist_ok=True)
        self._clear_directory(output_dir)

        if config_manager.is_mineru_cloud_mode():
            return self._process_via_cloud_api(pdf_path, output_dir, log_path)

        return self._process_via_cli(pdf_path, output_dir, runtime_temp_dir, log_path)

    def _process_via_cloud_api(self, pdf_path, output_dir, log_path):
        api_base_url = config_manager.get_mineru_api_base_url().rstrip("/")
        api_key = config_manager.get_mineru_api_key()
        model_version = config_manager.get_mineru_model_version()
        language = config_manager.get_mineru_language()
        enable_table = config_manager.get_mineru_enable_table()
        enable_formula = config_manager.get_mineru_enable_formula()
        is_ocr = config_manager.get_mineru_is_ocr()
        poll_interval = config_manager.get_mineru_poll_interval()

        if not api_key:
            return False, "当前处于 MinerU 官方云 API 模式，但未配置 `MINERU_API_KEY`。", None

        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Accept": "*/*",
            }
        )

        log_data = {
            "mode": "cloud_api",
            "api_base_url": api_base_url,
            "model_version": model_version,
            "language": language,
            "enable_table": enable_table,
            "enable_formula": enable_formula,
            "is_ocr": is_ocr,
        }

        try:
            quota_response = session.get(f"{api_base_url}/quota", timeout=20)
            quota_payload = self._safe_json(quota_response)
            log_data["quota_status"] = quota_response.status_code
            log_data["quota_response"] = quota_payload

            create_payload = {
                "files": [
                    {
                        "name": pdf_path.name,
                        "data_id": pdf_path.stem,
                        "is_ocr": is_ocr,
                    }
                ],
                "language": language,
                "enable_table": enable_table,
                "enable_formula": enable_formula,
                "model_version": model_version,
            }
            log_data["create_payload"] = create_payload

            create_response = session.post(
                f"{api_base_url}/file-urls/batch",
                json=create_payload,
                timeout=30,
            )
            create_result = self._safe_json(create_response)
            log_data["create_status"] = create_response.status_code
            log_data["create_response"] = create_result

            if create_response.status_code != 200 or create_result.get("code") != 0:
                details = create_result.get("msg") or create_response.text.strip() or f"HTTP {create_response.status_code}"
                self._write_cloud_log(log_path, log_data)
                return False, f"申请 MinerU 上传地址失败: {details}", None

            batch_id = ((create_result.get("data") or {}).get("batch_id")) or ""
            file_urls = ((create_result.get("data") or {}).get("file_urls")) or []
            if not batch_id or not file_urls:
                self._write_cloud_log(log_path, log_data)
                return False, "MinerU 云 API 返回的 batch_id 或 file_urls 为空。", None

            upload_url = file_urls[0]
            upload_response, upload_attempts = self._upload_to_cloud(upload_url, pdf_path)
            log_data["batch_id"] = batch_id
            log_data["upload_status"] = upload_response.status_code
            log_data["upload_attempts"] = upload_attempts

            if upload_response.status_code != 200:
                self._write_cloud_log(log_path, log_data)
                return False, f"上传 PDF 到 MinerU 云端失败: HTTP {upload_response.status_code}", None

            deadline = time.time() + self.timeout
            latest_result = None
            poll_history = []
            while time.time() < deadline:
                result_response = session.get(
                    f"{api_base_url}/extract-results/batch/{batch_id}",
                    timeout=30,
                )
                result_payload = self._safe_json(result_response)
                poll_history.append(
                    {
                        "status": result_response.status_code,
                        "response": result_payload,
                    }
                )

                if result_response.status_code != 200 or result_payload.get("code") != 0:
                    details = result_payload.get("msg") or result_response.text.strip() or f"HTTP {result_response.status_code}"
                    log_data["poll_history"] = poll_history
                    self._write_cloud_log(log_path, log_data)
                    return False, f"查询 MinerU 云任务状态失败: {details}", None

                extract_results = ((result_payload.get("data") or {}).get("extract_result")) or []
                if extract_results:
                    latest_result = extract_results[0]
                    state = latest_result.get("state")
                    if state in self.TERMINAL_STATES:
                        break

                time.sleep(poll_interval)

            log_data["poll_history"] = poll_history
            log_data["final_result"] = latest_result

            if latest_result is None:
                self._write_cloud_log(log_path, log_data)
                return False, "MinerU 云任务已提交，但未查询到任务结果。", None

            state = latest_result.get("state")
            if state == "failed":
                err_msg = latest_result.get("err_msg") or "未知错误"
                self._write_cloud_log(log_path, log_data)
                return False, f"MinerU 云解析失败: {err_msg}", None

            if state != "done":
                self._write_cloud_log(log_path, log_data)
                return False, f"MinerU 云任务超时，最后状态为 `{state}`。", None

            full_zip_url = latest_result.get("full_zip_url")
            if not full_zip_url:
                self._write_cloud_log(log_path, log_data)
                return False, "MinerU 云任务已完成，但结果中没有 `full_zip_url`。", None

            zip_path = output_dir / "mineru-result.zip"
            download_response, download_attempts = self._download_from_cloud(full_zip_url)
            log_data["download_status"] = download_response.status_code
            log_data["download_attempts"] = download_attempts
            log_data["full_zip_url"] = full_zip_url

            if download_response.status_code != 200:
                self._write_cloud_log(log_path, log_data)
                return False, f"下载 MinerU 结果压缩包失败: HTTP {download_response.status_code}", None

            zip_path.write_bytes(download_response.content)
            with zipfile.ZipFile(zip_path, "r") as archive:
                archive.extractall(output_dir)
            zip_path.unlink(missing_ok=True)

            origin_md_path = self._find_origin_markdown(output_dir)
            self._write_cloud_log(log_path, log_data)

            if not origin_md_path:
                return False, "MinerU 云任务已完成，但输出目录中没有找到可用的 Markdown 文件。", None

            return True, "MinerU 云解析完成。", str(origin_md_path)
        except requests.RequestException as exc:
            log_data["error"] = str(exc)
            self._write_cloud_log(log_path, log_data)
            return False, f"调用 MinerU 官方云 API 失败: {exc}", None
        except (OSError, zipfile.BadZipFile) as exc:
            log_data["error"] = str(exc)
            self._write_cloud_log(log_path, log_data)
            return False, f"处理 MinerU 云结果失败: {exc}", None

    def _process_via_cli(self, pdf_path, output_dir, runtime_temp_dir, log_path):
        if not self.mineru_command:
            return False, "当前处于本地 CLI 模式，但未找到 `mineru` 命令。", None

        backend = config_manager.get_mineru_backend()
        server_url = config_manager.get_mineru_server_url()
        api_url = config_manager.get_mineru_api_url()
        parse_method = config_manager.get_mineru_parse_method()
        lang = config_manager.get_mineru_lang()

        cmd = [
            self.mineru_command,
            "-p",
            str(pdf_path),
            "-o",
            str(output_dir),
        ]

        if api_url:
            cmd.extend(["--api-url", api_url])
        if backend:
            cmd.extend(["-b", backend])
        if config_manager.backend_requires_server_url(backend) and server_url:
            cmd.extend(["-u", server_url])
        if config_manager.backend_supports_parse_method(backend) and parse_method:
            cmd.extend(["-m", parse_method])
        if config_manager.backend_supports_parse_method(backend) and lang:
            cmd.extend(["-l", lang])

        try:
            runtime_temp_dir.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env["TMP"] = str(runtime_temp_dir)
            env["TEMP"] = str(runtime_temp_dir)
            env["TMPDIR"] = str(runtime_temp_dir)
            self._configure_mineru_environment(env, backend)
            self._ensure_localhost_bypass(env)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=self.timeout,
            )
            self._write_cli_log(log_path, cmd, result.stdout, result.stderr, result.returncode)
        except subprocess.TimeoutExpired as exc:
            self._write_cli_log(log_path, cmd, exc.stdout, exc.stderr, None, error=str(exc))
            return False, f"MinerU 本地 CLI 执行超时，超过 {self.timeout} 秒。", None
        except OSError as exc:
            self._write_cli_log(log_path, cmd, "", "", None, error=str(exc))
            return False, f"MinerU 本地 CLI 启动失败: {exc}", None

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            details = stderr or stdout or "MinerU 返回了非 0 状态码。"
            return False, f"MinerU 本地 CLI 解析失败: {details}", None

        origin_md_path = self._find_origin_markdown(output_dir)
        if not origin_md_path:
            return False, "MinerU 本地 CLI 执行完成，但输出目录中没有找到可用的 Markdown 文件。", None

        self._cleanup_runtime_dir(runtime_temp_dir)
        return True, "MinerU 本地 CLI 解析完成。", str(origin_md_path)

    def _upload_to_cloud(self, upload_url, pdf_path):
        attempts = []
        for trust_env in (True, False):
            attempt_name = "system_proxy" if trust_env else "direct_no_proxy"
            for retry_index in range(1, 3):
                try:
                    with pdf_path.open("rb") as handle:
                        with requests.Session() as upload_session:
                            upload_session.trust_env = trust_env
                            response = upload_session.put(
                                upload_url,
                                data=handle,
                                timeout=300,
                                headers={"Connection": "close"},
                            )
                    attempts.append(
                        {
                            "path": attempt_name,
                            "retry": retry_index,
                            "status": response.status_code,
                        }
                    )
                    return response, attempts
                except requests.RequestException as exc:
                    attempts.append(
                        {
                            "path": attempt_name,
                            "retry": retry_index,
                            "error": str(exc),
                        }
                    )
                    if trust_env is False or retry_index == 2:
                        last_exc = exc
                time.sleep(1)

        raise last_exc

    def _download_from_cloud(self, download_url):
        attempts = []
        for trust_env in (True, False):
            attempt_name = "system_proxy" if trust_env else "direct_no_proxy"
            for retry_index in range(1, 3):
                try:
                    with requests.Session() as download_session:
                        download_session.trust_env = trust_env
                        response = download_session.get(
                            download_url,
                            timeout=300,
                            headers={"Connection": "close"},
                        )
                    attempts.append(
                        {
                            "path": attempt_name,
                            "retry": retry_index,
                            "status": response.status_code,
                        }
                    )
                    return response, attempts
                except requests.RequestException as exc:
                    attempts.append(
                        {
                            "path": attempt_name,
                            "retry": retry_index,
                            "error": str(exc),
                        }
                    )
                    if trust_env is False or retry_index == 2:
                        last_exc = exc
                time.sleep(1)

        raise last_exc

    def _configure_mineru_environment(self, env, backend):
        model_source = config_manager.get_mineru_model_source()
        if model_source:
            env["MINERU_MODEL_SOURCE"] = model_source
            return

        if backend in {"pipeline", "vlm-auto-engine", "hybrid-auto-engine"}:
            env.setdefault("MINERU_MODEL_SOURCE", "local")

    def _find_origin_markdown(self, output_dir):
        full_md = sorted(output_dir.rglob("full.md"), key=lambda path: (len(path.parts), str(path)))
        if full_md:
            return full_md[0]

        preferred = sorted(output_dir.rglob("origin.md"), key=lambda path: (len(path.parts), str(path)))
        if preferred:
            return preferred[0]

        candidates = sorted(
            (path for path in output_dir.rglob("*.md") if path.name.lower() != "zh.md"),
            key=lambda path: (len(path.parts), str(path)),
        )
        return candidates[0] if candidates else None

    def _clear_directory(self, directory):
        for item in directory.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    def _cleanup_runtime_dir(self, directory):
        if not directory.exists():
            return

        try:
            shutil.rmtree(directory)
        except OSError:
            pass

    def _ensure_localhost_bypass(self, env):
        localhost_hosts = ["127.0.0.1", "localhost"]
        for key in ("NO_PROXY", "no_proxy"):
            existing = env.get(key, "")
            entries = [item.strip() for item in existing.split(",") if item.strip()]
            for host in localhost_hosts:
                if host not in entries:
                    entries.append(host)
            env[key] = ",".join(entries)

    def _safe_json(self, response):
        try:
            return response.json()
        except ValueError:
            return {"raw_text": response.text.strip()}

    def _write_cli_log(self, log_path, command, stdout, stderr, returncode, error=None):
        if not log_path:
            return

        log_path.parent.mkdir(parents=True, exist_ok=True)
        content = [
            "[mode]",
            "cli",
            "",
            "[command]",
            " ".join(command),
            "",
            "[returncode]",
            str(returncode if returncode is not None else "N/A"),
        ]
        if error:
            content.extend(["", "[error]", error])
        if stdout:
            content.extend(["", "[stdout]", stdout])
        if stderr:
            content.extend(["", "[stderr]", stderr])
        log_path.write_text("\n".join(content).strip() + "\n", encoding="utf-8")

    def _write_cloud_log(self, log_path, data):
        if not log_path:
            return

        safe_data = json.loads(json.dumps(data))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(safe_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


pdf_processor = PDFProcessor()
