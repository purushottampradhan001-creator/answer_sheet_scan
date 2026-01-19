"""
Image validation module for duplicate detection and quality checks.
Works completely offline.
"""

# This file was moved from validator.py - update imports if needed

import cv2
import numpy as np
from PIL import Image
import imagehash
import os
from typing import Tuple, Dict, Optional


class ImageValidator:
    """Validates images for duplicates, quality, and corruption."""
    
    def __init__(self, hash_threshold: int = 5):
        """
        Initialize validator.
        
        Args:
            hash_threshold: Maximum hamming distance for duplicate detection (0-64)
        """
        self.hash_threshold = hash_threshold
        self.processed_hashes = []  # Store hashes for current answer copy
    
    def reset(self):
        """Reset validator for new answer copy."""
        self.processed_hashes = []
    
    def check_duplicate(self, image_path: str) -> Tuple[bool, Optional[str]]:
        """
        Check if image is duplicate using perceptual hashing.
        
        Returns:
            (is_duplicate, message)
        """
        try:
            # Generate perceptual hash
            with Image.open(image_path) as img:
                phash = imagehash.phash(img)
            
            # Compare with existing hashes
            for existing_hash in self.processed_hashes:
                hamming_distance = phash - existing_hash
                if hamming_distance <= self.hash_threshold:
                    return True, f"Duplicate detected (similarity: {hamming_distance})"
            
            # Not a duplicate, store hash
            self.processed_hashes.append(phash)
            return False, None
            
        except Exception as e:
            return False, f"Error checking duplicate: {str(e)}"
    
    def check_quality(self, image_path: str) -> Tuple[str, Dict]:
        """
        Check image quality: blur, resolution, corruption.
        
        Returns:
            (status, details)
            status: 'accepted', 'low_quality', 'rejected'
        """
        try:
            # Read image
            img = cv2.imread(image_path)
            if img is None:
                return 'rejected', {'error': 'Cannot read image file'}
            
            details = {}
            
            # Check resolution
            height, width = img.shape[:2]
            min_resolution = 800 * 600  # Minimum acceptable resolution
            resolution = height * width
            details['resolution'] = f"{width}x{height}"
            details['pixel_count'] = resolution
            
            if resolution < min_resolution:
                return 'low_quality', {**details, 'warning': 'Low resolution'}
            
            # Check blur using Laplacian variance
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            details['blur_score'] = round(laplacian_var, 2)
            
            # Blur threshold (adjust based on testing)
            blur_threshold = 100.0
            if laplacian_var < blur_threshold:
                return 'low_quality', {**details, 'warning': 'Image appears blurry'}
            
            # Check file size (corruption indicator)
            file_size = os.path.getsize(image_path)
            details['file_size_kb'] = round(file_size / 1024, 2)
            
            if file_size < 10 * 1024:  # Less than 10KB might be corrupted
                return 'rejected', {**details, 'error': 'File too small, possibly corrupted'}
            
            # Check if image can be fully decoded
            try:
                test_img = Image.open(image_path)
                test_img.verify()
            except Exception as e:
                return 'rejected', {**details, 'error': f'Image corruption detected: {str(e)}'}
            
            return 'accepted', details
            
        except Exception as e:
            return 'rejected', {'error': f'Quality check failed: {str(e)}'}
    
    def validate_image(self, image_path: str) -> Dict:
        """
        Complete validation: duplicate + quality.
        
        Returns:
            {
                'valid': bool,
                'duplicate': bool,
                'quality_status': str,
                'message': str,
                'details': dict
            }
        """
        result = {
            'valid': False,
            'duplicate': False,
            'quality_status': 'unknown',
            'message': '',
            'details': {}
        }
        
        # Check duplicate
        is_duplicate, dup_message = self.check_duplicate(image_path)
        result['duplicate'] = is_duplicate
        
        if is_duplicate:
            result['message'] = dup_message
            return result
        
        # Check quality
        quality_status, quality_details = self.check_quality(image_path)
        result['quality_status'] = quality_status
        result['details'] = quality_details
        
        if quality_status == 'rejected':
            result['message'] = quality_details.get('error', 'Image rejected')
            return result
        
        # Image is valid
        result['valid'] = True
        if quality_status == 'low_quality':
            result['message'] = f"Accepted with warning: {quality_details.get('warning', '')}"
        else:
            result['message'] = 'Image accepted'
        
        return result
