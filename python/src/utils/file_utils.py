"""
File utility functions
"""

import os
from typing import List, Dict
from datetime import datetime


def sanitize_filename(text: str) -> str:
    """Sanitize text for use in filename."""
    import re
    # Remove or replace invalid filename characters
    text = re.sub(r'[<>:"/\\|?*]', '_', text)
    # Replace spaces with underscores
    text = text.replace(' ', '_')
    # Remove multiple underscores
    text = re.sub(r'_+', '_', text)
    # Remove leading/trailing underscores
    text = text.strip('_')
    return text


def list_images_in_directory(directory: str) -> List[Dict]:
    """List all image files in a directory."""
    images = []
    if not os.path.exists(directory):
        return images
    
    valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
    scanner_dir_abs = os.path.abspath(directory)
    
    for filename in sorted(os.listdir(directory)):
        file_path = os.path.join(scanner_dir_abs, filename)
        if os.path.isfile(file_path) and filename.lower().endswith(valid_extensions):
            file_time = os.path.getmtime(file_path)
            images.append({
                'filename': filename,
                'path': file_path,
                'created_at': datetime.fromtimestamp(file_time).isoformat()
            })
    
    # Sort by creation time (oldest first)
    images.sort(key=lambda x: x['created_at'])
    return images


def list_pdfs_in_directory(directory: str) -> List[Dict]:
    """List all PDF files in a directory."""
    pdfs = []
    if not os.path.exists(directory):
        return pdfs
    
    output_dir_abs = os.path.abspath(directory)
    for filename in sorted(os.listdir(directory), reverse=True):
        if filename.lower().endswith('.pdf'):
            file_path = os.path.join(output_dir_abs, filename)
            file_size = os.path.getsize(file_path)
            file_time = os.path.getmtime(file_path)
            pdfs.append({
                'filename': filename,
                'path': file_path,
                'size': file_size,
                'size_mb': round(file_size / (1024 * 1024), 2),
                'created_at': datetime.fromtimestamp(file_time).isoformat()
            })
    
    return pdfs


def generate_answer_copy_id() -> str:
    """Generate unique answer copy ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"AC_{timestamp}"
