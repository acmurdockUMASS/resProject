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

FRONT END FRONT END 

cd frontend

npm install 

if .env.example does not exist in frontend folder (NOT IN SRC) create it and just add this line VITE_API_BASE_URL=https://seamstress-m6lai.ondigitalocean.app

npm run dev 

open the url http://localhost:5173/

