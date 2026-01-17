"""SuckCode image support - Load images for multimodal LLMs via OpenRouter."""

import base64
import mimetypes
from pathlib import Path
from typing import Optional, Union
import httpx

SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# ═══════════════════════════════════════════════════════════════════════════════
# Image Loading
# ═══════════════════════════════════════════════════════════════════════════════

def load_image(path: Union[str, Path]) -> Optional[dict]:
    """Load an image from file path, return OpenRouter-compatible format."""
    path = Path(path)
    
    if not path.exists() or path.suffix.lower() not in SUPPORTED_FORMATS:
        return None
    
    try:
        data = path.read_bytes()
        encoded = base64.b64encode(data).decode("utf-8")
        media_type = mimetypes.guess_type(str(path))[0] or "image/png"
        
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{encoded}"}
        }
    except Exception:
        return None

def load_image_from_url(url: str) -> Optional[dict]:
    """Load an image from URL, return OpenRouter-compatible format."""
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        
        content_type = resp.headers.get("content-type", "image/png").split(";")[0]
        encoded = base64.b64encode(resp.content).decode("utf-8")
        
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{content_type};base64,{encoded}"}
        }
    except Exception:
        return None

def load_image_from_clipboard() -> Optional[dict]:
    """Load image from clipboard (requires PIL)."""
    try:
        from PIL import ImageGrab
        import io
        
        img = ImageGrab.grabclipboard()
        if img is None:
            return None
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{encoded}"}
        }
    except:
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# Image Detection in Messages
# ═══════════════════════════════════════════════════════════════════════════════

def extract_images_from_text(text: str) -> list[dict]:
    """Extract and load images referenced in text."""
    import re
    images = []
    
    # Match file paths with image extensions
    pattern = r'(?:^|\s)["\'"]?([^\s"\']+\.(?:png|jpg|jpeg|gif|webp|bmp))["\'"]?'
    for match in re.finditer(pattern, text, re.IGNORECASE):
        path = match.group(1)
        img = load_image(path)
        if img:
            images.append(img)
        elif path.startswith(("http://", "https://")):
            img = load_image_from_url(path)
            if img:
                images.append(img)
    
    # Match [image: path] syntax
    for match in re.finditer(r'\[image:\s*([^\]]+)\]', text, re.IGNORECASE):
        path = match.group(1).strip()
        img = load_image(path) or load_image_from_url(path)
        if img:
            images.append(img)
    
    return images

def create_message_with_images(text: str, images: list[dict]) -> dict:
    """Create a user message with text and images."""
    if not images:
        return {"role": "user", "content": text}
    
    content = [{"type": "text", "text": text}]
    content.extend(images)
    return {"role": "user", "content": content}

def process_message_with_images(text: str, model: str = None) -> tuple[str, list[dict]]:
    """Process message, extracting any images. Returns (text, images)."""
    images = extract_images_from_text(text)
    return text, images

# ═══════════════════════════════════════════════════════════════════════════════
# Screenshot (requires PIL)
# ═══════════════════════════════════════════════════════════════════════════════

def take_screenshot() -> Optional[dict]:
    """Take a screenshot, return OpenRouter-compatible format."""
    try:
        from PIL import ImageGrab
        import io
        
        img = ImageGrab.grab()
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{encoded}"}
        }
    except:
        return None

def get_image_info(path: str) -> Optional[dict]:
    """Get image file info."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            return {"path": path, "width": img.width, "height": img.height, "format": img.format}
    except:
        p = Path(path)
        if p.exists():
            return {"path": path, "size_bytes": p.stat().st_size}
        return None

# For backwards compatibility
def is_vision_model(model: str) -> bool:
    """Most modern models support images. Always returns True."""
    return True
