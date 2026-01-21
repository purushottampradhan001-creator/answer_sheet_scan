/**
 * Renderer Process - Frontend Logic with Image Editing
 */

let API_URL = 'http://127.0.0.1:5001';

// UI Elements
const btnComplete = document.getElementById('btn-complete');
const btnViewPdfs = document.getElementById('btn-view-pdfs');
const editorContainer = document.getElementById('editor-container');
const editorControls = document.getElementById('editor-controls');
const scannedGallery = document.getElementById('scanned-gallery');
const pdfGallery = document.getElementById('pdf-gallery');
const pdfPreview = document.getElementById('pdf-preview');
const pdfPreviewFrame = document.getElementById('pdf-preview-frame');
const pdfPreviewTitle = document.getElementById('pdf-preview-title');
const btnClosePreview = document.getElementById('btn-close-preview');
const messageContainer = document.getElementById('message-container');

// Tab elements
const tabButtons = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

// Editor controls
const rotateSlider = document.getElementById('rotate-slider');
const brightnessSlider = document.getElementById('brightness-slider');
const contrastSlider = document.getElementById('contrast-slider');
const rotateValue = document.getElementById('rotate-value');
const brightnessValue = document.getElementById('brightness-value');
const contrastValue = document.getElementById('contrast-value');
const btnRotate90 = document.getElementById('btn-rotate-90');
const btnRotate180 = document.getElementById('btn-rotate-180');
const btnApplyEdits = document.getElementById('btn-apply-edits');
const btnResetEdits = document.getElementById('btn-reset-edits');
const btnSaveImage = document.getElementById('btn-save-image');

// State
let currentAnswerCopyId = null;
let currentImages = [];
let scannedImages = [];
const imageCacheBusters = new Map();
let selectedImageIndex = -1;
let currentEditingImage = null;
let currentEditingCanvas = null;
let currentEditingCtx = null;
let originalImage = null;
let scannerPollInterval = null;
let imageAutoProcessingData = {}; // Store auto-processing data for each image
let imageAutoProcessingApplied = new Set(); // Track which images have had auto-processing applied
let imageFingerRemovalApplied = new Set(); // Track which images have had finger removal applied
let examDetails = {
    degree: null,
    subject: null,
    exam_date: null,
    college: null,
    unique_id: null
};
let cropState = {
    enabled: false,
    mode: 'single', // single | split
    splitDirection: null,
    selections: {
        primary: {
            startX: 0,
            startY: 0,
            endX: 0,
            endY: 0
        },
        secondary: {
            startX: 0,
            startY: 0,
            endX: 0,
            endY: 0
        }
    },
    isDragging: false,
    dragMode: null,
    activeHandle: null,
    activeSelection: 'primary',
    dragStartX: 0,
    dragStartY: 0,
    startXInitial: 0,
    startYInitial: 0,
    endXInitial: 0,
    endYInitial: 0
};

// Initialize
async function init() {
    // Get API URL
    if (window.electronAPI) {
        API_URL = await window.electronAPI.getApiUrl();
    }
    
    // Check backend health with retries
    let backendReady = false;
    for (let i = 0; i < 10; i++) {
        try {
            const response = await fetch(`${API_URL}/health`);
            if (response.ok) {
                backendReady = true;
                break;
            }
        } catch (error) {
            // Wait before retrying
            if (i < 9) {
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        }
    }
    
    if (!backendReady) {
        showMessage('Warning: Cannot connect to Python backend. Retrying...', 'warning');
        // Continue anyway - backend might start later
    }
    
    // Load saved exam details first (before auto-starting)
    await loadSavedExamDetails();
    
    // Auto-start answer copy
    await autoStartAnswerCopy();
    
    // Set up event listeners
    btnComplete.addEventListener('click', completeAnswerCopy);
    btnViewPdfs.addEventListener('click', () => switchTab('pdfs'));
    btnClosePreview.addEventListener('click', closePDFPreview);
    
    // Load scanned images
    await loadScannedImages();
    
    // Tab switching
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.dataset.tab;
            switchTab(tabName);
        });
    });
    
    // Settings event listeners
    const btnBrowseOutput = document.getElementById('btn-browse-output');
    const btnBrowseScanner = document.getElementById('btn-browse-scanner');
    const btnSaveSettings = document.getElementById('btn-save-settings');
    const btnResetSettings = document.getElementById('btn-reset-settings');
    
    if (btnBrowseOutput) {
        btnBrowseOutput.addEventListener('click', async () => {
            const folderPath = await window.electronAPI?.selectFolder();
            if (folderPath) {
                document.getElementById('output-path-input').value = folderPath;
                document.getElementById('output-path-display').textContent = `Current: ${folderPath}`;
            }
        });
    }
    
    if (btnBrowseScanner) {
        btnBrowseScanner.addEventListener('click', async () => {
            const folderPath = await window.electronAPI?.selectFolder();
            if (folderPath) {
                document.getElementById('scanner-path-input').value = folderPath;
                document.getElementById('scanner-path-display').textContent = `Current: ${folderPath}`;
            }
        });
    }
    
    if (btnSaveSettings) {
        btnSaveSettings.addEventListener('click', saveSettings);
    }
    
    if (btnResetSettings) {
        btnResetSettings.addEventListener('click', resetSettings);
    }
    
    // Editor controls
    rotateSlider.addEventListener('input', updateEditorPreview);
    brightnessSlider.addEventListener('input', updateEditorPreview);
    contrastSlider.addEventListener('input', updateEditorPreview);
    btnRotate90.addEventListener('click', () => {
        rotateSlider.value = (parseInt(rotateSlider.value) + 90) % 360;
        updateEditorPreview();
    });
    btnRotate180.addEventListener('click', () => {
        rotateSlider.value = (parseInt(rotateSlider.value) + 180) % 360;
        updateEditorPreview();
    });
    btnApplyEdits.addEventListener('click', applyEdits);
    btnResetEdits.addEventListener('click', resetEdits);
    
    // Crop functionality
    const btnCropToggle = document.getElementById('btn-crop-toggle');
    const btnCropClear = document.getElementById('btn-crop-clear');
    const btnCropContinue = document.getElementById('btn-crop-continue');
    const cropOverlay = document.getElementById('crop-overlay');
    
    if (btnCropToggle) {
        btnCropToggle.addEventListener('click', toggleCrop);
    }
    if (btnCropClear) {
        btnCropClear.addEventListener('click', clearCrop);
    }
    if (btnCropContinue) {
        btnCropContinue.addEventListener('click', continueCrop);
    }
    
    // Crop selection dragging - attach handlers to overlay and selections
    setupCropOverlayElements(cropOverlay);
    // Global mouse events for dragging
    document.addEventListener('mousemove', updateCropDrag);
    document.addEventListener('mouseup', endCropDrag);
    
    // Start polling for scanner images
    startScannerPolling();
    
    // Load PDFs
    loadPDFs();
    
    // Exam details modal handlers
    const examModal = document.getElementById('exam-details-modal');
    const btnCloseExamModal = document.getElementById('btn-close-exam-modal');
    const btnCancelExam = document.getElementById('btn-cancel-exam');
    const btnSaveExamDetails = document.getElementById('btn-save-exam-details');
    const examDetailsForm = document.getElementById('exam-details-form');
    
    if (btnCloseExamModal) {
        btnCloseExamModal.addEventListener('click', closeExamModal);
    }
    if (btnCancelExam) {
        btnCancelExam.addEventListener('click', closeExamModal);
    }
    if (btnSaveExamDetails) {
        btnSaveExamDetails.addEventListener('click', saveExamDetails);
    }
    
    // Close modal when clicking outside
    if (examModal) {
        examModal.addEventListener('click', (e) => {
            if (e.target === examModal) {
                closeExamModal();
            }
        });
    }
}

async function loadScannedImages() {
    try {
        const response = await fetch(`${API_URL}/list_scanner_images`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        
        scannedImages = data.images || [];
        updateScannedGallery();
        
        // Select last image by default
        if (scannedImages.length > 0) {
            selectedImageIndex = scannedImages.length - 1;
            await loadImageForPreview(scannedImages[selectedImageIndex].path);
            updateScannedGallery();
        }
        
        // Update UI to enable/disable buttons based on image count
        updateUI();
    } catch (error) {
        console.error('Error loading scanned images:', error);
        // Don't show error if backend is just starting up - it's not critical
        if (scannedImages.length === 0) {
            scannedGallery.innerHTML = '<div class="empty-state-small"><p>No images found. Scanner folder will be checked automatically.</p></div>';
        }
        // Still update UI even on error
        updateUI();
    }
}

function updateScannedGallery() {
    // Update image count badge
    const imageCountBadge = document.getElementById('image-count-badge');
    if (imageCountBadge) {
        imageCountBadge.textContent = scannedImages.length;
    }
    
    if (scannedImages.length === 0) {
        scannedGallery.innerHTML = '<div class="empty-state-small"><p>No image found</p></div>';
        return;
    }
    
    scannedGallery.innerHTML = scannedImages.map((img, index) => {
        const cacheBust = imageCacheBusters.get(img.path);
        const src = `file://${img.path.replace(/\\/g, '/')}${cacheBust ? `?v=${cacheBust}` : ''}`;
        return `
        <div class="scanned-gallery-item ${index === selectedImageIndex ? 'selected' : ''}" 
             onclick="selectScannedImage(${index})">
            <img src="${src}" alt="${img.filename}" 
                 onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'200\\' height=\\'150\\'%3E%3Crect fill=\\'%23ddd\\' width=\\'200\\' height=\\'150\\'/%3E%3Ctext x=\\'50%25\\' y=\\'50%25\\' text-anchor=\\'middle\\' dy=\\'.3em\\' fill=\\'%23999\\'%3EImage%3C/text%3E%3C/svg%3E'">
            <div class="scanned-gallery-item-info">${img.filename}</div>
            <button class="scanned-gallery-item-delete" onclick="event.stopPropagation(); deleteScannedImage(${index})" title="Delete image">
                ×
            </button>
        </div>
    `}).join('');
}

async function selectScannedImage(index) {
    if (index < 0 || index >= scannedImages.length) return;
    
    selectedImageIndex = index;
    await loadImageForPreview(scannedImages[index].path);
    updateScannedGallery();
}

async function deleteScannedImage(index) {
    if (index < 0 || index >= scannedImages.length) return;
    
    const imageToDelete = scannedImages[index];
    
    // Confirm deletion
    if (!confirm(`Are you sure you want to delete "${imageToDelete.filename}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/delete_scanner_image`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                path: imageToDelete.path
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage(`Image "${imageToDelete.filename}" deleted successfully`, 'success');
            
            // If the deleted image was currently selected, clear the preview
            if (selectedImageIndex === index) {
                clearImagePreview();
                selectedImageIndex = -1;
            } else if (selectedImageIndex > index) {
                // Adjust selected index if a previous image was deleted
                selectedImageIndex--;
            }
            
            // Reload scanned images to update the list
            await loadScannedImages();
        } else {
            showMessage(data.error || 'Failed to delete image', 'error');
        }
    } catch (error) {
        console.error('Error deleting image:', error);
        showMessage(`Error deleting image: ${error.message}`, 'error');
    }
}

async function loadImageForPreview(imagePath) {
    try {
        // Ensure path is absolute (backend should return absolute paths)
        // Check if path is relative (doesn't start with / on Unix or drive letter on Windows)
        let normalizedPath = imagePath;
        if (imagePath && !imagePath.startsWith('/') && !imagePath.match(/^[A-Za-z]:/)) {
            console.warn('Received relative path from backend:', imagePath);
            // Try to construct absolute path - this is a fallback
            // Backend should be fixed to return absolute paths
        }
        
        // Read file using Electron API if available
        let imageBlob;
        if (window.electronAPI) {
            const fileData = await window.electronAPI.readFile(normalizedPath);
            if (fileData.success) {
                imageBlob = new Blob([fileData.data]);
            } else {
                throw new Error(fileData.error);
            }
        } else {
            // Fallback - try to fetch
            const response = await fetch(`file://${normalizedPath}`);
            imageBlob = await response.blob();
        }
        
        // Create object URL for image
        const imageUrl = URL.createObjectURL(imageBlob);
        
        // Load image into preview
        const img = new Image();
        
        img.onload = () => {
            // Create canvas
            if (currentEditingCanvas) {
                currentEditingCanvas.remove();
            }
            
            currentEditingCanvas = document.createElement('canvas');
            currentEditingCanvas.width = img.width;
            currentEditingCanvas.height = img.height;
            currentEditingCtx = currentEditingCanvas.getContext('2d');
            
            // Draw original image
            currentEditingCtx.drawImage(img, 0, 0);
            originalImage = img;
            currentEditingImage = imagePath;
            
            // Show in editor while preserving crop overlay
            let existingOverlay = document.getElementById('crop-overlay');
            editorContainer.innerHTML = '';
            editorContainer.appendChild(currentEditingCanvas);
            if (!existingOverlay) {
                existingOverlay = createCropOverlay();
            }
            editorContainer.appendChild(existingOverlay);
            setupCropOverlayElements(existingOverlay);
            editorControls.style.display = 'block';
            
            // Reset sliders
            resetEdits();
            
            // Display auto-processing info and run auto-processing on load
            displayAutoProcessingInfo(imagePath);
            
            // Clean up object URL
            URL.revokeObjectURL(imageUrl);
        };
        
        img.onerror = () => {
            showMessage('Error loading image for preview', 'error');
            URL.revokeObjectURL(imageUrl);
        };
        
        img.src = imageUrl;
        
    } catch (error) {
        console.error('Error loading image:', error);
        showMessage(`Error loading image: ${error.message}`, 'error');
    }
}

async function displayAutoProcessingInfo(imagePath) {
    /**
     * Display auto-processing information for the current image.
     * This is called when an image is loaded for preview.
     * 
     * @param {string} imagePath - Path to the image
     */
    const panel = document.getElementById('auto-processing-panel');
    const content = document.getElementById('auto-processing-content');
    
    if (!panel || !content) {
        console.warn('Auto-processing panel elements not found');
        return;
    }
    
    // Hide auto-processing panel/messages
    panel.style.display = 'none';
    content.innerHTML = '';
    
    try {
        if (!imageFingerRemovalApplied.has(imagePath)) {
            const fingerResponse = await fetch(`${API_URL}/remove_fingers`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    image_path: imagePath,
                    output_path: imagePath
                })
            });

            if (fingerResponse.ok) {
                const fingerData = await fingerResponse.json();
                if (fingerData.success) {
                    imageFingerRemovalApplied.add(imagePath);
                    imageCacheBusters.set(imagePath, Date.now());
                    updateScannedGallery();
                    await loadImageForPreview(imagePath);
                    return;
                }
            }
        }

        const hasBeenProcessed = imageAutoProcessingApplied.has(imagePath);
        
        const checkResponse = await fetch(`${API_URL}/auto_check_image`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image_path: imagePath
            })
        });
        
        if (!checkResponse.ok) {
            throw new Error(`HTTP ${checkResponse.status}`);
        }
        
        const checkData = await checkResponse.json();
        
        if (!checkData.success) {
            throw new Error(checkData.error || 'Auto-check failed');
        }
        
        // Store the processing data for this image
        imageAutoProcessingData[imagePath] = checkData;
        
        const twoPagesInfo = checkData.checks?.two_pages;
        if (twoPagesInfo && twoPagesInfo.is_two_pages) {
            enableSplitCrop(twoPagesInfo);
            content.innerHTML = '';
            return;
        }
        
        if (!hasBeenProcessed) {
            const response = await fetch(`${API_URL}/auto_process_image`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    image_path: imagePath
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.error || 'Auto-processing failed');
            }
            
            // Mark this image as processed when auto-processing was run
            imageAutoProcessingApplied.add(imagePath);
            
            // If image was split, mark split images as processed too
            if (data.split_images && data.split_images.length > 0) {
                data.split_images.forEach(splitPath => {
                    imageAutoProcessingApplied.add(splitPath);
                });

                // Refresh gallery to remove the original and show split images
                await loadScannedImages();
            }
        }
        
        // Do not display any auto-processing messages
        content.innerHTML = '';
        
    } catch (error) {
        console.error('Error fetching auto-processing info:', error);
        // Suppress UI errors for auto-processing panel
        content.innerHTML = '';
    }
}


function switchTab(tabName) {
    tabButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    tabContents.forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tabName}`);
    });
    
    // Clear image preview when switching away from images tab
    if (tabName !== 'images' && currentEditingCanvas) {
        clearImagePreview();
    }
    
    if (tabName === 'pdfs') {
        loadPDFs();
    } else if (tabName === 'settings') {
        loadSettings();
    }
}

async function loadCurrentStatus() {
    try {
        const response = await fetch(`${API_URL}/get_current_status`);
        const data = await response.json();
        
        if (data.active) {
            currentAnswerCopyId = data.answer_copy_id;
            currentImages = data.images || [];
            updateUI();
        }
    } catch (error) {
        console.error('Error loading status:', error);
    }
}

function startScannerPolling() {
    // Poll every 2 seconds for new scanner images
    scannerPollInterval = setInterval(async () => {
        await checkForNewScannerImages();
    }, 2000);
}

let processedScannerImages = new Set();

async function checkForNewScannerImages() {
    try {
        // Reload scanned images to check for new ones
        const response = await fetch(`${API_URL}/list_scanner_images`);
        const data = await response.json();
        
        const newImageCount = data.images?.length || 0;
        if (newImageCount > scannedImages.length) {
            // New images detected, reload gallery
            scannedImages = data.images || [];
            updateScannedGallery();
            
            // Select last image (newest)
            if (scannedImages.length > 0) {
                selectedImageIndex = scannedImages.length - 1;
                await loadImageForPreview(scannedImages[selectedImageIndex].path);
                updateScannedGallery();
                showMessage(`New image detected: ${scannedImages[selectedImageIndex].filename}`, 'success');
            }
            
            // Update UI to enable/disable buttons
            updateUI();
        } else if (newImageCount !== scannedImages.length) {
            // Image count changed (might have been deleted)
            scannedImages = data.images || [];
            updateScannedGallery();
            updateUI();
        }
    } catch (error) {
        console.error('Error checking scanner images:', error);
    }
}


function updateEditorPreview() {
    if (!currentEditingCanvas || !originalImage) return;
    
    // Update value displays
    rotateValue.textContent = `${rotateSlider.value}°`;
    brightnessValue.textContent = `${brightnessSlider.value}%`;
    contrastValue.textContent = `${contrastSlider.value}%`;
    
    // Apply preview (simplified - full implementation would use image processing)
    const canvas = currentEditingCanvas;
    const ctx = currentEditingCtx;
    
    // Clear and redraw
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    
    // Apply transformations
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    
    ctx.translate(centerX, centerY);
    ctx.rotate((parseInt(rotateSlider.value) * Math.PI) / 180);
    ctx.translate(-centerX, -centerY);
    
    // Apply brightness/contrast filters
    ctx.filter = `brightness(${brightnessSlider.value}%) contrast(${contrastSlider.value}%)`;
    
    ctx.drawImage(originalImage, 0, 0);
    ctx.restore();
}

function resetEdits() {
    if (!rotateSlider || !brightnessSlider || !contrastSlider) return;
    
    rotateSlider.value = 0;
    brightnessSlider.value = 100;
    contrastSlider.value = 100;
    
    // Clear crop
    clearCrop();
    
    // Reload original image
    if (originalImage && currentEditingCanvas && currentEditingCtx) {
        currentEditingCtx.clearRect(0, 0, currentEditingCanvas.width, currentEditingCanvas.height);
        currentEditingCtx.drawImage(originalImage, 0, 0);
    }
    
    updateEditorPreview();
    showMessage('All edits reset', 'info');
}

async function applyEdits() {
    if (!currentEditingImage || !currentEditingCanvas || !originalImage) {
        showMessage('No image to edit', 'warning');
        return;
    }
    
    try {
        if (cropState.mode === 'split') {
            await applySplitCropSelections();
            return;
        }

        const rotateDegrees = parseInt(rotateSlider.value, 10) || 0;
        const brightnessFactor = (parseInt(brightnessSlider.value, 10) || 100) / 100;
        const contrastFactor = (parseInt(contrastSlider.value, 10) || 100) / 100;

        const edits = {};
        if (rotateDegrees !== 0) edits.rotate = rotateDegrees;
        if (brightnessFactor !== 1) edits.brightness = brightnessFactor;
        if (contrastFactor !== 1) edits.contrast = contrastFactor;

        // Apply crop only when no rotation is requested to avoid coord mismatch.
        if (rotateDegrees === 0 && cropState.enabled && selectionHasArea(cropState.selections.primary)) {
            const crop = computeCropCoordsFromSelection(cropState.selections.primary);
            if (crop) edits.crop = crop;
        }

        if (Object.keys(edits).length === 0) {
            showMessage('No edits to apply', 'info');
            return;
        }

        const response = await fetch(`${API_URL}/apply_scanner_image_edits`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image_path: currentEditingImage,
                edits
            })
        });

        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to apply edits');
        }

        imageCacheBusters.set(currentEditingImage, Date.now());
        updateScannedGallery();
        showMessage('Edits applied successfully', 'success');
        await loadImageForPreview(currentEditingImage);
    } catch (error) {
        showMessage(`Error applying edits: ${error.message}`, 'error');
        console.error('Apply edits error:', error);
    }
}

async function continueCrop() {
    if (!currentEditingCanvas || !originalImage) {
        showMessage('No image to crop', 'warning');
        return;
    }
    
    if (cropState.mode === 'split') {
        await applySplitCropSelections();
        return;
    }
    
    updateEditorPreview();
    await applyCropSelection({ requireSelection: true });
}

async function applyCropSelection({ requireSelection = false } = {}) {
    if (cropState.mode === 'split') {
        return null;
    }
    
    const cropSelection = document.getElementById('crop-selection');
    if (!cropState.enabled || !cropSelection || !currentEditingCanvas || !editorContainer) {
        return requireSelection ? false : null;
    }
    
    const selectionState = cropState.selections.primary;
    const hasSelection = selectionState.startX !== selectionState.endX && selectionState.startY !== selectionState.endY;
    if (!hasSelection) {
        if (requireSelection) {
            showMessage('Adjust the crop box before continuing', 'warning');
            return false;
        }
        return null;
    }
    
    // Get the canvas position within the container
    const containerRect = editorContainer.getBoundingClientRect();
    const canvasRect = currentEditingCanvas.getBoundingClientRect();
    
    // Calculate the actual canvas position within container (centered)
    const canvasOffsetX = (containerRect.width - canvasRect.width) / 2;
    const canvasOffsetY = (containerRect.height - canvasRect.height) / 2;
    
    // Get crop coordinates relative to container
    const left = Math.min(selectionState.startX, selectionState.endX);
    const top = Math.min(selectionState.startY, selectionState.endY);
    const width = Math.abs(selectionState.endX - selectionState.startX);
    const height = Math.abs(selectionState.endY - selectionState.startY);
    
    // Convert to canvas coordinates
    const cropX = Math.max(0, left - canvasOffsetX);
    const cropY = Math.max(0, top - canvasOffsetY);
    const cropWidth = Math.min(canvasRect.width - cropX, width);
    const cropHeight = Math.min(canvasRect.height - cropY, height);
    
    if (cropWidth <= 0 || cropHeight <= 0) {
        showMessage('Invalid crop selection', 'warning');
        return false;
    }
    
    // Calculate scale factors
    const scaleX = currentEditingCanvas.width / canvasRect.width;
    const scaleY = currentEditingCanvas.height / canvasRect.height;
    
    // Convert to actual canvas pixel coordinates
    const actualCropX = cropX * scaleX;
    const actualCropY = cropY * scaleY;
    const actualCropWidth = cropWidth * scaleX;
    const actualCropHeight = cropHeight * scaleY;
    
    // Create new canvas with cropped image
    const croppedCanvas = document.createElement('canvas');
    croppedCanvas.width = actualCropWidth;
    croppedCanvas.height = actualCropHeight;
    const croppedCtx = croppedCanvas.getContext('2d');
    
    // Draw cropped portion
    croppedCtx.drawImage(
        currentEditingCanvas,
        actualCropX, actualCropY, actualCropWidth, actualCropHeight,
        0, 0, actualCropWidth, actualCropHeight
    );
    
    return await new Promise((resolve) => {
        // Replace current canvas with cropped version
        currentEditingCanvas.width = actualCropWidth;
        currentEditingCanvas.height = actualCropHeight;
        currentEditingCtx.clearRect(0, 0, actualCropWidth, actualCropHeight);
        currentEditingCtx.drawImage(croppedCanvas, 0, 0);
        
        // Update original image reference
        const img = new Image();
        img.onload = () => {
            originalImage = img;
            clearCrop();
            updateEditorPreview();
            showMessage('Crop applied successfully', 'success');
            resolve(true);
        };
        img.onerror = () => {
            showMessage('Error applying crop', 'error');
            resolve(false);
        };
        img.src = croppedCanvas.toDataURL();
    });
}

function computeCropCoordsFromSelection(selectionState) {
    if (!currentEditingCanvas || !editorContainer) return null;
    const containerRect = editorContainer.getBoundingClientRect();
    const canvasRect = currentEditingCanvas.getBoundingClientRect();
    
    // Calculate the actual canvas position within container (centered)
    const canvasOffsetX = (containerRect.width - canvasRect.width) / 2;
    const canvasOffsetY = (containerRect.height - canvasRect.height) / 2;
    
    const left = Math.min(selectionState.startX, selectionState.endX);
    const top = Math.min(selectionState.startY, selectionState.endY);
    const width = Math.abs(selectionState.endX - selectionState.startX);
    const height = Math.abs(selectionState.endY - selectionState.startY);
    
    const cropX = Math.max(0, left - canvasOffsetX);
    const cropY = Math.max(0, top - canvasOffsetY);
    const cropWidth = Math.min(canvasRect.width - cropX, width);
    const cropHeight = Math.min(canvasRect.height - cropY, height);
    
    if (cropWidth <= 0 || cropHeight <= 0) {
        return null;
    }
    
    const scaleX = currentEditingCanvas.width / canvasRect.width;
    const scaleY = currentEditingCanvas.height / canvasRect.height;
    
    return {
        x: Math.round(cropX * scaleX),
        y: Math.round(cropY * scaleY),
        width: Math.round(cropWidth * scaleX),
        height: Math.round(cropHeight * scaleY)
    };
}

async function applySplitCropSelections() {
    if (!currentEditingImage || !currentEditingCanvas) {
        showMessage('No image to split', 'warning');
        return;
    }
    
    const primary = cropState.selections.primary;
    const secondary = cropState.selections.secondary;
    
    if (!selectionHasArea(primary) || !selectionHasArea(secondary)) {
        showMessage('Adjust both crop boxes before continuing', 'warning');
        return;
    }
    
    const primaryCrop = computeCropCoordsFromSelection(primary);
    const secondaryCrop = computeCropCoordsFromSelection(secondary);
    
    if (!primaryCrop || !secondaryCrop) {
        showMessage('Invalid split selection', 'warning');
        return;
    }
    
    const crops = [primaryCrop, secondaryCrop];
    if (cropState.splitDirection === 'vertical') {
        crops.sort((a, b) => a.x - b.x);
    } else if (cropState.splitDirection === 'horizontal') {
        crops.sort((a, b) => a.y - b.y);
    }
    
    try {
        const response = await fetch(`${API_URL}/split_image_with_crops`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image_path: currentEditingImage,
                crops
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Split failed');
        }
        
        showMessage('Image split into 2 pages', 'success');
        clearImagePreview();
        await loadScannedImages();
    } catch (error) {
        console.error('Split image error:', error);
        showMessage(`Error splitting image: ${error.message}`, 'error');
    }
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function getSelectionElement(selectionKey) {
    if (selectionKey === 'secondary') {
        return document.getElementById('crop-selection-secondary');
    }
    return document.getElementById('crop-selection');
}

function getSelectionState(selectionKey) {
    return cropState.selections[selectionKey] || cropState.selections.primary;
}

function selectionHasArea(selectionState) {
    return selectionState.startX !== selectionState.endX && selectionState.startY !== selectionState.endY;
}

function initializeCropSelectionToCanvas() {
    if (!currentEditingCanvas || !editorContainer) return;
    const containerRect = editorContainer.getBoundingClientRect();
    const canvasRect = currentEditingCanvas.getBoundingClientRect();
    
    const left = clamp(canvasRect.left - containerRect.left, 0, containerRect.width);
    const top = clamp(canvasRect.top - containerRect.top, 0, containerRect.height);
    const right = clamp(left + canvasRect.width, 0, containerRect.width);
    const bottom = clamp(top + canvasRect.height, 0, containerRect.height);
    
    cropState.mode = 'single';
    const primary = cropState.selections.primary;
    primary.startX = left;
    primary.startY = top;
    primary.endX = right;
    primary.endY = bottom;
    
    updateCropSelection();
}

function updateCropContinueState() {
    const btnCropContinue = document.getElementById('btn-crop-continue');
    if (!btnCropContinue) return;
    if (!cropState.enabled) {
        btnCropContinue.disabled = true;
        return;
    }
    
    if (cropState.mode === 'split') {
        const primary = cropState.selections.primary;
        const secondary = cropState.selections.secondary;
        btnCropContinue.disabled = !(selectionHasArea(primary) && selectionHasArea(secondary));
        return;
    }
    
    const hasSelection = selectionHasArea(cropState.selections.primary);
    btnCropContinue.disabled = !hasSelection;
}

function enableSplitCrop(twoPagesInfo) {
    if (!currentEditingCanvas || !editorContainer) return;
    
    cropState.enabled = true;
    cropState.mode = 'split';
    cropState.splitDirection = twoPagesInfo.split_direction || null;
    
    const cropOverlay = document.getElementById('crop-overlay');
    const btnCropClear = document.getElementById('btn-crop-clear');
    const btnCropToggle = document.getElementById('btn-crop-toggle');
    const btnCropContinue = document.getElementById('btn-crop-continue');
    
    setupCropOverlayElements(cropOverlay);
    
    if (cropOverlay) {
        cropOverlay.style.display = 'block';
        cropOverlay.classList.add('active');
    }
    if (btnCropClear) btnCropClear.style.display = 'inline-flex';
    if (btnCropContinue) btnCropContinue.style.display = 'inline-flex';
    if (btnCropToggle) {
        btnCropToggle.style.background = 'var(--primary-color)';
        btnCropToggle.style.color = 'white';
    }
    
    const primaryElement = getSelectionElement('primary');
    const secondaryElement = getSelectionElement('secondary');
    if (primaryElement) {
        primaryElement.style.display = 'block';
    }
    if (secondaryElement) {
        secondaryElement.style.display = 'block';
    }
    
    const containerRect = editorContainer.getBoundingClientRect();
    const canvasRect = currentEditingCanvas.getBoundingClientRect();
    const canvasLeft = clamp(canvasRect.left - containerRect.left, 0, containerRect.width);
    const canvasTop = clamp(canvasRect.top - containerRect.top, 0, containerRect.height);
    const canvasRight = clamp(canvasLeft + canvasRect.width, 0, containerRect.width);
    const canvasBottom = clamp(canvasTop + canvasRect.height, 0, containerRect.height);
    
    const scaleX = canvasRect.width / currentEditingCanvas.width;
    const scaleY = canvasRect.height / currentEditingCanvas.height;
    const splitPosition = twoPagesInfo.split_position || 0;
    
    if (twoPagesInfo.split_direction === 'vertical') {
        const splitX = clamp(canvasLeft + splitPosition * scaleX, canvasLeft + 1, canvasRight - 1);
        cropState.selections.primary = {
            startX: canvasLeft,
            startY: canvasTop,
            endX: splitX,
            endY: canvasBottom
        };
        cropState.selections.secondary = {
            startX: splitX,
            startY: canvasTop,
            endX: canvasRight,
            endY: canvasBottom
        };
    } else {
        const splitY = clamp(canvasTop + splitPosition * scaleY, canvasTop + 1, canvasBottom - 1);
        cropState.selections.primary = {
            startX: canvasLeft,
            startY: canvasTop,
            endX: canvasRight,
            endY: splitY
        };
        cropState.selections.secondary = {
            startX: canvasLeft,
            startY: splitY,
            endX: canvasRight,
            endY: canvasBottom
        };
    }
    
    updateCropSelection();
    showMessage('Two pages detected - adjust both boxes, then click Continue', 'info');
}

function createCropOverlay() {
    const overlay = document.createElement('div');
    overlay.id = 'crop-overlay';
    overlay.className = 'crop-overlay';
    overlay.style.display = 'none';
    
    const primary = createCropSelectionElement('primary');
    const secondary = createCropSelectionElement('secondary');
    secondary.style.display = 'none';
    
    overlay.appendChild(primary);
    overlay.appendChild(secondary);
    
    setupCropOverlayElements(overlay);
    
    return overlay;
}

function createCropSelectionElement(selectionKey) {
    const selection = document.createElement('div');
    selection.id = selectionKey === 'secondary' ? 'crop-selection-secondary' : 'crop-selection';
    selection.className = 'crop-selection';
    selection.dataset.selection = selectionKey;
    
    const handles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
    handles.forEach(handleName => {
        const handle = document.createElement('div');
        handle.className = `crop-handle handle-${handleName}`;
        handle.dataset.handle = handleName;
        selection.appendChild(handle);
    });
    
    return selection;
}

function setupCropOverlayElements(overlayElement) {
    const overlay = overlayElement || document.getElementById('crop-overlay');
    if (!overlay) return;
    
    if (!overlay.dataset.listenersBound) {
        overlay.addEventListener('mousedown', startCropDrag);
        overlay.dataset.listenersBound = 'true';
    }
    
    let primary = document.getElementById('crop-selection');
    if (!primary) {
        primary = createCropSelectionElement('primary');
        overlay.appendChild(primary);
    }
    if (!primary.dataset.selection) {
        primary.dataset.selection = 'primary';
    }
    bindSelectionEvents(primary);
    
    let secondary = document.getElementById('crop-selection-secondary');
    if (!secondary) {
        secondary = createCropSelectionElement('secondary');
        secondary.style.display = 'none';
        overlay.appendChild(secondary);
    }
    if (!secondary.dataset.selection) {
        secondary.dataset.selection = 'secondary';
    }
    bindSelectionEvents(secondary);
}

function bindSelectionEvents(selection) {
    if (!selection || selection.dataset.listenersBound) return;
    selection.addEventListener('mousedown', startCropMove);
    selection.querySelectorAll('.crop-handle').forEach(handle => {
        handle.addEventListener('mousedown', (e) => startCropResize(e, handle.dataset.handle));
    });
    selection.dataset.listenersBound = 'true';
}

function startCropMove(e) {
    if (!cropState.enabled || !currentEditingCanvas || !editorContainer) return;
    if (e.target && e.target.classList.contains('crop-handle')) return;
    
    e.preventDefault();
    e.stopPropagation();
    const selectionKey = e.currentTarget?.dataset?.selection || 'primary';
    cropState.activeSelection = selectionKey;
    const selectionState = getSelectionState(selectionKey);
    const left = Math.min(selectionState.startX, selectionState.endX);
    const right = Math.max(selectionState.startX, selectionState.endX);
    const top = Math.min(selectionState.startY, selectionState.endY);
    const bottom = Math.max(selectionState.startY, selectionState.endY);
    selectionState.startX = left;
    selectionState.endX = right;
    selectionState.startY = top;
    selectionState.endY = bottom;
    cropState.isDragging = true;
    cropState.dragMode = 'move';
    cropState.activeHandle = null;
    
    cropState.dragStartX = e.clientX;
    cropState.dragStartY = e.clientY;
    cropState.startXInitial = selectionState.startX;
    cropState.startYInitial = selectionState.startY;
    cropState.endXInitial = selectionState.endX;
    cropState.endYInitial = selectionState.endY;
}

function startCropResize(e, handle) {
    if (!cropState.enabled || !currentEditingCanvas || !editorContainer) return;
    if (!handle) return;
    
    e.preventDefault();
    e.stopPropagation();
    const selectionKey = e.currentTarget?.parentElement?.dataset?.selection || 'primary';
    cropState.activeSelection = selectionKey;
    const selectionState = getSelectionState(selectionKey);
    const left = Math.min(selectionState.startX, selectionState.endX);
    const right = Math.max(selectionState.startX, selectionState.endX);
    const top = Math.min(selectionState.startY, selectionState.endY);
    const bottom = Math.max(selectionState.startY, selectionState.endY);
    selectionState.startX = left;
    selectionState.endX = right;
    selectionState.startY = top;
    selectionState.endY = bottom;
    cropState.isDragging = true;
    cropState.dragMode = 'resize';
    cropState.activeHandle = handle;
    
    cropState.dragStartX = e.clientX;
    cropState.dragStartY = e.clientY;
    cropState.startXInitial = selectionState.startX;
    cropState.startYInitial = selectionState.startY;
    cropState.endXInitial = selectionState.endX;
    cropState.endYInitial = selectionState.endY;
}

function toggleCrop() {
    if (!currentEditingCanvas || !editorContainer) {
        showMessage('Load an image before cropping', 'warning');
        return;
    }
    
    cropState.enabled = !cropState.enabled;
    cropState.mode = 'single';
    cropState.splitDirection = null;
    const cropOverlay = document.getElementById('crop-overlay');
    const btnCropClear = document.getElementById('btn-crop-clear');
    const btnCropToggle = document.getElementById('btn-crop-toggle');
    const btnCropContinue = document.getElementById('btn-crop-continue');
    
    if (cropState.enabled) {
        if (cropOverlay) {
            cropOverlay.style.display = 'block';
            cropOverlay.classList.add('active');
        }
        if (btnCropClear) btnCropClear.style.display = 'inline-flex';
        if (btnCropContinue) btnCropContinue.style.display = 'inline-flex';
        if (btnCropToggle) {
            btnCropToggle.style.background = 'var(--primary-color)';
            btnCropToggle.style.color = 'white';
        }
        initializeCropSelectionToCanvas();
        updateCropContinueState();
        showMessage('Adjust the red dotted box, then click Continue to crop', 'info');
    } else {
        if (btnCropToggle) {
            btnCropToggle.style.background = '';
            btnCropToggle.style.color = '';
        }
        clearCrop();
    }
}

function clearCrop() {
    cropState.enabled = false;
    cropState.mode = 'single';
    cropState.splitDirection = null;
    cropState.activeSelection = 'primary';
    cropState.selections.primary = {
        startX: 0,
        startY: 0,
        endX: 0,
        endY: 0
    };
    cropState.selections.secondary = {
        startX: 0,
        startY: 0,
        endX: 0,
        endY: 0
    };
    cropState.isDragging = false;
    cropState.dragMode = null;
    cropState.activeHandle = null;
    
    const cropOverlay = document.getElementById('crop-overlay');
    const cropSelection = document.getElementById('crop-selection');
    const cropSelectionSecondary = document.getElementById('crop-selection-secondary');
    const btnCropClear = document.getElementById('btn-crop-clear');
    const btnCropToggle = document.getElementById('btn-crop-toggle');
    const btnCropContinue = document.getElementById('btn-crop-continue');
    
    if (cropOverlay) {
        cropOverlay.style.display = 'none';
        cropOverlay.classList.remove('active');
    }
    if (cropSelection) {
        cropSelection.style.left = '0px';
        cropSelection.style.top = '0px';
        cropSelection.style.width = '0px';
        cropSelection.style.height = '0px';
    }
    if (cropSelectionSecondary) {
        cropSelectionSecondary.style.left = '0px';
        cropSelectionSecondary.style.top = '0px';
        cropSelectionSecondary.style.width = '0px';
        cropSelectionSecondary.style.height = '0px';
        cropSelectionSecondary.style.display = 'none';
    }
    if (btnCropClear) btnCropClear.style.display = 'none';
    if (btnCropContinue) btnCropContinue.style.display = 'none';
    if (btnCropToggle) {
        btnCropToggle.style.background = '';
        btnCropToggle.style.color = '';
    }
}

function startCropDrag(e) {
    if (!cropState.enabled || !currentEditingCanvas || !editorContainer) return;
    if (cropState.mode === 'split') return;
    if (e.target && e.target.id !== 'crop-overlay') return;
    
    e.preventDefault();
    e.stopPropagation();
    cropState.isDragging = true;
    cropState.dragMode = 'select';
    cropState.activeHandle = null;
    cropState.activeSelection = 'primary';
    
    // Get the actual canvas position within the container
    const containerRect = editorContainer.getBoundingClientRect();
    
    // Calculate position relative to the container (where overlay is positioned)
    const selectionState = cropState.selections.primary;
    selectionState.startX = e.clientX - containerRect.left;
    selectionState.startY = e.clientY - containerRect.top;
    selectionState.endX = selectionState.startX;
    selectionState.endY = selectionState.startY;
    
    cropState.dragStartX = e.clientX;
    cropState.dragStartY = e.clientY;
    cropState.startXInitial = selectionState.startX;
    cropState.startYInitial = selectionState.startY;
    cropState.endXInitial = selectionState.endX;
    cropState.endYInitial = selectionState.endY;
    
    updateCropSelection();
}

function updateCropDrag(e) {
    if (!cropState.isDragging || !currentEditingCanvas || !editorContainer) return;
    
    const containerRect = editorContainer.getBoundingClientRect();
    const minSize = 20;
    const dx = e.clientX - cropState.dragStartX;
    const dy = e.clientY - cropState.dragStartY;
    const selectionState = getSelectionState(cropState.activeSelection);
    
    if (cropState.dragMode === 'move') {
        const width = cropState.endXInitial - cropState.startXInitial;
        const height = cropState.endYInitial - cropState.startYInitial;
        const newStartX = clamp(cropState.startXInitial + dx, 0, containerRect.width - width);
        const newStartY = clamp(cropState.startYInitial + dy, 0, containerRect.height - height);
        selectionState.startX = newStartX;
        selectionState.startY = newStartY;
        selectionState.endX = newStartX + width;
        selectionState.endY = newStartY + height;
    } else if (cropState.dragMode === 'resize' && cropState.activeHandle) {
        let left = cropState.startXInitial;
        let right = cropState.endXInitial;
        let top = cropState.startYInitial;
        let bottom = cropState.endYInitial;
        
        if (cropState.activeHandle.includes('w')) {
            left = clamp(cropState.startXInitial + dx, 0, right - minSize);
        }
        if (cropState.activeHandle.includes('e')) {
            right = clamp(cropState.endXInitial + dx, left + minSize, containerRect.width);
        }
        if (cropState.activeHandle.includes('n')) {
            top = clamp(cropState.startYInitial + dy, 0, bottom - minSize);
        }
        if (cropState.activeHandle.includes('s')) {
            bottom = clamp(cropState.endYInitial + dy, top + minSize, containerRect.height);
        }
        
        selectionState.startX = left;
        selectionState.startY = top;
        selectionState.endX = right;
        selectionState.endY = bottom;
    } else {
        // Selection drag mode
        const x = e.clientX - containerRect.left;
        const y = e.clientY - containerRect.top;
        selectionState.endX = clamp(x, 0, containerRect.width);
        selectionState.endY = clamp(y, 0, containerRect.height);
    }
    
    updateCropSelection();
}

function endCropDrag(e) {
    if (!cropState.isDragging) return;
    
    cropState.isDragging = false;
    cropState.dragMode = null;
    cropState.activeHandle = null;
    updateCropSelection();
}

function updateCropSelection(selectionKey = null) {
    if (!currentEditingCanvas) return;
    
    const updateSelectionElement = (key) => {
        const selectionElement = getSelectionElement(key);
        const selectionState = getSelectionState(key);
        if (!selectionElement) return;
        
        const left = Math.min(selectionState.startX, selectionState.endX);
        const top = Math.min(selectionState.startY, selectionState.endY);
        const width = Math.abs(selectionState.endX - selectionState.startX);
        const height = Math.abs(selectionState.endY - selectionState.startY);
        
        selectionElement.style.left = left + 'px';
        selectionElement.style.top = top + 'px';
        selectionElement.style.width = width + 'px';
        selectionElement.style.height = height + 'px';
    };
    
    if (selectionKey) {
        updateSelectionElement(selectionKey);
    } else if (cropState.mode === 'split') {
        updateSelectionElement('primary');
        updateSelectionElement('secondary');
    } else {
        updateSelectionElement('primary');
        const secondaryElement = getSelectionElement('secondary');
        if (secondaryElement) {
            secondaryElement.style.display = 'none';
        }
    }
    
    updateCropContinueState();
}


async function autoStartAnswerCopy() {
    try {
        // Check if there's already an active answer copy
        const statusResponse = await fetch(`${API_URL}/get_current_status`);
        const statusData = await statusResponse.json();
        
        if (statusData.active) {
            currentAnswerCopyId = statusData.answer_copy_id;
            currentImages = statusData.images || [];
            // Use exam details from backend (which loads from saved settings)
            if (statusData.exam_details) {
                examDetails = statusData.exam_details;
                // Update UI with saved exam details
                updateExamDetailsInUI(examDetails);
            }
            updateUI();
            return true;
        }
        
        // Start new answer copy automatically
        const response = await fetch(`${API_URL}/start_answer_copy`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentAnswerCopyId = data.answer_copy_id;
            currentImages = [];
            
            // Load exam details from the response (automatically restored from saved settings)
            if (data.exam_details) {
                examDetails = data.exam_details;
            } else {
                // Fallback: try to get from backend
                try {
                    const examResponse = await fetch(`${API_URL}/get_exam_details`);
                    const examData = await examResponse.json();
                    if (examData.success && examData.exam_details) {
                        examDetails = examData.exam_details;
                    }
                } catch (e) {
                    // Ignore errors
                }
            }
            
            updateUI();
            
            // Only show exam modal if exam details are not already saved
            const hasExamDetails = examDetails && 
                examDetails.degree && 
                examDetails.subject && 
                examDetails.exam_date && 
                examDetails.college;
            
            if (!hasExamDetails) {
                // Show exam details modal with pre-populated values (if any)
                showExamModal();
            } else {
                // Exam details are already saved, just update the UI
                updateExamDetailsInUI(examDetails);
                showMessage('Answer copy started with saved exam details', 'success');
            }
            return true;
        } else {
            showMessage(data.error || 'Failed to initialize', 'error');
            return false;
        }
    } catch (error) {
        console.error('Error auto-starting answer copy:', error);
        showMessage('Warning: Could not initialize. Please refresh.', 'warning');
        return false;
    }
}


async function completeAnswerCopy() {
    try {
        btnComplete.disabled = true;
        
        // Auto-start answer copy if needed
        if (!currentAnswerCopyId) {
            const started = await autoStartAnswerCopy();
            if (!started || !currentAnswerCopyId) {
                showMessage('Failed to start answer copy. Please try again.', 'error');
                btnComplete.disabled = false;
                return;
            }
        }
        
        // Check current status from backend
        const statusResponse = await fetch(`${API_URL}/get_current_status`);
        const statusData = await statusResponse.json();
        
        if (!statusData.active) {
            showMessage('No active answer copy. Please start a new one.', 'error');
            btnComplete.disabled = false;
            return;
        }
        
        // Check if exam details are set
        const examDetailsResponse = await fetch(`${API_URL}/get_exam_details`);
        let examDetailsData = null;
        try {
            examDetailsData = await examDetailsResponse.json();
        } catch (e) {
            // Exam details endpoint might not exist yet
        }
        
        const hasExamDetails = examDetailsData && examDetailsData.success && 
            examDetailsData.exam_details && 
            examDetailsData.exam_details.degree && 
            examDetailsData.exam_details.subject && 
            examDetailsData.exam_details.exam_date && 
            examDetailsData.exam_details.college;
        
        if (!hasExamDetails) {
            // Show exam details modal
            showMessage('Please provide exam details before generating PDF', 'warning');
            showExamModal();
            btnComplete.disabled = false;
            return;
        }
        
        const imagesInCopy = statusData.images || [];
        
        if (imagesInCopy.length === 0) {
            // No images in answer copy yet, try to upload from scannedImages
            if (scannedImages.length === 0) {
                showMessage('No images to generate PDF. Please upload images first.', 'warning');
                btnComplete.disabled = false;
                return;
            }
            
            if (!confirm(`Upload ${scannedImages.length} image(s) and generate PDF?`)) {
                btnComplete.disabled = false;
                return;
            }
            
            showMessage('Uploading images...', 'info');
            
            // Upload all scanned images to the answer copy
            let uploadedCount = 0;
            let failedCount = 0;
            
            for (const scannedImg of scannedImages) {
                try {
                    // Read file
                    let file;
                    if (window.electronAPI) {
                        const fileData = await window.electronAPI.readFile(scannedImg.path);
                        if (fileData.success) {
                            const blob = new Blob([fileData.data]);
                            file = new File([blob], scannedImg.filename, { type: 'image/jpeg' });
                        } else {
                            console.error(`Failed to read file: ${scannedImg.path}`, fileData.error);
                            failedCount++;
                            continue;
                        }
                    } else {
                        const response = await fetch(`file://${scannedImg.path}`);
                        const blob = await response.blob();
                        file = new File([blob], scannedImg.filename, { type: 'image/jpeg' });
                    }
                    
                    // Upload image
                    const formData = new FormData();
                    formData.append('image', file);
                    
                    const uploadResponse = await fetch(`${API_URL}/upload_image`, {
                        method: 'POST',
                        body: formData
                    });
                    
                    const uploadData = await uploadResponse.json();
                    
                    if (uploadData.success) {
                        uploadedCount++;
                        console.log(`Uploaded: ${scannedImg.filename}`);
                        
                        // Store auto-processing data for this image
                        if (uploadData.auto_processing && uploadData.image) {
                            imageAutoProcessingData[uploadData.image.path] = uploadData.auto_processing;
                            
                            // Show auto-processing messages
                            if (uploadData.auto_processing.messages && uploadData.auto_processing.messages.length > 0) {
                                const messages = uploadData.auto_processing.messages.join('\n');
                                showMessage(`Auto-processing completed for ${scannedImg.filename}`, 'info');
                                console.log('Auto-processing:', messages);
                            }
                        }
                        
                        // If this is the first image and unique ID was extracted, update the form
                        if (uploadData.unique_id_extracted && uploadData.image.sequence === 1) {
                            // Reload exam details to get the extracted unique ID
                            const examDetailsResponse = await fetch(`${API_URL}/get_exam_details`);
                            try {
                                const examDetailsData = await examDetailsResponse.json();
                                if (examDetailsData.success && examDetailsData.exam_details.unique_id) {
                                    const uniqueIdInput = document.getElementById('exam-unique-id');
                                    if (uniqueIdInput) {
                                        uniqueIdInput.value = examDetailsData.exam_details.unique_id;
                                        examDetails.unique_id = examDetailsData.exam_details.unique_id;
                                    }
                                }
                            } catch (e) {
                                // Ignore errors
                            }
                        }
                    } else {
                        failedCount++;
                        console.error(`Failed to upload ${scannedImg.filename}:`, uploadData.error || 'Unknown error');
                    }
                } catch (error) {
                    failedCount++;
                    console.error(`Error uploading ${scannedImg.filename}:`, error);
                }
            }
            
            if (uploadedCount === 0) {
                showMessage('No images were uploaded successfully. Cannot generate PDF.', 'error');
                btnComplete.disabled = false;
                return;
            }
            
            if (failedCount > 0) {
                showMessage(`Warning: ${failedCount} image(s) failed to upload. Generating PDF with ${uploadedCount} image(s)...`, 'warning');
            }
        } else {
            // Images already in answer copy, just generate PDF
            if (!confirm(`Generate PDF for ${imagesInCopy.length} image(s)?`)) {
                btnComplete.disabled = false;
                return;
            }
        }
        
        // Close any open PDF preview before generating new one
        if (pdfPreview.style.display === 'flex') {
            closePDFPreview();
        }
        
        // Generate PDF
        // Show progress indicator
        const progressMessage = showMessage('Generating PDF... This may take a moment. Please wait...', 'info');
        
        const startTime = Date.now();
        const response = await fetch(`${API_URL}/complete_answer_copy`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        const elapsedTime = ((Date.now() - startTime) / 1000).toFixed(1);
        
        // Remove progress message
        if (progressMessage && progressMessage.parentElement) {
            progressMessage.remove();
        }
        
        if (data.success) {
            showMessage(`PDF generated successfully in ${elapsedTime}s: ${data.pdf_path}`, 'success');
            
            // Clear image preview/editor
            clearImagePreview();
            
            // Reset state
            currentAnswerCopyId = null;
            currentImages = [];
            scannedImages = [];
            selectedImageIndex = -1;
            
            // Reload scanned images (they may have been moved/cleaned)
            await loadScannedImages();
            
            // Reload PDFs
            await loadPDFs();
            
            // Update UI
            updateUI();
            
            // Switch to PDFs tab to show the new PDF
            switchTab('pdfs');
        } else {
            showMessage(data.error || 'PDF generation failed', 'error');
            console.error('PDF generation error:', data);
        }
    } catch (error) {
        showMessage(`Error: ${error.message}`, 'error');
        console.error('Complete answer copy error:', error);
    } finally {
        btnComplete.disabled = false;
    }
}

function updateUI() {
    // Update buttons
    btnComplete.disabled = scannedImages.length === 0;
    updateScannedGallery();
}


async function loadPDFs() {
    try {
        const response = await fetch(`${API_URL}/list_pdfs`);
        const data = await response.json();
        
        // Close preview if currently viewing a PDF that no longer exists
        if (pdfPreview.style.display === 'flex' && pdfPreviewFrame.src) {
            const currentPdfPath = pdfPreviewFrame.src;
            const pdfsExist = data.pdfs && data.pdfs.length > 0;
            const currentPdfStillExists = pdfsExist && data.pdfs.some(pdf => {
                // Check if the current preview is for a PDF that still exists
                try {
                    const blobUrl = currentPdfPath;
                    if (blobUrl.startsWith('blob:')) {
                        // We can't easily check blob URLs, so we'll just close if PDFs list changed
                        return false;
                    }
                } catch (e) {
                    return false;
                }
            });
            
            if (!currentPdfStillExists) {
                closePDFPreview();
            }
        }
        
        if (data.pdfs && data.pdfs.length > 0) {
            pdfGallery.innerHTML = data.pdfs.map(pdf => `
                <div class="pdf-item" onclick="openPDF('${pdf.path.replace(/\\/g, '/')}', '${pdf.filename.replace(/'/g, "\\'")}')">
                    <div class="pdf-item-icon">📄</div>
                    <div class="pdf-item-name">${pdf.filename}</div>
                    <div class="pdf-item-info">
                        ${pdf.size_mb} MB<br>
                        ${new Date(pdf.created_at).toLocaleString()}
                    </div>
                    <div class="pdf-item-actions">
                        <button class="pdf-item-open" onclick="event.stopPropagation(); openPDF('${pdf.path.replace(/\\/g, '/')}', '${pdf.filename.replace(/'/g, "\\'")}')">Preview</button>
                    </div>
                </div>
            `).join('');
        } else {
            pdfGallery.innerHTML = '<div class="empty-state-small"><p>No PDFs generated yet</p></div>';
            // Close preview if no PDFs exist
            if (pdfPreview.style.display === 'flex') {
                closePDFPreview();
            }
        }
    } catch (error) {
        console.error('Error loading PDFs:', error);
        pdfGallery.innerHTML = '<div class="empty-state-small"><p>Error loading PDFs</p></div>';
        // Close preview on error
        if (pdfPreview.style.display === 'flex') {
            closePDFPreview();
        }
    }
}

async function openPDF(pdfPath, pdfName) {
    try {
        // Clean up any existing preview first
        if (pdfPreviewFrame.src && pdfPreviewFrame.src.startsWith('blob:')) {
            URL.revokeObjectURL(pdfPreviewFrame.src);
        }
        
        // Show loading state
        pdfPreviewTitle.textContent = `Loading ${pdfName}...`;
        pdfPreview.style.display = 'flex';
        pdfPreviewFrame.src = ''; // Clear previous PDF
        
        // Read PDF file using Electron API
        let pdfBlob;
        if (window.electronAPI) {
            const fileData = await window.electronAPI.readFile(pdfPath);
            if (fileData.success) {
                pdfBlob = new Blob([fileData.data], { type: 'application/pdf' });
            } else {
                throw new Error(fileData.error || 'Failed to read PDF file');
            }
        } else {
            // Fallback - try to fetch
            const response = await fetch(`file://${pdfPath}`);
            if (!response.ok) {
                throw new Error(`Failed to load PDF: ${response.statusText}`);
            }
            pdfBlob = await response.blob();
        }
        
        // Create object URL for PDF
        const pdfUrl = URL.createObjectURL(pdfBlob);
        pdfPreviewTitle.textContent = pdfName;
        pdfPreviewFrame.src = pdfUrl;
        
        // Store the current PDF path for cleanup tracking
        pdfPreviewFrame.dataset.pdfPath = pdfPath;
        
        // Handle iframe load errors
        pdfPreviewFrame.onerror = () => {
            console.error('Error loading PDF in iframe');
            showMessage('Error displaying PDF preview. Try opening externally.', 'error');
            closePDFPreview();
        };
        
        // Scroll to preview
        pdfPreview.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (error) {
        console.error('Error loading PDF:', error);
        showMessage(`Error loading PDF: ${error.message}`, 'error');
        closePDFPreview();
        
        // Try fallback - open in external viewer
        if (window.electronAPI) {
            try {
                await window.electronAPI.openPDF(pdfPath);
            } catch (openError) {
                console.error('Error opening PDF externally:', openError);
            }
        }
    }
}

function closePDFPreview() {
    // Clean up blob URL if it exists
    if (pdfPreviewFrame.src && pdfPreviewFrame.src.startsWith('blob:')) {
        try {
            URL.revokeObjectURL(pdfPreviewFrame.src);
        } catch (e) {
            console.warn('Error revoking blob URL:', e);
        }
    }
    pdfPreview.style.display = 'none';
    pdfPreviewFrame.src = '';
    pdfPreviewFrame.dataset.pdfPath = '';
    pdfPreviewTitle.textContent = '';
}

function clearImagePreview() {
    // Clear the image editor/preview
    const panel = document.getElementById('auto-processing-panel');
    if (panel) {
        panel.style.display = 'none';
    }
    if (currentEditingCanvas) {
        currentEditingCanvas.remove();
        currentEditingCanvas = null;
    }
    if (editorContainer) {
        editorContainer.innerHTML = '';
    }
    if (editorControls) {
        editorControls.style.display = 'none';
    }
    
    // Reset editing state
    currentEditingImage = null;
    currentEditingCtx = null;
    originalImage = null;
    selectedImageIndex = -1;
    
    // Reset crop state
    cropState = {
        enabled: false,
        mode: 'single',
        splitDirection: null,
        selections: {
            primary: {
                startX: 0,
                startY: 0,
                endX: 0,
                endY: 0
            },
            secondary: {
                startX: 0,
                startY: 0,
                endX: 0,
                endY: 0
            }
        },
        isDragging: false,
        dragMode: null,
        activeHandle: null,
        activeSelection: 'primary',
        dragStartX: 0,
        dragStartY: 0,
        startXInitial: 0,
        startYInitial: 0,
        endXInitial: 0,
        endYInitial: 0
    };
}



function showMessage(text, type = 'info') {
    const message = document.createElement('div');
    message.className = `message ${type}`;
    message.innerHTML = `
        <span>${text}</span>
        <button class="message-close" onclick="this.parentElement.remove()">×</button>
    `;
    
    messageContainer.appendChild(message);
    
    // Auto-remove after 5 seconds for info/success messages
    if (type === 'info' || type === 'success') {
        setTimeout(() => {
            if (message.parentElement) {
                message.remove();
            }
        }, 5000);
    }
    
    // Return message element so it can be removed manually
    return message;
}

// Settings functions
async function loadSettings() {
    try {
        // Load output folder
        const outputResponse = await fetch(`${API_URL}/get_output_folder`);
        const outputData = await outputResponse.json();
        if (outputData.folder_path) {
            document.getElementById('output-path-input').value = outputData.folder_path;
            document.getElementById('output-path-display').textContent = `Current: ${outputData.folder_path}`;
        }
        
        // Load scanner folder
        const scannerResponse = await fetch(`${API_URL}/get_scanner_folder`);
        const scannerData = await scannerResponse.json();
        if (scannerData.folder_path) {
            document.getElementById('scanner-path-input').value = scannerData.folder_path;
            document.getElementById('scanner-path-display').textContent = `Current: ${scannerData.folder_path}`;
        }
        
        // Load exam details
        try {
            const examDetailsResponse = await fetch(`${API_URL}/get_exam_details`);
            const examDetailsData = await examDetailsResponse.json();
            
            if (examDetailsData.success && examDetailsData.exam_details) {
                const details = examDetailsData.exam_details;
                document.getElementById('settings-exam-degree').value = details.degree || '';
                document.getElementById('settings-exam-subject').value = details.subject || '';
                document.getElementById('settings-exam-date').value = details.exam_date || '';
                document.getElementById('settings-exam-college').value = details.college || '';
                document.getElementById('settings-exam-unique-id').value = details.unique_id || '';
                examDetails = details;
            }
        } catch (examError) {
            // Exam details might not be available if no active answer copy
            console.log('No exam details available:', examError);
            // Clear the fields
            document.getElementById('settings-exam-degree').value = '';
            document.getElementById('settings-exam-subject').value = '';
            document.getElementById('settings-exam-date').value = '';
            document.getElementById('settings-exam-college').value = '';
            document.getElementById('settings-exam-unique-id').value = '';
        }
    } catch (error) {
        console.error('Error loading settings:', error);
        showMessage('Failed to load settings', 'error');
    }
}

async function saveSettings() {
    try {
        // Check if backend is available first
        try {
            const healthCheck = await fetch(`${API_URL}/health`);
            if (!healthCheck.ok) {
                throw new Error('Backend not ready');
            }
        } catch (error) {
            showMessage('Backend is not ready yet. Please wait a moment and try again.', 'warning');
            return;
        }
        
        const outputPath = document.getElementById('output-path-input').value;
        const scannerPath = document.getElementById('scanner-path-input').value;
        
        // Save output folder
        if (outputPath) {
            const outputResponse = await fetch(`${API_URL}/set_output_folder`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: outputPath })
            });
            
            if (!outputResponse.ok) {
                throw new Error(`HTTP ${outputResponse.status}`);
            }
            
            const outputData = await outputResponse.json();
            if (!outputData.success) {
                showMessage(`Failed to set output folder: ${outputData.error || 'Unknown error'}`, 'error');
                return;
            }
        }
        
        // Save scanner folder
        if (scannerPath) {
            const scannerResponse = await fetch(`${API_URL}/set_scanner_folder`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: scannerPath })
            });
            
            if (!scannerResponse.ok) {
                throw new Error(`HTTP ${scannerResponse.status}`);
            }
            
            const scannerData = await scannerResponse.json();
            if (!scannerData.success) {
                showMessage(`Failed to set scanner folder: ${scannerData.error || 'Unknown error'}`, 'error');
                return;
            }
        }
        
        // Save exam details (if there's an active answer copy)
        try {
            const degree = document.getElementById('settings-exam-degree').value.trim();
            const subject = document.getElementById('settings-exam-subject').value.trim();
            const examDate = document.getElementById('settings-exam-date').value;
            const college = document.getElementById('settings-exam-college').value.trim();
            const uniqueId = document.getElementById('settings-exam-unique-id').value.trim();
            
            // Check if there's an active answer copy
            const statusResponse = await fetch(`${API_URL}/get_current_status`);
            const statusData = await statusResponse.json();
            
            if (statusData.active) {
                // Only save if at least some fields are filled
                if (degree || subject || examDate || college || uniqueId) {
                    const examResponse = await fetch(`${API_URL}/set_exam_details`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            degree: degree || null,
                            subject: subject || null,
                            exam_date: examDate || null,
                            college: college || null,
                            unique_id: uniqueId || null
                        })
                    });
                    
                    const examData = await examResponse.json();
                    if (examData.success) {
                        examDetails = examData.exam_details;
                    }
                }
            } else {
                // No active answer copy - just store in local state for next time
                examDetails = {
                    degree: degree || null,
                    subject: subject || null,
                    exam_date: examDate || null,
                    college: college || null,
                    unique_id: uniqueId || null
                };
            }
        } catch (examError) {
            console.log('Could not save exam details (no active answer copy):', examError);
            // This is okay - exam details will be saved when answer copy is started
        }
        
        showMessage('Settings saved successfully!', 'success');
        // Reload settings to show updated paths
        await loadSettings();
    } catch (error) {
        console.error('Error saving settings:', error);
        if (error.message && error.message.includes('fetch')) {
            showMessage('Failed to connect to backend. Please ensure the application is running properly.', 'error');
        } else {
            showMessage(`Failed to save settings: ${error.message || 'Unknown error'}`, 'error');
        }
    }
}

async function resetSettings() {
    try {
        // Reset to default paths (relative to Python directory)
        const defaultOutput = 'output';
        const defaultScanner = 'scanner_input';
        
        // Save default output folder
        const outputResponse = await fetch(`${API_URL}/set_output_folder`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: defaultOutput })
        });
        
        // Save default scanner folder
        const scannerResponse = await fetch(`${API_URL}/set_scanner_folder`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: defaultScanner })
        });
        
        showMessage('Settings reset to defaults', 'success');
        // Reload settings to show updated paths
        await loadSettings();
    } catch (error) {
        console.error('Error resetting settings:', error);
        showMessage('Failed to reset settings', 'error');
    }
}

// Exam Details Modal Functions
function showExamModal() {
    const examModal = document.getElementById('exam-details-modal');
    if (!examModal) return;
    
    // Load existing exam details if available
    loadExamDetails().then(() => {
        examModal.style.display = 'flex';
    });
}

function closeExamModal() {
    const examModal = document.getElementById('exam-details-modal');
    if (examModal) {
        examModal.style.display = 'none';
    }
}

async function loadSavedExamDetails() {
    // Load saved exam details from backend on app startup
    try {
        const response = await fetch(`${API_URL}/get_exam_details`);
        const data = await response.json();
        
        if (data.success && data.exam_details) {
            examDetails = data.exam_details;
            // Update UI with saved exam details
            updateExamDetailsInUI(examDetails);
        }
    } catch (error) {
        console.error('Error loading saved exam details:', error);
        // Continue without exam details - they'll be loaded when answer copy starts
    }
}

function updateExamDetailsInUI(details) {
    // Update all exam detail fields in the UI with provided details
    if (!details) return;
    
    // Update modal form
    const examDegree = document.getElementById('exam-degree');
    const examSubject = document.getElementById('exam-subject');
    const examDate = document.getElementById('exam-date');
    const examCollege = document.getElementById('exam-college');
    const examUniqueId = document.getElementById('exam-unique-id');
    
    if (examDegree) examDegree.value = details.degree || '';
    if (examSubject) examSubject.value = details.subject || '';
    if (examDate) examDate.value = details.exam_date || '';
    if (examCollege) examCollege.value = details.college || '';
    if (examUniqueId) examUniqueId.value = details.unique_id || '';
    
    // Update settings tab form
    const settingsDegree = document.getElementById('settings-exam-degree');
    const settingsSubject = document.getElementById('settings-exam-subject');
    const settingsDate = document.getElementById('settings-exam-date');
    const settingsCollege = document.getElementById('settings-exam-college');
    const settingsUniqueId = document.getElementById('settings-exam-unique-id');
    
    if (settingsDegree) settingsDegree.value = details.degree || '';
    if (settingsSubject) settingsSubject.value = details.subject || '';
    if (settingsDate) settingsDate.value = details.exam_date || '';
    if (settingsCollege) settingsCollege.value = details.college || '';
    if (settingsUniqueId) settingsUniqueId.value = details.unique_id || '';
}

async function loadExamDetails() {
    try {
        const response = await fetch(`${API_URL}/get_exam_details`);
        const data = await response.json();
        
        if (data.success && data.exam_details) {
            const details = data.exam_details;
            examDetails = details;
            // Update UI with exam details
            updateExamDetailsInUI(details);
        } else {
            // If no exam details from backend, use saved examDetails from settings
            if (examDetails && (examDetails.degree || examDetails.subject || examDetails.exam_date || examDetails.college)) {
                updateExamDetailsInUI(examDetails);
            } else {
                // Clear the form
                updateExamDetailsInUI({
                    degree: '',
                    subject: '',
                    exam_date: '',
                    college: '',
                    unique_id: ''
                });
            }
        }
    } catch (error) {
        console.error('Error loading exam details:', error);
        // If endpoint doesn't exist or error, use saved examDetails from settings
        if (examDetails && (examDetails.degree || examDetails.subject || examDetails.exam_date || examDetails.college)) {
            updateExamDetailsInUI(examDetails);
        } else {
            // Clear the form
            updateExamDetailsInUI({
                degree: '',
                subject: '',
                exam_date: '',
                college: '',
                unique_id: ''
            });
        }
    }
}

async function saveExamDetails() {
    const examDetailsForm = document.getElementById('exam-details-form');
    if (!examDetailsForm || !examDetailsForm.checkValidity()) {
        examDetailsForm.reportValidity();
        return;
    }
    
    try {
        const degree = document.getElementById('exam-degree').value.trim();
        const subject = document.getElementById('exam-subject').value.trim();
        const examDate = document.getElementById('exam-date').value;
        const college = document.getElementById('exam-college').value.trim();
        const uniqueId = document.getElementById('exam-unique-id').value.trim();
        
        if (!degree || !subject || !examDate || !college) {
            showMessage('Please fill in all required fields', 'error');
            return;
        }
        
        const response = await fetch(`${API_URL}/set_exam_details`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                degree: degree,
                subject: subject,
                exam_date: examDate,
                college: college,
                unique_id: uniqueId || null
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            examDetails = data.exam_details;
            // Also update settings tab form
            document.getElementById('settings-exam-degree').value = examDetails.degree || '';
            document.getElementById('settings-exam-subject').value = examDetails.subject || '';
            document.getElementById('settings-exam-date').value = examDetails.exam_date || '';
            document.getElementById('settings-exam-college').value = examDetails.college || '';
            document.getElementById('settings-exam-unique-id').value = examDetails.unique_id || '';
            
            showMessage('Exam details saved successfully', 'success');
            closeExamModal();
            
            // If user was trying to generate PDF, retry
            if (btnComplete.disabled && scannedImages.length > 0) {
                // Re-enable button so user can try again
                btnComplete.disabled = false;
            }
        } else {
            showMessage(data.error || 'Failed to save exam details', 'error');
        }
    } catch (error) {
        console.error('Error saving exam details:', error);
        showMessage(`Error saving exam details: ${error.message}`, 'error');
    }
}

// Make functions available globally
window.selectScannedImage = selectScannedImage;
window.deleteScannedImage = deleteScannedImage;
window.openPDF = openPDF;
window.closePDFPreview = closePDFPreview;

// Initialize on load
document.addEventListener('DOMContentLoaded', init);
