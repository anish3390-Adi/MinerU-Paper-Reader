from pathlib import Path

import streamlit as st

from utils.config_manager import ConfigError, config_manager
from utils.error_handler import error_handler
from utils.image_processor import image_processor
from utils.pdf_processor import pdf_processor
from utils.translator import translator


st.set_page_config(page_title="论文 Markdown 双语转换器", layout="wide")
st.title("英文论文 PDF -> 中文 Markdown")


def sync_runtime_mode_override():
    default_mode = config_manager.get_env("MINERU_MODE") or config_manager.get("tools.mineru_mode", "cloud_api")
    selected_mode = st.session_state.get("mineru_mode_selector", default_mode)
    config_manager.set_runtime_override("MINERU_MODE", selected_mode)


def render_runtime_panel():
    with st.sidebar:
        st.header("运行环境")

        default_mode = config_manager.get_env("MINERU_MODE") or config_manager.get("tools.mineru_mode", "cloud_api")
        if "mineru_mode_selector" not in st.session_state:
            st.session_state["mineru_mode_selector"] = default_mode

        st.radio(
            "MinerU 模式",
            options=["cloud_api", "cli"],
            key="mineru_mode_selector",
            horizontal=True,
            help="这是当前页面会话级切换，不会自动写回 .env。",
        )

        sync_runtime_mode_override()
        summary = config_manager.get_runtime_summary()
        issues = config_manager.get_runtime_issues()

        st.caption(f"当前模式: `{summary['mineru_mode']}`")
        st.caption(f"默认来源: `{default_mode}`")

        if summary["mineru_mode"] == "cloud_api":
            st.caption(f"MinerU 云 API: `{summary['mineru_api_base_url']}`")
            st.caption(f"MinerU 模型版本: `{summary['mineru_model_version']}`")
        else:
            st.caption(f"MinerU 命令: `{summary['mineru_command']}`")
            st.caption(f"MinerU 后端: `{summary['mineru_backend']}`")
            st.caption(f"MinerU Server URL: `{summary['mineru_server_url']}`")
            st.caption(f"MinerU API URL: `{summary['mineru_api_url']}`")

        st.caption(f"md-translator API: `{summary['translator_api_url']}`")
        st.caption(f"md-translator 目录: `{summary['translator_project_dir']}`")
        st.caption(f"Node.js 命令: `{summary['node_command']}`")
        st.caption(f"DeepSeek 模型: `{summary['deepseek_model']}`")
        st.caption(f"DeepSeek 地址: `{summary['deepseek_base_url']}`")

        if issues:
            st.error("\n".join(issues))
        else:
            st.success("运行前检查通过")

    if issues:
        st.error("运行前检查未通过，请先修复侧边栏中的环境问题。")
        st.stop()


def process_pdf(uploaded_file, progress_bar):
    workspace = pdf_processor.create_run_workspace(uploaded_file.name)
    pdf_path = workspace["input_dir"] / "paper.pdf"
    output_dir = workspace["output_dir"]
    logs_dir = workspace["logs_dir"]
    runtime_dir = workspace["runtime_dir"]
    mineru_log_path = logs_dir / "mineru.log"
    translator_log_path = logs_dir / "translator.log"

    try:
        pdf_path.write_bytes(uploaded_file.getbuffer())

        progress_bar.progress(10, text="1/3 已保存上传的 PDF，开始调用 MinerU")
        success, message, origin_md_path = pdf_processor.process(
            pdf_path,
            output_dir,
            runtime_temp_dir=runtime_dir,
            log_path=mineru_log_path,
        )
        if not success:
            return False, None, None, message, None

        progress_bar.progress(55, text="2/3 MinerU 已完成，开始调用 md-translator")
        zh_md_path = output_dir / config_manager.get("translation.output_filename", "zh.md")
        success, message, translated_path = translator.translate(
            origin_md_path,
            zh_md_path,
            run_root=workspace["run_root"],
            log_path=translator_log_path,
        )
        if not success:
            return False, None, None, message, None

        progress_bar.progress(85, text="3/3 翻译完成，开始渲染双语结果")
        english_raw = Path(origin_md_path).read_text(encoding="utf-8")
        chinese_raw = Path(translated_path).read_text(encoding="utf-8")

        english_md = image_processor.embed_images_in_md(english_raw, origin_md_path)
        chinese_md = image_processor.embed_images_in_md(chinese_raw, translated_path)

        artifacts = {
            "run_root": str(workspace["run_root"]),
            "input_pdf_path": str(pdf_path),
            "origin_md_path": str(origin_md_path),
            "zh_md_path": str(translated_path),
            "mineru_log_path": str(mineru_log_path),
            "translator_log_path": str(translator_log_path),
            "origin_raw": english_raw,
            "zh_raw": chinese_raw,
            "mineru_log_raw": mineru_log_path.read_text(encoding="utf-8") if mineru_log_path.exists() else "",
            "translator_log_raw": translator_log_path.read_text(encoding="utf-8")
            if translator_log_path.exists()
            else "",
        }
        progress_bar.progress(100, text="处理完成")
        return True, english_md, chinese_md, "处理成功", artifacts
    except Exception as exc:
        error_message = error_handler.handle_error(exc, "处理 PDF 时发生错误")
        return False, None, None, error_message, None


def render_downloads(artifacts):
    st.subheader("下载结果")
    download_col_1, download_col_2, download_col_3, download_col_4 = st.columns(4)

    with download_col_1:
        st.download_button(
            label="下载英文 Markdown",
            data=artifacts["origin_raw"],
            file_name="origin.md",
            mime="text/markdown",
        )

    with download_col_2:
        st.download_button(
            label="下载中文 Markdown",
            data=artifacts["zh_raw"],
            file_name="zh.md",
            mime="text/markdown",
        )

    with download_col_3:
        st.download_button(
            label="下载 mineru.log",
            data=artifacts["mineru_log_raw"],
            file_name="mineru.log",
            mime="text/plain",
        )

    with download_col_4:
        st.download_button(
            label="下载 translator.log",
            data=artifacts["translator_log_raw"],
            file_name="translator.log",
            mime="text/plain",
        )


def render_artifacts(artifacts):
    st.subheader("运行产物")
    st.caption(f"运行目录: `{artifacts['run_root']}`")
    st.caption(f"输入 PDF: `{artifacts['input_pdf_path']}`")
    st.caption(f"英文 Markdown: `{artifacts['origin_md_path']}`")
    st.caption(f"中文 Markdown: `{artifacts['zh_md_path']}`")
    st.caption(f"MinerU 日志: `{artifacts['mineru_log_path']}`")
    st.caption(f"md-translator 日志: `{artifacts['translator_log_path']}`")


def main():
    try:
        config_manager.validate_runtime()
    except ConfigError:
        render_runtime_panel()
        return

    render_runtime_panel()

    uploaded_file = st.file_uploader("请上传英文论文 PDF", type=["pdf"])
    if uploaded_file is None:
        st.info("上传 PDF 后会自动执行 MinerU 解析和 md-translator 翻译。")
        return

    max_file_size = config_manager.get("app.max_file_size", 50) * 1024 * 1024
    if uploaded_file.size > max_file_size:
        st.error(f"文件大小超过限制（{max_file_size / 1024 / 1024:.1f} MB）。")
        return

    progress_bar = st.progress(0, text="准备开始处理")
    success, english_md, chinese_md, message, artifacts = process_pdf(uploaded_file, progress_bar)

    if not success:
        st.error(message)
        return

    st.success(message)
    render_artifacts(artifacts)
    st.divider()
    render_downloads(artifacts)
    st.divider()

    col_en, col_zh = st.columns(2)
    with col_en:
        st.subheader("英文原文")
        st.markdown(english_md, unsafe_allow_html=True)

    with col_zh:
        st.subheader("中文译文")
        st.markdown(chinese_md, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
