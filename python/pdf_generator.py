"""
PDF generation module using ReportLab.
Creates one PDF per answer copy from ordered images.
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from PIL import Image
import os
from typing import List, Optional


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
    
    def generate_pdf(self, image_paths: List[str], answer_copy_id: str) -> str:
        """
        Generate PDF from list of images.
        
        Args:
            image_paths: Ordered list of image file paths
            answer_copy_id: Unique identifier for answer copy
            
        Returns:
            Path to generated PDF file
        """
        if not image_paths:
            raise ValueError("No images provided for PDF generation")
        
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
