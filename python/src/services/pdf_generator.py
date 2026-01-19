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
        
        # Generate filename based on exam details
        if exam_details and all([
            exam_details.get('degree'),
            exam_details.get('subject'),
            exam_details.get('exam_date'),
            exam_details.get('college')
        ]):
            # Format: Degree_Subject_ExamDate_College_UniqueID.pdf
            degree = sanitize_filename(exam_details['degree'])
            subject = sanitize_filename(exam_details['subject'])
            exam_date = exam_details['exam_date'].replace('-', '')  # Remove dashes from date
            college = sanitize_filename(exam_details['college'])
            
            # Get unique_id, generate from fields if missing
            unique_id = exam_details.get('unique_id')
            if not unique_id:
                # Generate from last 2 characters of each field
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
                    unique_id = ''.join(unique_parts)
                else:
                    # Fallback to timestamp
                    unique_id = answer_copy_id.split('_')[-1]
            
            pdf_filename = f"{degree}_{subject}_{exam_date}_{college}_{unique_id}.pdf"
        else:
            # Fallback to original format
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
