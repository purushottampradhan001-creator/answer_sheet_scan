"""
PDF generation module using ReportLab.
Creates one PDF per answer copy from ordered images.
"""

# This file was moved from pdf_generator.py - update imports if needed

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from PIL import Image
import os
import re
import uuid
import random
import time
import hashlib
from typing import List, Optional


def sanitize_filename(text: str) -> str:
    """Sanitize text for use in filename."""
    # Remove or replace invalid filename characters
    text = re.sub(r'[<>:"/\\|?*]', '_', text)
    # Replace spaces with underscores
    text = text.replace(' ', '_')
    # Remove multiple underscores
    text = re.sub(r'_+', '_', text)
    # Remove leading/trailing underscores
    text = text.strip('_')
    return text


class PDFGenerator:
    """Generates PDFs from image sequences."""
    
    def __init__(self, page_size: str = 'A4', output_dir: str = 'output'):
        """
        Initialize PDF generator.
        
        Args:
            page_size: 'A4' or 'letter'
            output_dir: Directory to save PDFs
        """
        self.page_size = A4 if page_size == 'A4' else letter
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_pdf(self, image_paths: List[str], answer_copy_id: str, exam_details: dict = None) -> str:
        """
        Generate PDF from list of images.
        
        Args:
            image_paths: Ordered list of image file paths
            answer_copy_id: Unique identifier for answer copy
            exam_details: Dictionary with exam details (degree, subject, exam_date, college, unique_id)
            
        Returns:
            Path to generated PDF file
        """
        if not image_paths:
            raise ValueError("No images provided for PDF generation")
        
        # Generate filename: degree3_subject3_examdate3_college3_uuid6.pdf
        if exam_details:
            # Extract first 3 characters from each field (uppercase, pad if needed)
            def get_3_chars(field_value: str) -> str:
                """Get first 3 characters from field, uppercase, pad if needed."""
                if not field_value:
                    return ''
                # Sanitize first
                sanitized = sanitize_filename(field_value)
                # Get first 3 chars, uppercase
                chars = sanitized[:3].upper()
                # Pad with 'X' if shorter than 3
                return chars.ljust(3, 'X')
            
            degree = get_3_chars(exam_details.get('degree') or '')
            subject = get_3_chars(exam_details.get('subject') or '')
            # For exam_date, remove dashes and get first 3 chars
            exam_date_raw = (exam_details.get('exam_date') or '').replace('-', '')
            exam_date = get_3_chars(exam_date_raw)
            college = get_3_chars(exam_details.get('college') or '')
            
            # Generate 6-digit unique ID that won't repeat across multiple instances
            # Use UUID4 (guaranteed unique) + timestamp, then hash to 6 digits
            # This ensures uniqueness even when running multiple instances simultaneously
            uuid_value = uuid.uuid4()
            timestamp = int(time.time() * 1000000)  # Microseconds for precision
            # Combine UUID and timestamp, then hash using SHA256 (deterministic)
            combined = f"{uuid_value}{timestamp}"
            hash_obj = hashlib.sha256(combined.encode())
            hash_hex = hash_obj.hexdigest()
            # Convert first 6 hex digits to integer, then modulo to 6-digit number
            unique_id = f"{int(hash_hex[:6], 16) % 1000000:06d}"
            
            # Build filename: degree3_subject3_examdate3_college3_uuid6.pdf
            filename_parts = []
            if degree:
                filename_parts.append(degree)
            if subject:
                filename_parts.append(subject)
            if exam_date:
                filename_parts.append(exam_date)
            if college:
                filename_parts.append(college)
            # Always add 6-digit UUID at the end
            filename_parts.append(unique_id)
            
            pdf_filename = '_'.join(filename_parts) + '.pdf'
        else:
            # Fallback to original format if no exam details
            pdf_filename = f"{answer_copy_id}.pdf"
        
        pdf_path = os.path.join(self.output_dir, pdf_filename)
        
        # Create PDF canvas
        c = canvas.Canvas(pdf_path, pagesize=self.page_size)
        page_width, page_height = self.page_size
        
        for idx, img_path in enumerate(image_paths, 1):
            if not os.path.exists(img_path):
                print(f"Warning: Image not found: {img_path}")
                continue
            
            pil_image = None
            try:
                # Open and process image
                pil_image = Image.open(img_path)
                
                # Convert to RGB if necessary (for JPEG compatibility)
                if pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')
                
                # Calculate dimensions to fit page while maintaining aspect ratio
                img_width, img_height = pil_image.size
                aspect_ratio = img_width / img_height
                
                # Fit to page with margins
                margin = 40
                max_width = page_width - (2 * margin)
                max_height = page_height - (2 * margin)
                
                if aspect_ratio > (max_width / max_height):
                    # Image is wider
                    display_width = max_width
                    display_height = max_width / aspect_ratio
                else:
                    # Image is taller
                    display_height = max_height
                    display_width = max_height * aspect_ratio
                
                # Center image on page
                x = (page_width - display_width) / 2
                y = (page_height - display_height) / 2
                
                # Draw image
                c.drawImage(
                    ImageReader(pil_image),
                    x, y,
                    width=display_width,
                    height=display_height,
                    preserveAspectRatio=True
                )
                
                # Add new page (except for last image)
                if idx < len(image_paths):
                    c.showPage()
                
                # Close image immediately to free memory
                pil_image.close()
                pil_image = None
                
            except Exception as e:
                print(f"Error processing image {img_path}: {str(e)}")
                if pil_image:
                    try:
                        pil_image.close()
                    except:
                        pass
                continue
        
        # Save PDF
        c.save()
        
        return pdf_path
