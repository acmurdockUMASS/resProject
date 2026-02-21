# resProject
Repository for HackHer 2026 project 
Perfect. Here is a **single clean copy-paste block** you can drop directly into your `README.md`.

---

# Resume Backend – Local Setup Guide

## Prerequisites

* Python 3.10+ (check with `python3 --version`)
* pip
* Git

---

## 1. Clone the repository

```bash
git clone <repo-url>
cd resProject
```

---

## 2. Create a virtual environment

From the project root:

```bash
python3 -m venv .venv
```

Activate it:

### Mac / Linux

```bash
source .venv/bin/activate
```

### Windows (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
```

You should now see `(.venv)` in your terminal.

---

## 3. Install dependencies

From the project root:

```bash
pip install -r backend/requirements.txt
```

(Optional but recommended)

```bash
pip install --upgrade pip
```

---

## 4. Set required environment variables

These are required for DigitalOcean Spaces file storage.

### Mac / Linux

```bash
export DO_SPACES_KEY="your_key"
export DO_SPACES_SECRET="your_secret"
export DO_SPACES_REGION="nyc3"
export DO_SPACES_BUCKET="your_bucket"
export DO_SPACES_ENDPOINT="https://nyc3.digitaloceanspaces.com"
```

### Windows (PowerShell)

```powershell
setx DO_SPACES_KEY "your_key"
setx DO_SPACES_SECRET "your_secret"
setx DO_SPACES_REGION "nyc3"
setx DO_SPACES_BUCKET "your_bucket"
setx DO_SPACES_ENDPOINT "https://nyc3.digitaloceanspaces.com"
```

If using `setx`, restart your terminal afterward.

---

## 5. Run the backend server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

You should see:

```
Uvicorn running on http://127.0.0.1:8000
```

---

## 6. Test the API

Open in your browser:

Swagger UI:

```
http://127.0.0.1:8000/docs
```

Health check:

```
http://127.0.0.1:8000/health
```

---

## 7. Stop the server

Press:

```
CTRL + C
```

---

## Common Issues

**ModuleNotFoundError: app**

* Make sure you `cd backend`
* Then run `uvicorn app.main:app --reload --port 8000`

**Could not open requirements.txt**

* Run: `pip install -r backend/requirements.txt` from the project root

**Virtual environment not activated**

* Run: `source .venv/bin/activate` (Mac/Linux)
* Or: `.venv\Scripts\Activate.ps1` (Windows)

---