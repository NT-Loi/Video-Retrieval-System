# 🎬 Video Retrieval System

A comprehensive, end-to-end video retrieval system capable of performing temporal text search, object detection, and audio transcript search. This system is designed to handle complex queries and provides a user-friendly interface for browsing and streaming video content.

## ✨ Features

-   **Advanced Search Capabilities**:
    -   **Temporal Text Search**: Find video segments using natural language queries describing a sequence of events.
    -   **Object Search**: Filter results based on specific objects appearing in the video.
    -   **Audio/Transcript Search**: Search for spoken words or phrases within the video content.
    -   **Hybrid Search**: Combine text, object, and audio queries for precise retrieval.
-   **Adaptive Streaming**: Supports **HLS (HTTP Live Streaming)** for smooth video playback.
-   **Interactive UI**: A clean web interface for searching, viewing results, and inspecting video details.

## 🛠️ System Architecture

The system is built using a microservices architecture:
-   **Frontend/Backend**: Flask (Python) web server.
-   **Vector Database**: Milvus (for storing and searching embeddings).
-   **Text Search Engine**: Elasticsearch (for transcript metadata search).
-   **Metadata Storage**: MongoDB (for storing and search object detection results).
-   **AI Models**:
    -   **CLIP**: For text-to-video retrieval (pre-processed).
    -   **RF-DETR**: For object detection (pre-processed).
    -   **TransNetV2**: For shot detection (pre-processed).
    -   **Whisper**: For audio transcription (pre-processed).

## 🚀 Prerequisites

Before you begin, ensure you have the following installed:

-   **Operating System**: Linux (Ubuntu recommended).
-   **Docker & Docker Compose**: For running database services.
-   **Python 3.10+**: For the application logic.
-   **NVIDIA Drivers & CUDA Tools**: Recommended for GPU acceleration (required for efficient model inference).
-   **FFmpeg**: For video processing.

## 📦 Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/NT-Loi/Video-Retrieval-System.git
cd Video-Retrieval-System
```

### 2. Set Up the Environment

It is recommended to use a virtual environment or Conda.

```bash
# Using venv
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

> **Note**: If you are using a specific CUDA version, you may need to install PyTorch separately suitable for your environment before running the requirements install.

### 4. Configure the Application

Create a `config.py` file in the root directory. You can use the following template (ensure paths match your system):

```python
import os

# Database Configurations
MONGO_URI = "mongodb://localhost:27017/"
MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"
ES_HOST = "http://localhost:9200"

# Paths
DATA_DIR = os.path.join(os.getcwd(), "data")
KEYFRAMES_DIR = os.path.join(DATA_DIR, "keyframes")
HLS_DIR = os.path.join(DATA_DIR, "hls")
SHOTS_DIR = os.path.join(DATA_DIR, "shots")

# Evaluation Server Credentials (for Proxy API)
EVAL_SERVER_URL = "https://eventretrieval.org"
EVAL_USERNAME = "your_username"
EVAL_PASSWORD = "your_password"
```

## 🏗️ Data Preparation

The system relies on processed data (keyframes, HLS streams, metadata). Ensure your data is organized in the `data/` directory.

### Ingestion

To ingest data into Mylvus, Elasticsearch, and MongoDB, you can use the built-in ingestion logic.
Open `app.py` and modify the initialization line if this is your first run:

```python
# In app.py
search_system = VideoRetrievalSystem(re_ingest=True) 
```

Or run the ingestion script directly if available (e.g., `ingest_data.py`).

> **Tip**: Set `re_ingest=False` after the initial run to speed up startup.

## ⚡ Running the Application

### 1. Start Database Services

Use Docker Compose to start Milvus, Elasticsearch, and MongoDB:

```bash
docker compose up -d
```

Check if services are running:
```bash
docker ps
```

### 2. Run the Flask App

Start the main application server:

```bash
python app.py
```

The server will start at `http://0.0.0.0:5000`.

## 📖 Usage Guide

### Web Interface

1.  Open your browser and navigate to `http://localhost:5000`.
2.  **Search**:
    -   **Text**: Enter a description like "A person running in the park".
    -   **Objects**: Enter objects to filter by, e.g., "car", "dog".
    -   **Audio**: Enter spoken phrases to find.
3.  **Results**: Click on a result to view the video shot. Hover over thumbnails to preview.