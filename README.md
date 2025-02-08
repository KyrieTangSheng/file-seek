# 📌 FileSeek – AI-Powered Local Document Archivist

🚀 **Fast. Private. Local.** – FileSeek is a lightweight AI-powered file archive and search tool that helps you organize and retrieve documents instantly using natural language.

It runs entirely on your machine, ensuring full privacy while giving you a cyber-style experience.

---

## 🔍 Key Features
- ✅ **Smart Search** – Natural language search with semantic understanding
- ✅ **Similar Document Finding** – Discover related documents automatically
- ✅ **AI-Powered OCR** – Extract text from images and scanned PDFs
- ✅ **Local-First** – Runs fully offline for complete privacy
- ✅ **Zero Config** – Works out of the box with sensible defaults
- ✅ **Real-time Monitoring** – Auto-detects new and modified files

---

## 📖 Why FileSeek?
- ⚡ **Blazing Fast** – Semantic search in milliseconds
- 🔒 **Privacy First** – No cloud, no data sharing, fully local
- 🤖 **AI-Powered** – Advanced OCR and semantic understanding
- 🪶 **Lightweight** – Minimal dependencies, smooth performance
- 💻 **Developer-Friendly** – Clean CLI with rich terminal UI

---

## 🛠 System Requirements

### Required Dependencies
Make sure you have these system packages installed:

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr poppler-utils libmagic1
```

**Fedora:**
```bash
sudo dnf install tesseract poppler-utils file-libs
```

**macOS:**
```bash
brew install tesseract poppler libmagic
```

**Windows:**
```powershell
# Using Chocolatey (Run as Administrator)
choco install tesseract poppler libmagic
```

---

## 🚀 Quick Start

### 1️⃣ Process Documents
Add documents to the archive:
```bash
fileseek process -r /path/to/documents
```

**Supports:** PDFs, text files, images (with OCR), and scanned documents

### 2️⃣ Search Documents
Find documents using natural language:
```bash
fileseek search "find my notes on machine learning"
```

### 3️⃣ Find Similar Documents
Discover documents similar to a reference file:
```bash
fileseek similar /path/to/reference/file
```

### 4️⃣ Monitor for Changes
Automatically process new, modified, or deleted files:
```bash
fileseek watch /path/to/watch
```

### 5️⃣ List All Processed Documents
View all archived documents:
```bash
fileseek list
```

---

## 📦 Run from Source
```bash
git clone https://github.com/yourusername/fileseek.git
pip install -e .
```

Now you can use all commands directly:
```bash
fileseek process ~/Documents
fileseek search "find my course note on machine learning"
fileseek similar ~/Documents/project_plan.pdf
fileseek watch ~/Documents
fileseek list
fileseek validate
```


## ⚙️ Configuration
FileSeek is zero-config by default but highly customizable:

```bash
# Set custom storage location
fileseek config set storage_path=~/FileSeekData

# Enable debug logging
fileseek config set logging.level=DEBUG

# Set OCR language (ISO 639-2 codes)
fileseek config set ocr.languages=["eng","fra"]
```

Key Configuration Options:
- `storage_path`: Where to store the document index
- `ocr.languages`: Languages for OCR processing
- `search.max_results`: Maximum number of search results
- `monitoring.watch_interval`: File monitoring frequency

---