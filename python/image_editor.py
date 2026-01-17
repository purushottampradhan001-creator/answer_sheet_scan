"""
Image editing utilities for crop, rotate, brightness, contrast adjustments.
"""

from PIL import Image, ImageEnhance, ImageOps
import io
import base64
from typing import Tuple, Optional


def crop_image(image: Image.Image, x: int, y: int, width: int, height: int) -> Image.Image:
    """Crop image to specified coordinates."""
    return image.crop((x, y, x + width, y + height))


def rotate_image(image: Image.Image, angle: float) -> Image.Image:
    """Rotate image by specified angle (in degrees)."""
    if angle == 0:
        return image
    # Convert to positive angle
    angle = angle % 360
    return image.rotate(angle, expand=True, fillcolor='white')


def adjust_brightness(image: Image.Image, factor: float) -> Image.Image:
    """Adjust image brightness. Factor: 0.0 (black) to 2.0 (bright), 1.0 is original."""
    enhancer = ImageEnhance.Brightness(image)
    return enhancer.enhance(factor)


def adjust_contrast(image: Image.Image, factor: float) -> Image.Image:
    """Adjust image contrast. Factor: 0.0 (gray) to 2.0 (high contrast), 1.0 is original."""
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


def adjust_saturation(image: Image.Image, factor: float) -> Image.Image:
    """Adjust image saturation. Factor: 0.0 (grayscale) to 2.0 (vivid), 1.0 is original."""
    enhancer = ImageEnhance.Color(image)
    return enhancer.enhance(factor)


def apply_edits(image_path: str, edits: dict, output_path: Optional[str] = None) -> str:
    """
    Apply multiple edits to an image.
    
    Args:
        image_path: Path to input image
        edits: Dictionary with edit parameters:
            - crop: {'x': int, 'y': int, 'width': int, 'height': int}
            - rotate: float (degrees)
            - brightness: float (0.0-2.0)
            - contrast: float (0.0-2.0)
            - saturation: float (0.0-2.0)
        output_path: Optional output path. If None, overwrites input.
    
    Returns:
        Path to edited image
    """
    image = Image.open(image_path)
    
    # Convert to RGB if necessary
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Apply edits in order
    if 'crop' in edits:
        crop_params = edits['crop']
        image = crop_image(
            image,
            crop_params['x'],
            crop_params['y'],
            crop_params['width'],
            crop_params['height']
        )
    
    if 'rotate' in edits:
        image = rotate_image(image, edits['rotate'])
    
    if 'brightness' in edits:
        image = adjust_brightness(image, edits['brightness'])
    
    if 'contrast' in edits:
        image = adjust_contrast(image, edits['contrast'])
    
    if 'saturation' in edits:
        image = adjust_saturation(image, edits['saturation'])
    
    # Save
    if output_path is None:
        output_path = image_path
    
    image.save(output_path, quality=95, optimize=True)
    return output_path


def image_to_base64(image: Image.Image, format: str = 'JPEG') -> str:
    """Convert PIL Image to base64 string."""
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/{format.lower()};base64,{img_str}"


def base64_to_image(base64_str: str) -> Image.Image:
    """Convert base64 string to PIL Image."""
    # Remove data URL prefix if present
    if ',' in base64_str:
        base64_str = base64_str.split(',')[1]
    
    img_data = base64.b64decode(base64_str)
    return Image.open(io.BytesIO(img_data))
