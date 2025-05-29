# Pocket Clone

A simple read-later application built with Flask, similar to Pocket.

## Features

- User registration and authentication
- Save articles with URLs
- Automatic title extraction from web pages
- View saved articles
- Delete articles
- Responsive web interface

## Setup for PythonAnywhere

1. Upload all files to your PythonAnywhere account
2. Install dependencies: `pip3.10 install --user -r requirements.txt`
3. Set up the web app in PythonAnywhere dashboard:
   - Source code: `/home/yourusername/pocket-clone`
   - Working directory: `/home/yourusername/pocket-clone`
   - WSGI configuration file: point to `app.py`
4. Change the secret key in `app.py` for production
5. The SQLite database will be created automatically on first run

## Local Development

1. Install dependencies: `pip install -r requirements.txt`
2. Run the application: `python app.py`
3. Open http://localhost:5000 in your browser

## Usage

1. Register a new account or login
2. Add articles by entering URLs (titles will be extracted automatically)
3. View your saved articles on the dashboard
4. Click on article titles to view details
5. Use "Open" to visit the original article
6. Delete articles you no longer need

## Database Schema

- **users**: id, username, password_hash, created_at
- **articles**: id, user_id, title, url, added_at
