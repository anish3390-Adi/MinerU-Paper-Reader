import base64
import mimetypes
import re
from pathlib import Path


class ImageProcessor:
    """Embeds local markdown images as data URLs for Streamlit rendering."""

    IMAGE_PATTERN = re.compile(r"!\[(.*?)\]\((.*?)\)")

    def embed_images_in_md(self, md_text, markdown_path):
        markdown_dir = Path(markdown_path).resolve().parent

        def replace_image(match):
            alt_text = match.group(1)
            raw_target = match.group(2).strip()

            if raw_target.startswith(("http://", "https://", "data:")):
                return match.group(0)

            image_path = self._resolve_image_path(markdown_dir, raw_target)
            if not image_path:
                return match.group(0)

            try:
                encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            except OSError:
                return match.group(0)

            mime_type, _ = mimetypes.guess_type(image_path.name)
            mime_type = mime_type or "application/octet-stream"
            return f"![{alt_text}](data:{mime_type};base64,{encoded})"

        return self.IMAGE_PATTERN.sub(replace_image, md_text)

    def _resolve_image_path(self, markdown_dir, raw_target):
        candidate = (markdown_dir / raw_target).resolve()
        if candidate.exists():
            return candidate

        fallback = (markdown_dir / "images" / Path(raw_target).name).resolve()
        if fallback.exists():
            return fallback

        return None


image_processor = ImageProcessor()
