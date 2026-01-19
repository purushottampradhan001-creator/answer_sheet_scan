"""
Auto image processor for quality checks and improvements.
Features:
- Blur detection
- Cut/edge detection
- Border detection
- Page splitting (2 pages in one scan)
- Object removal (fingers, yellow stickers)
"""

import cv2
import numpy as np
from PIL import Image
import os
from typing import Dict, Tuple, Optional, List


class AutoImageProcessor:
    """Automatically processes images to detect and fix issues."""
    
    def __init__(self):
        """Initialize the auto processor."""
        self.blur_threshold = 100.0  # Laplacian variance threshold
        self.edge_margin_threshold = 0.05  # 5% margin for edge detection
        self.yellow_lower = np.array([20, 100, 100])  # HSV lower bound for yellow
        self.yellow_upper = np.array([30, 255, 255])  # HSV upper bound for yellow
    
    def check_blur(self, image_path: str) -> Dict:
        """
        Check if image is blurry using Laplacian variance.
        
        Returns:
            {
                'is_blurry': bool,
                'blur_score': float,
                'needs_improvement': bool
            }
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {'is_blurry': True, 'blur_score': 0, 'needs_improvement': True, 'error': 'Cannot read image'}
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            
            is_blurry = laplacian_var < self.blur_threshold
            needs_improvement = laplacian_var < (self.blur_threshold * 1.5)  # Warning threshold
            
            return {
                'is_blurry': is_blurry,
                'blur_score': round(laplacian_var, 2),
                'needs_improvement': needs_improvement,
                'threshold': self.blur_threshold
            }
        except Exception as e:
            return {'is_blurry': True, 'blur_score': 0, 'needs_improvement': True, 'error': str(e)}
    
    def check_cut_edges(self, image_path: str) -> Dict:
        """
        Check if image is cut on any side.
        
        Returns:
            {
                'is_cut': bool,
                'cut_sides': List[str],  # ['top', 'bottom', 'left', 'right']
                'edge_margins': Dict  # margins for each side
            }
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {'is_cut': True, 'cut_sides': ['all'], 'error': 'Cannot read image'}
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            height, width = gray.shape
            
            # Detect edges using Canny
            edges = cv2.Canny(gray, 50, 150)
            
            # Check each side for content
            margin_pixels = int(min(width, height) * self.edge_margin_threshold)
            
            # Top edge
            top_region = edges[:margin_pixels, :]
            top_content = np.sum(top_region > 0) / (margin_pixels * width)
            
            # Bottom edge
            bottom_region = edges[-margin_pixels:, :]
            bottom_content = np.sum(bottom_region > 0) / (margin_pixels * width)
            
            # Left edge
            left_region = edges[:, :margin_pixels]
            left_content = np.sum(left_region > 0) / (margin_pixels * height)
            
            # Right edge
            right_region = edges[:, -margin_pixels:]
            right_content = np.sum(right_region > 0) / (margin_pixels * height)
            
            # Threshold for considering a side "cut" (very low edge content)
            edge_threshold = 0.01  # 1% of pixels should have edges
            
            cut_sides = []
            if top_content < edge_threshold:
                cut_sides.append('top')
            if bottom_content < edge_threshold:
                cut_sides.append('bottom')
            if left_content < edge_threshold:
                cut_sides.append('left')
            if right_content < edge_threshold:
                cut_sides.append('right')
            
            return {
                'is_cut': len(cut_sides) > 0,
                'cut_sides': cut_sides,
                'edge_margins': {
                    'top': round(top_content, 4),
                    'bottom': round(bottom_content, 4),
                    'left': round(left_content, 4),
                    'right': round(right_content, 4)
                }
            }
        except Exception as e:
            return {'is_cut': True, 'cut_sides': ['unknown'], 'error': str(e)}
    
    def detect_borders(self, image_path: str) -> Dict:
        """
        Detect document borders and suggest crop coordinates.
        
        Returns:
            {
                'borders_detected': bool,
                'crop_coords': {'x': int, 'y': int, 'width': int, 'height': int},
                'confidence': float
            }
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {'borders_detected': False, 'error': 'Cannot read image'}
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Apply adaptive threshold
            thresh = cv2.adaptiveThreshold(
                blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours:
                return {'borders_detected': False, 'error': 'No contours found'}
            
            # Find largest contour (likely the document)
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(largest_contour)
            
            # Calculate confidence based on contour area vs image area
            image_area = gray.shape[0] * gray.shape[1]
            contour_area = cv2.contourArea(largest_contour)
            confidence = min(contour_area / image_area, 1.0)
            
            # Add small margin
            margin = 10
            x = max(0, x - margin)
            y = max(0, y - margin)
            w = min(img.shape[1] - x, w + 2 * margin)
            h = min(img.shape[0] - y, h + 2 * margin)
            
            return {
                'borders_detected': confidence > 0.3,  # At least 30% of image
                'crop_coords': {'x': x, 'y': y, 'width': w, 'height': h},
                'confidence': round(confidence, 3)
            }
        except Exception as e:
            return {'borders_detected': False, 'error': str(e)}
    
    def detect_two_pages(self, image_path: str) -> Dict:
        """
        Detect if 2 pages are scanned together (side by side or top/bottom).
        
        Returns:
            {
                'is_two_pages': bool,
                'split_direction': str,  # 'vertical' or 'horizontal'
                'split_position': int,  # pixel position to split
                'confidence': float
            }
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {'is_two_pages': False, 'error': 'Cannot read image'}
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            height, width = gray.shape
            
            # Check for vertical split (side by side pages)
            # Look for vertical line in the middle with low content
            mid_x = width // 2
            margin = width // 10  # 10% margin around center
            
            vertical_region = gray[:, mid_x - margin:mid_x + margin]
            vertical_variance = np.var(vertical_region)
            
            # Check for horizontal split (top/bottom pages)
            mid_y = height // 2
            horizontal_region = gray[mid_y - margin:mid_y + margin, :]
            horizontal_variance = np.var(horizontal_region)
            
            # Lower variance in center suggests a split (less content = likely gap between pages)
            vertical_split_score = 1.0 / (1.0 + vertical_variance / 1000.0)
            horizontal_split_score = 1.0 / (1.0 + horizontal_variance / 1000.0)
            
            # Also check aspect ratio - if very wide, likely side-by-side
            aspect_ratio = width / height
            is_wide = aspect_ratio > 1.5
            is_tall = aspect_ratio < 0.67
            
            is_two_pages = False
            split_direction = None
            split_position = None
            confidence = 0.0
            
            if is_wide and vertical_split_score > 0.6:
                # Likely side-by-side pages
                is_two_pages = True
                split_direction = 'vertical'
                split_position = mid_x
                confidence = min(vertical_split_score, 0.9)
            elif is_tall and horizontal_split_score > 0.6:
                # Likely top/bottom pages
                is_two_pages = True
                split_direction = 'horizontal'
                split_position = mid_y
                confidence = min(horizontal_split_score, 0.9)
            elif vertical_split_score > 0.7:
                # Strong vertical split regardless of aspect ratio
                is_two_pages = True
                split_direction = 'vertical'
                split_position = mid_x
                confidence = vertical_split_score
            elif horizontal_split_score > 0.7:
                # Strong horizontal split regardless of aspect ratio
                is_two_pages = True
                split_direction = 'horizontal'
                split_position = mid_y
                confidence = horizontal_split_score
            
            return {
                'is_two_pages': is_two_pages,
                'split_direction': split_direction,
                'split_position': split_position,
                'confidence': round(confidence, 3)
            }
        except Exception as e:
            return {'is_two_pages': False, 'error': str(e)}
    
    def split_two_pages(self, image_path: str, output_dir: str, split_info: Dict) -> List[str]:
        """
        Split an image containing 2 pages into 2 separate images.
        
        Args:
            image_path: Path to input image
            output_dir: Directory to save split images
            split_info: Result from detect_two_pages()
        
        Returns:
            List of paths to split images
        """
        try:
            img = Image.open(image_path)
            width, height = img.size
            
            split_direction = split_info['split_direction']
            split_position = split_info['split_position']
            
            output_paths = []
            
            if split_direction == 'vertical':
                # Split left and right
                left_img = img.crop((0, 0, split_position, height))
                right_img = img.crop((split_position, 0, width, height))
                
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                left_path = os.path.join(output_dir, f"{base_name}_left.jpg")
                right_path = os.path.join(output_dir, f"{base_name}_right.jpg")
                
                left_img.save(left_path, quality=95, optimize=True)
                right_img.save(right_path, quality=95, optimize=True)
                
                output_paths = [left_path, right_path]
            elif split_direction == 'horizontal':
                # Split top and bottom
                top_img = img.crop((0, 0, width, split_position))
                bottom_img = img.crop((0, split_position, width, height))
                
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                top_path = os.path.join(output_dir, f"{base_name}_top.jpg")
                bottom_path = os.path.join(output_dir, f"{base_name}_bottom.jpg")
                
                top_img.save(top_path, quality=95, optimize=True)
                bottom_img.save(bottom_path, quality=95, optimize=True)
                
                output_paths = [top_path, bottom_path]
            
            return output_paths
        except Exception as e:
            print(f"Error splitting pages: {e}")
            return []
    
    def remove_yellow_objects(self, image_path: str, output_path: Optional[str] = None) -> str:
        """
        Remove yellow stickers/objects from image using inpainting.
        
        Args:
            image_path: Path to input image
            output_path: Optional output path. If None, overwrites input.
        
        Returns:
            Path to processed image
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return image_path
            
            # Convert to HSV for better color detection
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            
            # Create mask for yellow objects
            mask = cv2.inRange(hsv, self.yellow_lower, self.yellow_upper)
            
            # Dilate mask to cover edges
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.dilate(mask, kernel, iterations=2)
            
            # Use inpainting to remove yellow objects
            result = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)
            
            if output_path is None:
                output_path = image_path
            
            cv2.imwrite(output_path, result)
            return output_path
        except Exception as e:
            print(f"Error removing yellow objects: {e}")
            return image_path
    
    def remove_fingers(self, image_path: str, output_path: Optional[str] = None) -> str:
        """
        Detect and remove finger marks from image.
        Uses skin color detection and inpainting.
        
        Args:
            image_path: Path to input image
            output_path: Optional output path. If None, overwrites input.
        
        Returns:
            Path to processed image
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return image_path
            
            # Convert to HSV for skin color detection
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            
            # Skin color range in HSV
            # Lower bound for skin color
            lower_skin1 = np.array([0, 20, 70], dtype=np.uint8)
            upper_skin1 = np.array([20, 255, 255], dtype=np.uint8)
            
            # Upper bound for skin color (wrapping around hue)
            lower_skin2 = np.array([170, 20, 70], dtype=np.uint8)
            upper_skin2 = np.array([180, 255, 255], dtype=np.uint8)
            
            # Create mask for skin color
            mask1 = cv2.inRange(hsv, lower_skin1, upper_skin1)
            mask2 = cv2.inRange(hsv, lower_skin2, upper_skin2)
            mask = cv2.bitwise_or(mask1, mask2)
            
            # Filter out small regions (likely not fingers)
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            
            # Remove very small blobs
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            min_area = (img.shape[0] * img.shape[1]) * 0.001  # 0.1% of image area
            
            filtered_mask = np.zeros_like(mask)
            for contour in contours:
                if cv2.contourArea(contour) > min_area:
                    cv2.drawContours(filtered_mask, [contour], -1, 255, -1)
            
            # Dilate mask slightly
            kernel = np.ones((5, 5), np.uint8)
            filtered_mask = cv2.dilate(filtered_mask, kernel, iterations=1)
            
            # Use inpainting to remove finger marks
            result = cv2.inpaint(img, filtered_mask, 3, cv2.INPAINT_TELEA)
            
            if output_path is None:
                output_path = image_path
            
            cv2.imwrite(output_path, result)
            return output_path
        except Exception as e:
            print(f"Error removing fingers: {e}")
            return image_path
    
    def auto_process(self, image_path: str, output_path: Optional[str] = None, 
                    auto_fix: bool = True) -> Dict:
        """
        Automatically check and process image for all issues.
        
        Args:
            image_path: Path to input image
            output_path: Optional output path for processed image
            auto_fix: If True, automatically apply fixes
        
        Returns:
            {
                'checks': {
                    'blur': Dict,
                    'cut_edges': Dict,
                    'borders': Dict,
                    'two_pages': Dict
                },
                'fixes_applied': List[str],
                'processed_image_path': str,
                'needs_attention': bool,
                'warnings': List[str],
                'messages': List[str]
            }
        """
        result = {
            'checks': {},
            'fixes_applied': [],
            'processed_image_path': image_path,
            'needs_attention': False,
            'warnings': [],
            'messages': []
        }
        
        messages = result['messages']
        
        if output_path is None:
            output_path = image_path
        
        # Run all checks
        blur_check = self.check_blur(image_path)
        result['checks']['blur'] = blur_check
        
        cut_check = self.check_cut_edges(image_path)
        result['checks']['cut_edges'] = cut_check
        
        border_check = self.detect_borders(image_path)
        result['checks']['borders'] = border_check
        
        two_pages_check = self.detect_two_pages(image_path)
        result['checks']['two_pages'] = two_pages_check
        
        # Collect warnings and build messages
        messages.append("🔍 Auto-processing completed")
        
        # Blur check messages
        if blur_check.get('is_blurry'):
            result['warnings'].append('Image is blurry')
            result['needs_attention'] = True
            messages.append(f"⚠️ Image is blurry (score: {blur_check.get('blur_score', 0)})")
        elif blur_check.get('needs_improvement'):
            result['warnings'].append('Image quality could be improved')
            messages.append(f"ℹ️ Image quality could be improved (score: {blur_check.get('blur_score', 0)})")
        else:
            messages.append(f"✅ Image sharpness: Good (score: {blur_check.get('blur_score', 0)})")
        
        # Cut edges check messages
        if cut_check.get('is_cut'):
            cut_sides = cut_check.get('cut_sides', [])
            result['warnings'].append(f"Image appears cut on: {', '.join(cut_sides)}")
            result['needs_attention'] = True
            messages.append(f"⚠️ Image appears cut on: {', '.join(cut_sides)}")
        else:
            messages.append("✅ Image edges: Complete")
        
        # Border detection messages
        if border_check.get('borders_detected'):
            confidence = border_check.get('confidence', 0)
            messages.append(f"✅ Document borders detected (confidence: {confidence:.1%})")
        else:
            messages.append("ℹ️ Document borders not clearly detected")
        
        # Two pages detection messages
        if two_pages_check.get('is_two_pages'):
            direction = two_pages_check.get('split_direction', 'unknown')
            confidence = two_pages_check.get('confidence', 0)
            result['warnings'].append('Two pages detected in one scan - consider splitting')
            result['needs_attention'] = True
            messages.append(f"⚠️ Two pages detected ({direction} split, confidence: {confidence:.1%})")
            messages.append("💡 Consider using 'Split Two Pages' feature to separate them")
        else:
            messages.append("✅ Single page detected")
        
        # Apply auto fixes if requested
        if auto_fix:
            processed_img = image_path
            
            # Remove yellow objects
            try:
                processed_img = self.remove_yellow_objects(processed_img, output_path)
                result['fixes_applied'].append('removed_yellow_objects')
                messages.append("🔧 Removed yellow stickers/objects")
            except Exception as e:
                result['warnings'].append(f"Could not remove yellow objects: {e}")
                messages.append(f"❌ Could not remove yellow objects: {e}")
            
            # Remove fingers
            try:
                processed_img = self.remove_fingers(processed_img, output_path)
                result['fixes_applied'].append('removed_fingers')
                messages.append("🔧 Removed finger marks")
            except Exception as e:
                result['warnings'].append(f"Could not remove fingers: {e}")
                messages.append(f"❌ Could not remove fingers: {e}")
            
            # Auto crop borders if detected
            if border_check.get('borders_detected') and border_check.get('confidence', 0) > 0.5:
                try:
                    img = Image.open(processed_img)
                    crop_coords = border_check['crop_coords']
                    cropped = img.crop((
                        crop_coords['x'],
                        crop_coords['y'],
                        crop_coords['x'] + crop_coords['width'],
                        crop_coords['y'] + crop_coords['height']
                    ))
                    cropped.save(output_path, quality=95, optimize=True)
                    processed_img = output_path
                    result['fixes_applied'].append('auto_cropped_borders')
                    messages.append("✂️ Auto-cropped to document borders")
                except Exception as e:
                    result['warnings'].append(f"Could not auto-crop borders: {e}")
                    messages.append(f"❌ Could not auto-crop borders: {e}")
            
            # Summary of fixes
            if result['fixes_applied']:
                messages.append(f"✅ Applied {len(result['fixes_applied'])} auto-fix(es)")
            else:
                messages.append("✅ No fixes needed")
            
            result['processed_image_path'] = processed_img
        
        return result
