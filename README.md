# 📌 FileSeek – AI-Powered Local Document Archivist

🚀 **Fast. Private. Local.** – FileSeek is a lightweight AI-powered file archive and search tool that helps you organize and retrieve documents instantly using natural language.

It runs entirely on your machine, ensuring full privacy while giving you a cyber-style experience.

---

## 🔍 Key Features
- ✅ **Instant Search** – Use natural language to find files & notes quickly.
- ✅ **Automatic Ingestion** – Detects new or modified files automatically.
- ✅ **AI-Powered Retrieval** – Uses OCR & semantic search for better results.
- ✅ **Local-First** – No internet needed. Runs fully offline & private.
- ✅ **Cyber-Style UI** – Terminal aesthetic for CLI lovers, with optional desktop or browser UI.
- ✅ **Zero Setup** – Works out of the box. No need to manage databases or indexes manually.

---

## 📖 Why FileSeek?
- ⚡ **Blazing Fast** – Searches take milliseconds.
- 🔒 **Privacy First** – Runs entirely offline, no cloud storage required.
- 🤖 **AI-Powered** – Finds content inside PDFs, scanned docs, and images.
- 🪶 **Lightweight** – No bloated dependencies, runs smoothly on any system.
- 💻 **Cyber-Cool Aesthetic** – Designed for developers & power users.

---

## 🛠 Installation

### 1️⃣ Install via pip
```bash
pip install fileseek
```

### 2️⃣ Run the Archivist
```bash
fileseek ingest ~/Documents
```

### 3️⃣ Search for Documents
```bash
fileseek query "project report"
```

---

## 🚀 Quick Start
FileSeek lets you store and retrieve documents with a simple CLI.

### 🗄 Ingest Files
Automatically detect new or modified files and add them to the archive:
```bash
fileseek ingest ~/MyFiles
```

**Supports:** PDFs, text files, images, and scanned documents.

### 🔍 Search with Natural Language
Find any document instantly using a semantic search engine:
```bash
fileseek query "find the tax return from 2022"
```

📄 *Returns the most relevant documents even if filenames don't match!*

### 👀 Preview Files
List all stored files:
```bash
fileseek list
```

### 🛠 Optional: Enable Auto-Watcher
Automatically process new files in the background:
```bash
fileseek watch ~/Documents
```
💡 *This will detect and process files in real time as they are added or modified.*

---

## 🔧 Configuration
FileSeek is zero-config by default, but you can tweak settings:
```bash
fileseek config set storage_path=~/FileSeekData
```

---

## 📦 Run from Source
```bash
git clone https://github.com/yourusername/fileseek.git

pip install -r requirements.txt

python run.py process ~/Documents
```

### 🚀 Quick Start with Source

### 🗄 Process Files
Add documents to the archive:
```bash
python run.py process -r ~/Documents
```

**Supports:** PDFs, text files, images, and scanned documents.

### 🔍 Search with Natural Language
Find documents using semantic search:
```bash
python run.py search "find the relevant documents of natural language processing"
```

📄 *Returns the most relevant documents even if filenames don't match!*

### 🔄 Find Similar Documents
Find documents similar to a reference file:
```bash
python run.py similar ~/Documents/project_plan.pdf
```

### 👀 Preview Files
List all stored files:
```bash
python run.py list
```

### ✅ Validate Archive
Check archive integrity:
```bash
python run.py validate -r ~/Documents
```

### 👀 Watch for Changes
Automatically process new or modified files:
```bash
python run.py watch -r ~/Documents
```
💡 *Detects and processes files in real time as they are added, modified, or deleted.*

### 🔧 Configuration
```bash
python run.py config set storage_path=~/FileSeekData
```

### 📄 Get Document Info
Get detailed information about a specific document:
```bash
python run.py info ~/Documents/sample.pdf
```