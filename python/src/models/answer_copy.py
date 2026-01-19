"""
Answer copy model and state management
"""

from typing import Dict, List, Optional
from datetime import datetime


class AnswerCopy:
    """Represents an answer copy session"""
    
    def __init__(self, answer_copy_id: str, working_path: str):
        self.id = answer_copy_id
        self.working_path = working_path
        self.images: List[Dict] = []
        self.exam_details = {
            'degree': None,
            'subject': None,
            'exam_date': None,
            'college': None,
            'unique_id': None
        }
        self.created_at = datetime.now()
        self.completed_at: Optional[datetime] = None
        self.pdf_path: Optional[str] = None
    
    def add_image(self, image_path: str, sequence_number: int, filename: str):
        """Add an image to this answer copy."""
        self.images.append({
            'path': image_path,
            'sequence': sequence_number,
            'filename': filename
        })
    
    def get_ordered_images(self) -> List[str]:
        """Get image paths in sequence order."""
        return [
            img['path'] for img in sorted(
                self.images,
                key=lambda x: x['sequence']
            )
        ]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'image_count': len(self.images),
            'images': self.images,
            'exam_details': self.exam_details,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'pdf_path': self.pdf_path
        }
