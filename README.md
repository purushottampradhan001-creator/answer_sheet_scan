# Offline Answer Sheet Image-to-PDF Desktop Application

A secure, offline desktop application for converting sequential answer sheet images into structured PDFs with validation.

## Features

- ✅ **100% Offline** - No internet required
- ✅ **Image Validation** - Duplicate detection, quality checks, corruption detection
- ✅ **Sequential Processing** - Process images one by one
- ✅ **PDF Generation** - One PDF per answer copy
- ✅ **Scanner Integration** - Auto-import images from scanner folder
- ✅ **Modern UI** - Clean, intuitive interface
- ✅ **Secure** - All data stored locally

## System Requirements

- **OS**: Windows 10/11, macOS, or Linux
- **Python**: 3.9 or higher
- **Node.js**: 16.x or higher
- **RAM**: 8 GB recommended
- **Storage**: SSD recommended

## Installation

### 1. Install Python Dependencies

```bash
cd python
pip install -r requirements.txt
```

### 2. Install Electron Dependencies

```bash
cd electron
npm install
```

## Running the Application

### Development Mode

1. **Start Python Backend** (Terminal 1):
```bash
cd python
python image_engine.py
```

2. **Start Electron App** (Terminal 2):
```bash
cd electron
npm start
```

### Production Build (Windows)

```bash
cd electron
npm run build:win
```

This will create a Windows installer in the `dist/` folder.

## Usage

### Manual Upload Method

1. **Start New Answer Copy**: Click "New Answer Copy" to begin
2. **Upload Images**: Click "Upload Image" and select images one by one
3. **Review**: Images are validated and displayed in the preview
4. **Complete**: Click "Complete & Generate PDF" when done
5. **Repeat**: Start a new answer copy for the next set

### Scanner Integration Method

1. **Start New Answer Copy**: Click "New Answer Copy" to begin
2. **Configure Scanner**: Set scanner to save to `scanner_input/` folder
3. **Scan Pages**: Scan documents - images appear automatically!
4. **Review**: Check images in the preview
5. **Complete**: Click "Complete & Generate PDF" when done

See [SCANNER_INTEGRATION.md](SCANNER_INTEGRATION.md) for detailed scanner setup instructions.

## Project Structure

```
answersheetscanning/
├── electron/          # Electron frontend
│   ├── main.js       # Main process
│   ├── renderer.js   # Renderer process
│   ├── index.html    # UI
│   └── styles.css    # Styling
├── python/            # Python backend
│   ├── image_engine.py    # Flask server
│   ├── validator.py       # Image validation
│   └── pdf_generator.py   # PDF creation
├── working/           # Temporary image storage
├── output/            # Generated PDFs
└── db/                # SQLite database
```

## API Endpoints

The Python backend exposes the following endpoints:

- `GET /health` - Health check
- `POST /start_answer_copy` - Start new answer copy
- `POST /upload_image` - Upload and validate image
- `GET /get_current_status` - Get current status
- `POST /complete_answer_copy` - Generate PDF
- `POST /remove_image` - Remove image from current copy

## Image Validation

- **Duplicate Detection**: Uses perceptual hashing (pHash)
- **Quality Checks**: Blur detection (Laplacian variance), resolution check
- **Corruption Detection**: File size and decode validation

## PDF Generation

- Uses ReportLab for PDF creation
- Maintains image order
- High-quality output
- A4 page size (configurable)

## Security

- All processing happens locally
- No cloud storage
- No external API calls
- Suitable for secure exam environments

## Troubleshooting

### Python Backend Won't Start

- Ensure Python 3.9+ is installed
- Install dependencies: `pip install -r requirements.txt`
- **Port changed to 5001** (was 5000) to avoid conflicts
- If port 5001 is in use, edit `python/image_engine.py` and change `PORT = 5001`

### Electron App Can't Connect

- Ensure Python backend is running
- Check firewall settings
- Verify API URL is `http://127.0.0.1:5001` (changed from 5000)

### Image Upload Fails

- Check image format (JPG, PNG, BMP, TIFF supported)
- Ensure image is not corrupted
- Verify file size is reasonable

## License

MIT License

## Support

For issues or questions, please check the documentation or create an issue in the repository.
