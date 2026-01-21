"""
Auto image processor for quality checks and improvements.
Features:
- Blur detection
- Cut/edge detection
- Border detection
- Page splitting (2 pages in one scan)
- Object removal (fingers, yellow stickers)
- Auto rotation (EXIF + OCR + fallback)
"""

import cv2
import numpy as np
from PIL import Image, ImageOps
import os
import sys
from typing import Dict, Tuple, Optional, List

# ---------------- OPTIONAL OCR ----------------
try:
    import pytesseract
    from pytesseract import Output as _tesseract_output
    _HAVE_TESSERACT = True
except Exception:
    pytesseract = None
    _tesseract_output = None
    _HAVE_TESSERACT = False


class AutoImageProcessor:
    """
    Automatically processes images to detect and fix issues.
    This class is SAFE for offline + production environments.
    """

    def __init__(self):
        # Blur
        self.blur_threshold = 100.0

        # Edge cut detection
        self.edge_margin_threshold = 0.05  # 5%

        # Yellow sticker detection (HSV)
        self.yellow_lower = np.array([20, 100, 100])
        self.yellow_upper = np.array([30, 255, 255])

        # Last-run flags (best-effort) so callers can know whether a step actually did work
        # without changing the public method signatures.
        self._last_finger_detected = None
        self._last_finger_removed = None

    # ----------------------------------------------------
    # INTERNAL SAFE HELPERS
    # ----------------------------------------------------

    def _safe_read_cv(self, image_path: str):
        img = cv2.imread(image_path)
        return img if img is not None else None

    def _safe_open_pil(self, image_path: str):
        try:
            return Image.open(image_path)
        except Exception:
            return None

    def _ensure_dir(self, path: str):
        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

    def _log_err(self, msg: str):
        print(msg, file=sys.stderr)
        sys.stderr.flush()
    # ----------------------------------------------------
    # IMAGE METADATA
    # ----------------------------------------------------

    def get_image_info(self, image_path: str) -> Dict:
        """
        Collect basic image metadata for reporting.
        """
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

            img = self._safe_open_pil(image_path)
            if img is None:
                return info

            info['width'] = int(img.width)
            info['height'] = int(img.height)
            info['mode'] = str(img.mode)
            info['format'] = str(img.format) if img.format else None

            dpi = img.info.get('dpi')
            if dpi and isinstance(dpi, (tuple, list)) and len(dpi) >= 2:
                info['dpi'] = (float(dpi[0]), float(dpi[1]))
            else:
                info['dpi'] = None

            if img.height > 0:
                info['aspect_ratio'] = round(img.width / img.height, 4)
            else:
                info['aspect_ratio'] = None

            img.close()
            return info

        except Exception as e:
            return {'path': image_path, 'error': str(e)}

    # ----------------------------------------------------
    # BLUR DETECTION
    # ----------------------------------------------------

    def check_blur(self, image_path: str) -> Dict:
        """
        Check if image is blurry using Laplacian variance.
        """
        try:
            img = self._safe_read_cv(image_path)
            if img is None:
                return {
                    'is_blurry': True,
                    'blur_score': 0.0,
                    'needs_improvement': True,
                    'error': 'Cannot read image'
                }

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

            is_blurry = lap_var < self.blur_threshold
            needs_improvement = lap_var < (self.blur_threshold * 1.5)

            return {
                'is_blurry': bool(is_blurry),
                'blur_score': round(lap_var, 2),
                'needs_improvement': bool(needs_improvement),
                'threshold': self.blur_threshold
            }

        except Exception as e:
            return {
                'is_blurry': True,
                'blur_score': 0.0,
                'needs_improvement': True,
                'error': str(e)
            }

    # ----------------------------------------------------
    # CUT / EDGE DETECTION
    # ----------------------------------------------------

    def check_cut_edges(self, image_path: str) -> Dict:
        """
        Detect if page is cut on any side.
        """
        try:
            img = self._safe_read_cv(image_path)
            if img is None:
                return {'is_cut': True, 'cut_sides': ['all']}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape

            edges = cv2.Canny(gray, 80, 160)

            margin = max(5, int(min(h, w) * self.edge_margin_threshold))

            def edge_density(region):
                total = region.size
                return float(np.count_nonzero(region)) / total if total else 0.0

            top = edge_density(edges[:margin, :])
            bottom = edge_density(edges[-margin:, :])
            left = edge_density(edges[:, :margin])
            right = edge_density(edges[:, -margin:])

            edge_threshold = 0.01
            cut_sides = []

            if top < edge_threshold:
                cut_sides.append('top')
            if bottom < edge_threshold:
                cut_sides.append('bottom')
            if left < edge_threshold:
                cut_sides.append('left')
            if right < edge_threshold:
                cut_sides.append('right')

            return {
                'is_cut': bool(cut_sides),
                'cut_sides': cut_sides,
                'edge_margins': {
                    'top': round(top, 4),
                    'bottom': round(bottom, 4),
                    'left': round(left, 4),
                    'right': round(right, 4)
                }
            }

        except Exception as e:
            return {
                'is_cut': True,
                'cut_sides': ['unknown'],
                'error': str(e)
            }
    # ----------------------------------------------------
    # BORDER DETECTION
    # ----------------------------------------------------

    def detect_borders(self, image_path: str) -> Dict:
        """
        Detect document borders and suggest crop coordinates.
        """
        try:
            img = self._safe_read_cv(image_path)
            if img is None:
                return {'borders_detected': False, 'error': 'Cannot read image'}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            thresh = cv2.adaptiveThreshold(
                blurred,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                11,
                2
            )

            contours, _ = cv2.findContours(
                thresh,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            if not contours:
                return {'borders_detected': False}

            largest = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest)

            image_area = float(gray.shape[0] * gray.shape[1])
            contour_area = float(cv2.contourArea(largest))
            confidence = contour_area / image_area if image_area else 0.0

            margin = 10
            x = max(0, x - margin)
            y = max(0, y - margin)
            w = min(img.shape[1] - x, w + margin * 2)
            h = min(img.shape[0] - y, h + margin * 2)

            return {
                'borders_detected': bool(confidence > 0.3),
                'crop_coords': {
                    'x': int(x),
                    'y': int(y),
                    'width': int(w),
                    'height': int(h)
                },
                'confidence': round(float(confidence), 3)
            }

        except Exception as e:
            return {'borders_detected': False, 'error': str(e)}

    # ----------------------------------------------------
    # TWO PAGE DETECTION (SIDE-BY-SIDE OR TOP-BOTTOM)
    # ----------------------------------------------------

    def detect_two_pages(self, image_path: str) -> Dict:
        """
        Robust detection of 2-page scans.
        Handles:
        - side-by-side pages
        - top-bottom stacked pages
        - handwritten / ruled pages
        - scanner borders
        """

        try:
            img = self._safe_read_cv(image_path)
            if img is None:
                return {'is_two_pages': False, 'error': 'Cannot read image'}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape

            # ---------- Binarize ----------
            _, binary = cv2.threshold(
                gray, 0, 255,
                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )

            # ---------- Remove scanner borders (CRITICAL) ----------
            pad = int(0.06 * min(h, w))  # 6% crop
            if pad * 2 < h and pad * 2 < w:
                binary = binary[pad:h - pad, pad:w - pad]
                h, w = binary.shape

            # ---------- Morphological cleanup ----------
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

            # ---------- Projection profiles ----------
            v_proj = np.sum(binary, axis=0).astype(np.float32)
            h_proj = np.sum(binary, axis=1).astype(np.float32)

            if v_proj.max() == 0 or h_proj.max() == 0:
                return {'is_two_pages': False}

            v_proj /= v_proj.max()
            h_proj /= h_proj.max()

            # ---------- Whitespace-based gap ----------
            def find_white_gap(proj, size):
                gaps = np.where(proj < 0.15)[0]
                if gaps.size == 0:
                    return None

                center = size / 2
                best = None

                for idx in gaps:
                    dist = abs(idx - center) / center
                    if dist > 0.3:
                        continue
                    score = 1.0 - dist
                    if not best or score > best['confidence']:
                        best = {
                            'position': int(idx),
                            'confidence': round(float(score), 3)
                        }
                return best

            # ---------- Gradient-based gap (HANDWRITTEN FIX) ----------
            def find_gradient_gap(proj, size):
                grad = np.abs(np.diff(proj))
                if grad.max() == 0:
                    return None

                grad /= grad.max()
                center = size / 2
                candidates = np.where(grad > 0.35)[0]

                best = None
                for idx in candidates:
                    dist = abs(idx - center) / center
                    if dist > 0.3:
                        continue
                    score = 1.0 - dist
                    if not best or score > best['confidence']:
                        best = {
                            'position': int(idx),
                            'confidence': round(float(score), 3)
                        }
                return best

            # ---------- Find candidates ----------
            v_gap = find_white_gap(v_proj, w)
            h_gap = find_white_gap(h_proj, h)

            v_grad = find_gradient_gap(v_proj, w)
            h_grad = find_gradient_gap(h_proj, h)

            # Prefer gradient if whitespace failed
            if not v_gap and v_grad:
                v_gap = v_grad
            if not h_gap and h_grad:
                h_gap = h_grad

            if not v_gap and not h_gap:
                return {
                    'is_two_pages': False,
                    'split_direction': None,
                    'split_position': None,
                    'confidence': 0.0
                }

            # ---------- Aspect ratio bias (STACKED PAGES FIX) ----------
            prefer_horizontal = h > w * 1.4

            if prefer_horizontal and h_gap:
                return {
                    'is_two_pages': True,
                    'split_direction': 'horizontal',
                    'split_position': h_gap['position'],
                    'confidence': h_gap['confidence']
                }

            if v_gap and (not h_gap or v_gap['confidence'] >= h_gap['confidence']):
                return {
                    'is_two_pages': True,
                    'split_direction': 'vertical',
                    'split_position': v_gap['position'],
                    'confidence': v_gap['confidence']
                }

            return {
                'is_two_pages': True,
                'split_direction': 'horizontal',
                'split_position': h_gap['position'],
                'confidence': h_gap['confidence']
            }

        except Exception as e:
            return {'is_two_pages': False, 'error': str(e)}

    # ----------------------------------------------------
    # SPLIT TWO PAGES
    # ----------------------------------------------------

    def split_two_pages(self, image_path: str, output_dir: str, split_info: Dict) -> List[str]:
        """
        Split a two-page scanned image into two separate images.
        """
        try:
            if not split_info.get('is_two_pages'):
                return []

            img = self._safe_open_pil(image_path)
            if img is None:
                return []

            self._ensure_dir(output_dir)

            width, height = img.size
            split_direction = split_info.get('split_direction')
            split_pos = int(split_info.get('split_position', 0))

            if split_pos <= 0:
                return []

            margin = int(0.01 * min(width, height))
            base = os.path.splitext(os.path.basename(image_path))[0]
            out_files = []

            # -------- Vertical (Left | Right) --------
            if split_direction == 'vertical':
                left_end = max(split_pos - margin, 1)
                right_start = min(split_pos + margin, width - 1)

                left = img.crop((0, 0, left_end, height))
                right = img.crop((right_start, 0, width, height))

                p1 = os.path.join(output_dir, f"{base}_page1.jpg")
                p2 = os.path.join(output_dir, f"{base}_page2.jpg")

                left.save(p1, quality=95, subsampling=0, optimize=True)
                right.save(p2, quality=95, subsampling=0, optimize=True)

                out_files.extend([p1, p2])

            # -------- Horizontal (Top / Bottom) --------
            elif split_direction == 'horizontal':
                top_end = max(split_pos - margin, 1)
                bottom_start = min(split_pos + margin, height - 1)

                top = img.crop((0, 0, width, top_end))
                bottom = img.crop((0, bottom_start, width, height))

                p1 = os.path.join(output_dir, f"{base}_page1.jpg")
                p2 = os.path.join(output_dir, f"{base}_page2.jpg")

                top.save(p1, quality=95, subsampling=0, optimize=True)
                bottom.save(p2, quality=95, subsampling=0, optimize=True)

                out_files.extend([p1, p2])

            img.close()
            return out_files

        except Exception as e:
            self._log_err(f"Split error: {e}")
            return []

    # ----------------------------------------------------
    # REMOVE YELLOW OBJECTS (STICKERS)
    # ----------------------------------------------------

    def remove_fingers(self, image_path: str, output_path: Optional[str] = None) -> str:
        """
        Robust finger removal for scanned documents.
        Detects:
        - Side fingers
        - Top-center holding fingers (Indian skin tones)
        """

        try:
            img = self._safe_read_cv(image_path)
            if img is None:
                print(f"✋ [finger] could not read: {os.path.basename(image_path)}", flush=True)
                return image_path

            h, w = img.shape[:2]
            print(f"✋ [finger] start: {os.path.basename(image_path)} ({w}x{h})", flush=True)

            # ---------- YCrCb (better than HSV for Indian skin) ----------
            ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)

            lower = np.array([0, 135, 85])
            upper = np.array([255, 180, 135])
            skin_mask = cv2.inRange(ycrcb, lower, upper)
            skin_px = int(np.count_nonzero(skin_mask))
            print(f"✋ [finger] skin_mask: px={skin_px} ({(skin_px / float(h*w)):.4f})", flush=True)

            # ---------- Clean mask ----------
            kernel = np.ones((3, 3), np.uint8)
            skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, 1)
            skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, kernel, 1)

            contours, _ = cv2.findContours(
                skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            print(f"✋ [finger] contours: total={len(contours)}", flush=True)

            final_mask = np.zeros_like(skin_mask)

            min_area_global = h * w * 0.0008   # LOWERED
            max_area = h * w * 0.1

            edge_margin = int(0.12 * min(h, w))
            top_band = int(0.22 * h)  # BIGGER TOP ZONE

            accepted = 0
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < min_area_global or area > max_area:
                    continue

                x, y, cw, ch = cv2.boundingRect(cnt)

                # ---------- POSITION CHECK ----------
                near_edge = (
                    x < edge_margin or
                    x + cw > w - edge_margin or
                    y + ch > h - edge_margin
                )

                in_top_center = (
                    y < top_band and
                    x > w * 0.2 and
                    x + cw < w * 0.8
                )

                if not (near_edge or in_top_center):
                    continue

                # ---------- SHAPE (RELAXED) ----------
                aspect_ratio = max(cw / (ch + 1e-6), ch / (cw + 1e-6))
                if aspect_ratio < 1.1:  # relaxed
                    continue

                hull = cv2.convexHull(cnt)
                hull_area = cv2.contourArea(hull)
                if hull_area == 0:
                    continue

                solidity = area / hull_area
                if solidity < 0.45:  # relaxed
                    continue

                # ---------- TEXT SAFETY (SOFT) ----------
                roi = img[y:y+ch, x:x+cw]
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                edge_ratio = np.count_nonzero(
                    cv2.Canny(gray, 60, 140)
                ) / gray.size

                if edge_ratio > 0.18:  # allow some writing overlap
                    continue

                # ✅ ACCEPT AS FINGER
                cv2.drawContours(final_mask, [cnt], -1, 255, -1)
                accepted += 1

            mask_px = int(cv2.countNonZero(final_mask))
            print(f"✋ [finger] accepted={accepted} mask_px={mask_px}", flush=True)
            if mask_px == 0:
                # IMPORTANT: explicit message for debugging
                print(f"✋ [finger] not detected: {os.path.basename(image_path)} (mask empty)", flush=True)
                self._log_err("Finger not detected: mask empty")
                return image_path

            final_mask = cv2.dilate(
                final_mask, np.ones((9, 9), np.uint8), iterations=1
            )

            result = cv2.inpaint(img, final_mask, 3, cv2.INPAINT_TELEA)

            if output_path is None:
                output_path = image_path

            cv2.imwrite(output_path, result)
            print(f"✋ [finger] removed -> {os.path.basename(output_path)}", flush=True)
            return output_path

        except Exception as e:
            self._log_err(f"Finger removal error: {e}")
            print(f"✋ [finger] error: {e}", flush=True)
            return image_path

    # ----------------------------------------------------
    # LINE ORIENTATION DETECTION (FALLBACK)
    # ----------------------------------------------------

    def _get_line_orientation_scores(self, image: Image.Image) -> Tuple[int, int]:
        """
        Return counts of (horizontal_lines, vertical_lines).
        """
        try:
            img = np.array(image)
            if img.ndim == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            else:
                gray = img

            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            min_len = int(0.2 * min(gray.shape))
            lines = cv2.HoughLinesP(
                edges,
                1,
                np.pi / 180,
                threshold=100,
                minLineLength=max(50, min_len),
                maxLineGap=20
            )

            if lines is None:
                return 0, 0

            horiz = 0
            vert = 0

            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
                if angle > 90:
                    angle = 180 - angle

                if angle < 15:
                    horiz += 1
                elif angle > 75:
                    vert += 1

            return horiz, vert

        except Exception:
            return 0, 0

    def _detect_line_orientation(self, image: Image.Image) -> Optional[str]:
        """
        Detect dominant line orientation.
        Returns 'horizontal', 'vertical', or None.
        """
        try:
            horiz, vert = self._get_line_orientation_scores(image)
            if horiz == 0 and vert == 0:
                return None
            if vert > horiz * 1.3:
                return 'vertical'
            if horiz > vert * 1.3:
                return 'horizontal'
            return None
        except Exception:
            return None

    # ----------------------------------------------------
    # OCR ROTATION DETECTION (OPTIONAL)
    # ----------------------------------------------------

    def _detect_rotation_angle(self, image: Image.Image) -> Optional[int]:
        """
        Detect rotation angle using Tesseract OSD (offline).
        Returns clockwise angle.
        """
        if not _HAVE_TESSERACT:
            return None
        try:
            osd = pytesseract.image_to_osd(
                image, output_type=_tesseract_output.DICT
            )
            angle = int(osd.get('rotate', 0))
            return angle if angle in (0, 90, 180, 270) else None
        except Exception:
            return None

    # ----------------------------------------------------
    # AUTO ROTATE IMAGE
    # ----------------------------------------------------

    def auto_rotate_image(
        self,
        image_path: str,
        output_path: Optional[str] = None
    ) -> Tuple[str, bool]:
        """
        Auto-rotate image using EXIF, OCR, and fallback logic.
        Returns (path, rotated_flag)
        """
        try:
            img = self._safe_open_pil(image_path)
            if img is None:
                return image_path, False

            rotated_img = ImageOps.exif_transpose(img)
            rotated = rotated_img != img

            # OCR-based correction
            angle = self._detect_rotation_angle(rotated_img)
            if angle and angle in (90, 180, 270):
                rotated_img = rotated_img.rotate(-angle, expand=True)
                rotated = True
            else:
                # Fallback line-based detection
                orientation = self._detect_line_orientation(rotated_img)
                if orientation == 'vertical':
                    # Try both directions and pick the one that yields more horizontal lines.
                    ccw = rotated_img.rotate(90, expand=True)
                    cw = rotated_img.rotate(-90, expand=True)
                    ccw_h, ccw_v = self._get_line_orientation_scores(ccw)
                    cw_h, cw_v = self._get_line_orientation_scores(cw)

                    if ccw_h > cw_h:
                        rotated_img = ccw
                        rotated = True
                    elif cw_h > ccw_h:
                        rotated_img = cw
                        rotated = True
                    else:
                        # If tie, prefer orientation with fewer vertical lines
                        if ccw_v < cw_v:
                            rotated_img = ccw
                            rotated = True
                        elif cw_v < ccw_v:
                            rotated_img = cw
                            rotated = True

            if not rotated:
                img.close()
                return image_path, False

            if output_path is None:
                output_path = image_path

            ext = os.path.splitext(output_path)[1].lower()
            if ext in ('.jpg', '.jpeg'):
                rotated_img.save(output_path, quality=95, optimize=True)
            else:
                rotated_img.save(output_path)

            img.close()
            return output_path, True

        except Exception as e:
            self._log_err(f"Auto-rotate error: {e}")
            return image_path, False
    # ----------------------------------------------------
    # FULL AUTO PROCESS PIPELINE
    # ----------------------------------------------------

    def auto_process(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        auto_fix: bool = True
    ) -> Dict:
        """
        Automatically check and process image for all issues.
        DOES NOT change input/output contract.
        """

        result = {
            'checks': {},
            'fixes_applied': [],
            'processed_image_path': image_path,
            'split_images': [],
            'needs_attention': False,
            'warnings': [],
            'messages': [],
            'image_info': {}
        }

        messages = result['messages']

        if output_path is None:
            output_path = image_path

        # ---------------- AUTO ROTATE ----------------
        if auto_fix:
            rotated_path, rotated = self.auto_rotate_image(image_path, output_path)
            if rotated:
                image_path = rotated_path
                result['processed_image_path'] = rotated_path
                result['fixes_applied'].append('auto_rotated')

                if _HAVE_TESSERACT:
                    messages.append("🔄 Auto-rotated image (EXIF + OCR)")
                else:
                    messages.append("🔄 Auto-rotated image (EXIF + line detection)")

        # ---------------- IMAGE INFO ----------------
        result['image_info'] = self.get_image_info(image_path)

        # ---------------- RUN CHECKS ----------------
        blur_check = self.check_blur(image_path)
        cut_check = self.check_cut_edges(image_path)
        border_check = self.detect_borders(image_path)

        base_name = os.path.splitext(os.path.basename(image_path))[0]
        is_split_child = base_name.endswith('_page1') or base_name.endswith('_page2')

        if is_split_child:
            two_pages_check = {
                'is_two_pages': False,
                'split_direction': None,
                'split_position': None,
                'confidence': 0.0,
                'note': 'Skipping two-page detection for split image'
            }
        else:
            two_pages_check = self.detect_two_pages(image_path)

        result['checks']['blur'] = blur_check
        result['checks']['cut_edges'] = cut_check
        result['checks']['borders'] = border_check
        result['checks']['two_pages'] = two_pages_check

        # ---------------- WARNINGS ----------------
        if blur_check.get('is_blurry'):
            result['needs_attention'] = True
            result['warnings'].append('Image quality is not good')
            messages.append(
                f"⚠️ Image is blurry (score: {blur_check.get('blur_score', 0)})"
            )

        if two_pages_check.get('is_two_pages'):
            result['needs_attention'] = True
            result['warnings'].append('Two pages detected in one scan')
            messages.append(
                f"⚠️ Two pages detected ({two_pages_check.get('split_direction')}, "
                f"confidence: {two_pages_check.get('confidence', 0):.2f})"
            )
        else:
            messages.append("✅ Single page detected")

        # ---------------- AUTO FIXES ----------------
        processed_img = image_path

        if auto_fix:
            # ---- Split two pages ----
            if two_pages_check.get('is_two_pages'):
                try:
                    output_dir = os.path.dirname(image_path) or os.getcwd()
                    split_paths = self.split_two_pages(
                        image_path, output_dir, two_pages_check
                    )

                    if len(split_paths) == 2:
                        result['split_images'] = split_paths
                        result['fixes_applied'].append('split_two_pages')
                        messages.append(
                            f"✂️ Split into: {os.path.basename(split_paths[0])}, "
                            f"{os.path.basename(split_paths[1])}"
                        )
                    else:
                        result['warnings'].append('Could not split pages')
                        messages.append("❌ Failed to split pages")

                except Exception as e:
                    self._log_err(str(e))
                    result['warnings'].append('Split failed')

            # ---- Remove yellow objects ----
            processed_img = self.remove_yellow_objects(processed_img, output_path)
            if processed_img == output_path:
                result['fixes_applied'].append('removed_yellow_objects')
                messages.append("🟡 Removed yellow stickers")

            # ---- Remove fingers ----
            processed_img = self.remove_fingers(processed_img, output_path)
            if getattr(self, "_last_finger_removed", False):
                result['fixes_applied'].append('removed_fingers')
                messages.append("✋ Removed finger marks")

            # ---- Auto crop borders ----
            if border_check.get('borders_detected') and border_check.get('confidence', 0) > 0.5:
                try:
                    img = self._safe_open_pil(processed_img)
                    if img:
                        c = border_check['crop_coords']
                        cropped = img.crop((
                            c['x'],
                            c['y'],
                            c['x'] + c['width'],
                            c['y'] + c['height']
                        ))
                        cropped.save(output_path, quality=95, optimize=True)
                        processed_img = output_path
                        img.close()

                        result['fixes_applied'].append('auto_cropped_borders')
                        messages.append("✂️ Auto-cropped document borders")
                except Exception as e:
                    self._log_err(str(e))
                    result['warnings'].append('Border crop failed')

        # ---------------- FINALIZE ----------------
        result['processed_image_path'] = processed_img

        if result['fixes_applied']:
            messages.append(f"✅ Applied {len(result['fixes_applied'])} fix(es)")
        else:
            messages.append("✅ No fixes required")

        return result
