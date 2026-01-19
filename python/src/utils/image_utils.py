"""
Image utility functions
"""

import imagehash
from PIL import Image
from datetime import datetime


def extract_unique_id_from_image(image_path: str) -> str:
    """
    Extract unique ID from first page image.
    Uses image hash as unique identifier.
    """
    try:
        with Image.open(image_path) as img:
            # Generate perceptual hash
            phash = imagehash.phash(img)
            # Use first 8 characters of hash as unique ID
            unique_id = str(phash)[:8]
            return unique_id
    except Exception as e:
        print(f"Error extracting unique ID from image: {e}")
        # Fallback: use timestamp-based ID
        timestamp = datetime.now().strftime("%H%M%S")
        return timestamp


def generate_unique_id_from_fields(degree: str, subject: str, exam_date: str, college: str) -> str:
    """Generate unique ID from last 2 characters of each field."""
    unique_parts = []
    
    if degree:
        deg_part = degree[-2:].upper() if len(degree) >= 2 else degree.upper()
        unique_parts.append(deg_part)
    
    if subject:
        subj_part = subject[-2:].upper() if len(subject) >= 2 else subject.upper()
        unique_parts.append(subj_part)
    
    if exam_date:
        date_part = exam_date[-2:] if len(exam_date) >= 2 else exam_date
        unique_parts.append(date_part)
    
    if college:
        coll_part = college[-2:].upper() if len(college) >= 2 else college.upper()
        unique_parts.append(coll_part)
    
    if unique_parts:
        return ''.join(unique_parts)
    return None
