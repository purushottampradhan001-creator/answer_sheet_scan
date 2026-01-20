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
import sys
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
            
            # Convert numpy bool to Python bool for JSON serialization
            is_blurry = bool(laplacian_var < self.blur_threshold)
            needs_improvement = bool(laplacian_var < (self.blur_threshold * 1.5))  # Warning threshold
            
            return {
                'is_blurry': is_blurry,
                'blur_score': round(float(laplacian_var), 2),
                'needs_improvement': needs_improvement,
                'threshold': self.blur_threshold
            }
        except Exception as e:
            return {'is_blurry': True, 'blur_score': 0, 'needs_improvement': True, 'error': str(e)}

    def get_image_info(self, image_path: str) -> Dict:
        """Collect basic image metadata for reporting."""
        try:
            info = {
                'path': image_path,
                'file_name': os.path.basename(image_path),
                'file_ext': os.path.splitext(image_path)[1].lower()
            }

            try:
                info['file_size_bytes'] = int(os.path.getsize(image_path))
            except Exception:
                info['file_size_bytes'] = None

            with Image.open(image_path) as img:
                info['width'] = int(img.width)
                info['height'] = int(img.height)
                info['mode'] = str(img.mode)
                info['format'] = str(img.format) if img.format else None

                # DPI is optional metadata and may be missing
                dpi = img.info.get('dpi') if hasattr(img, 'info') else None
                if dpi and isinstance(dpi, (tuple, list)) and len(dpi) >= 2:
                    info['dpi'] = (float(dpi[0]), float(dpi[1]))
                else:
                    info['dpi'] = None

            # Avoid divide-by-zero
            if info.get('height'):
                info['aspect_ratio'] = round(float(info['width']) / float(info['height']), 4)
            else:
                info['aspect_ratio'] = None

            return info
        except Exception as e:
            return {'path': image_path, 'error': str(e)}
    
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
            top_content = float(np.sum(top_region > 0) / (margin_pixels * width))
            
            # Bottom edge
            bottom_region = edges[-margin_pixels:, :]
            bottom_content = float(np.sum(bottom_region > 0) / (margin_pixels * width))
            
            # Left edge
            left_region = edges[:, :margin_pixels]
            left_content = float(np.sum(left_region > 0) / (margin_pixels * height))
            
            # Right edge
            right_region = edges[:, -margin_pixels:]
            right_content = float(np.sum(right_region > 0) / (margin_pixels * height))
            
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
                'is_cut': bool(len(cut_sides) > 0),
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
            image_area = float(gray.shape[0] * gray.shape[1])
            contour_area = float(cv2.contourArea(largest_contour))
            confidence = float(min(contour_area / image_area, 1.0))
            
            # Add small margin
            margin = 10
            x = int(max(0, x - margin))
            y = int(max(0, y - margin))
            w = int(min(img.shape[1] - x, w + 2 * margin))
            h = int(min(img.shape[0] - y, h + 2 * margin))
            
            return {
                'borders_detected': bool(confidence > 0.3),  # At least 30% of image
                'crop_coords': {'x': x, 'y': y, 'width': w, 'height': h},
                'confidence': round(confidence, 3)
            }
        except Exception as e:
            return {'borders_detected': False, 'error': str(e)}
    
    def detect_two_pages(self, image_path: str) -> Dict:
        """
        Robust detection of 2-page scans using projection profiles.
        Works for side-by-side AND top-bottom pages.
        """

        try:
            img = cv2.imread(image_path)
            if img is None:
                return {'is_two_pages': False, 'error': 'Cannot read image'}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape

            # Binary image
            _, binary = cv2.threshold(gray, 0, 255,
                                    cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # Remove noise
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

            # Projection profiles
            vertical_proj = np.sum(binary, axis=0)
            horizontal_proj = np.sum(binary, axis=1)

            # Normalize
            vertical_proj = vertical_proj / np.max(vertical_proj)
            horizontal_proj = horizontal_proj / np.max(horizontal_proj)

            # Detect LOW ink zones (possible split)
            v_gap = np.where(vertical_proj < 0.15)[0]
            h_gap = np.where(horizontal_proj < 0.15)[0]

            min_gap_width = int(0.04 * min(h, w))  # 4% of size

            result = {
                'is_two_pages': False,
                'split_direction': None,
                'split_position': None,
                'confidence': 0.0
            }

            # ---- Vertical split (side by side) ----
            if len(v_gap) > min_gap_width:
                center = w // 2
                gap_center = int(np.mean(v_gap))

                if abs(gap_center - center) < w * 0.15:
                    result.update({
                        'is_two_pages': True,
                        'split_direction': 'vertical',
                        'split_position': gap_center,
                        'confidence': 0.85
                    })
                    return result

            # ---- Horizontal split (top / bottom) ----
            if len(h_gap) > min_gap_width:
                center = h // 2
                gap_center = int(np.mean(h_gap))

                if abs(gap_center - center) < h * 0.15:
                    result.update({
                        'is_two_pages': True,
                        'split_direction': 'horizontal',
                        'split_position': gap_center,
                        'confidence': 0.9
                    })
                    return result

            return result

        except Exception as e:
            return {'is_two_pages': False, 'error': str(e)}

    def split_two_pages(self, image_path: str, output_dir: str, split_info: Dict) -> List[str]:
        try:
            if not split_info.get('is_two_pages'):
                return []

            os.makedirs(output_dir, exist_ok=True)

            img = Image.open(image_path)
            width, height = img.size

            split_direction = split_info['split_direction']
            split_pos = split_info['split_position']

            # Safety margin to avoid cutting text
            margin = int(0.01 * min(width, height))  # 1%

            base_name = os.path.splitext(os.path.basename(image_path))[0]
            output_files = []

            # ---------------- VERTICAL SPLIT ----------------
            if split_direction == 'vertical':
                # Left page: from left edge to split position (with margin)
                left_x_end = max(split_pos - margin, 1)  # At least 1 pixel
                left = img.crop((0, 0, left_x_end, height))
                
                # Right page: from split position (with margin) to right edge
                right_x_start = min(split_pos + margin, width - 1)  # At least 1 pixel from right
                right = img.crop((right_x_start, 0, width, height))

                left_path = os.path.join(output_dir, f"{base_name}_page1.jpg")
                right_path = os.path.join(output_dir, f"{base_name}_page2.jpg")

                # Skip re-splitting if outputs already exist
                if os.path.exists(left_path) and os.path.exists(right_path):
                    return [left_path, right_path]

                left.save(left_path, quality=95, subsampling=0, optimize=True)
                right.save(right_path, quality=95, subsampling=0, optimize=True)

                output_files.extend([left_path, right_path])

            # ---------------- HORIZONTAL SPLIT ----------------
            elif split_direction == 'horizontal':
                # Top page: from top to split position (with margin)
                top_y_end = max(split_pos - margin, 1)  # At least 1 pixel
                top = img.crop((0, 0, width, top_y_end))
                
                # Bottom page: from split position (with margin) to bottom
                bottom_y_start = min(split_pos + margin, height - 1)  # At least 1 pixel from bottom
                bottom = img.crop((0, bottom_y_start, width, height))

                top_path = os.path.join(output_dir, f"{base_name}_page1.jpg")
                bottom_path = os.path.join(output_dir, f"{base_name}_page2.jpg")

                # Skip re-splitting if outputs already exist
                if os.path.exists(top_path) and os.path.exists(bottom_path):
                    return [top_path, bottom_path]

                top.save(top_path, quality=95, subsampling=0, optimize=True)
                bottom.save(bottom_path, quality=95, subsampling=0, optimize=True)

                output_files.extend([top_path, bottom_path])

            return output_files

        except Exception as e:
            print(f"Split error: {e}", file=sys.stderr)
            sys.stderr.flush()
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
            print(f"Error removing yellow objects: {e}", file=sys.stderr)
            sys.stderr.flush()
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
            print(f"Error removing fingers: {e}", file=sys.stderr)
            sys.stderr.flush()
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
                'split_images': List[str],  # Paths to split images if two pages were split
                'needs_attention': bool,
                'warnings': List[str],
                'messages': List[str]
            }
        """
        result = {
            'checks': {},
            'fixes_applied': [],
            'processed_image_path': image_path,
            'split_images': [],  # Will contain split image paths if two pages are split
            'needs_attention': False,
            'warnings': [],
            'messages': [],
            'image_info': {}
        }
        
        messages = result['messages']
        
        if output_path is None:
            output_path = image_path
        
        # Run all checks
        image_info = self.get_image_info(image_path)
        result['image_info'] = image_info

        blur_check = self.check_blur(image_path)
        result['checks']['blur'] = blur_check
        
        cut_check = self.check_cut_edges(image_path)
        result['checks']['cut_edges'] = cut_check
        
        border_check = self.detect_borders(image_path)
        result['checks']['borders'] = border_check
        
        # Avoid re-splitting already split pages
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        is_split_child = base_name.endswith('_page1') or base_name.endswith('_page2')

        if is_split_child:
            two_pages_check = {
                'is_two_pages': False,
                'split_direction': None,
                'split_position': None,
                'confidence': 0.0,
                'note': 'Skipping two-page detection for already split page'
            }
        else:
            two_pages_check = self.detect_two_pages(image_path)
            print(f"Two pages check auto_process: {two_pages_check}", file=sys.stderr)
            sys.stderr.flush()

        result['checks']['two_pages'] = two_pages_check
        
        # Blur check messages (only warn if blurry)
        if blur_check.get('is_blurry'):
            result['warnings'].append('Image quality is not good')
            result['needs_attention'] = True
            messages.append(f"⚠️ Image quality is not good (score: {blur_check.get('blur_score', 0)})")
        
        # Two pages detection messages
        if two_pages_check.get('is_two_pages'):
            direction = two_pages_check.get('split_direction', 'unknown')
            confidence = two_pages_check.get('confidence', 0)
            result['warnings'].append('Two pages detected in one scan - consider splitting')
            result['needs_attention'] = True
            messages.append(f"⚠️ Two pages detected ({direction} split, confidence: {confidence:.1%})")
        else:
            messages.append("✅ Single page detected")
        
        # Apply auto fixes if requested
        if auto_fix:
            # Auto-split two pages if detected
            if two_pages_check.get('is_two_pages'):
                try:
                    # Determine output directory - use same directory as input image
                    output_dir = os.path.dirname(image_path)
                    if not output_dir:
                        output_dir = os.getcwd()
                    
                    # Split the pages
                    split_paths = self.split_two_pages(image_path, output_dir, two_pages_check)
                    
                    if split_paths and len(split_paths) == 2:
                        result['fixes_applied'].append('split_two_pages')
                        result['split_images'] = split_paths
                        messages.append(f"✂️ Split into 2 pages: {os.path.basename(split_paths[0])} and {os.path.basename(split_paths[1])}")
                        print(f"Auto-split successful: {split_paths}", file=sys.stderr)
                        sys.stderr.flush()
                    else:
                        result['warnings'].append('Could not split two pages automatically')
                        messages.append("❌ Could not split two pages automatically")
                        print(f"Split failed or returned unexpected result: {split_paths}", file=sys.stderr)
                        sys.stderr.flush()
                except Exception as e:
                    result['warnings'].append(f"Could not split two pages: {e}")
                    messages.append(f"❌ Could not split two pages: {e}")
                    print(f"Error splitting two pages: {e}", file=sys.stderr)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    sys.stderr.flush()
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
