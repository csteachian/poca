from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import hashlib
import os
from datetime import datetime
import requests
from urllib.parse import urlparse
import re
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
import socket
import ipaddress
import logging


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

app = Flask(__name__)
CSRFProtect(app)
app.secret_key = os.environ.get('SECRET_KEY') or 'dev-only-key'

app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Database initialization
def init_db():
    conn = sqlite3.connect('pocket_clone.db')
    cursor = conn.cursor()

    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create articles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    conn.commit()
    conn.close()


# CSRF in-dept defense. Avoids CSRF-TOKEN from being cached by CDNS
@app.after_request
def add_header(response):
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-store, max-age=0'
    return response

def hash_password(password):
    return generate_password_hash(password)


def is_host_safe(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False

    for family, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def get_db_connection():
    conn = sqlite3.connect('pocket_clone.db')
    conn.row_factory = sqlite3.Row
    return conn

def extract_title_from_url(url):
    """Try to extract title from URL or use a simple fallback"""
    response = None
    try:


        parsed = urlparse(url)
        if not parsed.scheme:
            url = 'http://' + url
            parsed = urlparse(url)
        if parsed.scheme in ('http', 'https'):
            host = parsed.hostname
            if host:
                if is_host_safe(host):
                    response = requests.get(url, timeout=5, allow_redirects=True)
                    for r in response.history:
                        location = r.headers.get('Location')
                        if not location:
                            continue
                        redirected_host = urlparse(location).hostname
                        if not redirected_host or not is_host_safe(redirected_host):
                            logger.warning("Blocked SSRF via redirect: %s -> %s", url, location)
                            return parsed.netloc or url

                else:
                    logger.warning("Blocked SSRF attempt or invalid host: %s", url)
                    return parsed.netloc or url

            else:
                logger.warning("Empty  host or could not resolve: %s", url)
                return parsed.netloc or url



        if response and response.status_code == 200:
            # Simple regex to extract title from HTML
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', response.text, re.IGNORECASE)
            if title_match:
                return title_match.group(1).strip()
    except Exception:
        pass

    # Fallback: use domain name or URL
    try:
        parsed = urlparse(url)
        return parsed.netloc or url
    except Exception:
        return url

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            flash('Username and password are required')
            return render_template('register.html')

        conn = get_db_connection()

        # Check if username already exists
        existing_user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing_user:
            flash('Username already exists')
            conn.close()
            return render_template('register.html')

        # Create new user
        password_hash = hash_password(password)
        conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                    (username, password_hash))
        conn.commit()
        conn.close()

        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT id, username, password_hash FROM users WHERE username = ?',
                           (username,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            conn.close()
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
        conn.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    articles = conn.execute('''
        SELECT id, title, url, added_at
        FROM articles
        WHERE user_id = ?
        ORDER BY added_at DESC
    ''', (session['user_id'],)).fetchall()
    conn.close()

    return render_template('dashboard.html', articles=articles, username=session['username'])

@app.route('/add_article', methods=['POST'])
def add_article():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    url = request.form['url'].strip()
    custom_title = request.form.get('title', '').strip()

    if not url:
        flash('URL is required')
        return redirect(url_for('dashboard'))

    # Use custom title if provided, otherwise extract from URL
    title = custom_title if custom_title else extract_title_from_url(url)

    # Add http:// if no protocol specified
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url

    conn = get_db_connection()
    conn.execute('INSERT INTO articles (user_id, title, url) VALUES (?, ?, ?)',
                (session['user_id'], title, url))
    conn.commit()
    conn.close()

    flash('Article saved successfully!')
    return redirect(url_for('dashboard'))

@app.route('/delete_article/<int:article_id>', methods=['POST'])
def delete_article(article_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    conn.execute('DELETE FROM articles WHERE id = ? AND user_id = ?',
                (article_id, session['user_id']))
    conn.commit()
    conn.close()

    flash('Article deleted successfully!')
    return redirect(url_for('dashboard'))

@app.route('/view_article/<int:article_id>')
def view_article(article_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    article = conn.execute('''
        SELECT id, title, url, added_at
        FROM articles
        WHERE id = ? AND user_id = ?
    ''', (article_id, session['user_id'])).fetchone()
    conn.close()

    if not article:
        flash('Article not found')
        return redirect(url_for('dashboard'))

    return render_template('view_article.html', article=article)

if __name__ == '__main__':
    init_db()
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
