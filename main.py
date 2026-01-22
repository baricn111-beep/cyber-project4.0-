import socket
import os
import mimetypes
import zipfile
from urllib.parse import unquote, parse_qs
import logging

# ================= CONFIGURATION =================
WEB_ROOT = r"C:\Users\Bari\OneDrive\Desktop\bari\4.0.py\webroot.zip"
UPLOAD_DIR = 'upload'  # תיקייה לשמירת קבצים שהועלו [cite: 36]
DEFAULT_URL = "/index.html"
IP = '0.0.0.0'
PORT = 8080
SOCKET_TIMEOUT = 5
QUEUE_SIZE = 10

# יצירת תיקיית upload אם אינה קיימת [cite: 36]
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

REDIRECTION_DICTIONARY = {"/moved/": "/index.html"}

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    filename='server.log',
    filemode='a'
)


# ================= FUNCTIONS =================

def get_file_data(file_name):
    internal_path = file_name.lstrip("/")
    try:
        with zipfile.ZipFile(WEB_ROOT, 'r') as z:
            with z.open(internal_path) as f:
                return f.read()
    except Exception:
        return None


def handle_client_request(resource, method, client_socket, body=None):
    """
    מנתח את הבקשה ומחזיר תגובה לפי הממשקים הנדרשים
    """
    if "?" in resource:
        path, query_string = resource.split("?", 1)
    else:
        path, query_string = resource, ""

    params = parse_qs(query_string)
    uri = path if path not in ['', '/'] else DEFAULT_URL

    # 1. ממשק calculate-next [cite: 4]
    if "calculate-next" in uri:
        num_str = params.get('num', [None])[0]
        if num_str and num_str.isdigit():
            result = str(int(num_str) + 1).encode()  # מחזיר את המספר העוקב
            header = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {len(result)}\r\n\r\n"
            client_socket.send(header.encode() + result)
        else:
            header = "HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n"  # החזרת 400 אם לא מספר [cite: 9]
            client_socket.send(header.encode())
        return

    # 2. ממשק calculate-area (שטח משולש) [cite: 18]
    if "calculate-area" in uri:
        width = params.get('width', [None])[0]
        height = params.get('height', [None])[0]
        try:
            # חישוב שטח משולש: (גובה * רוחב) / 2
            area = (float(width) * float(height)) / 2
            result = f"{area}".encode()  # יחזיר '6.0' עבור 3 ו-4 [cite: 21]
            header = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {len(result)}\r\n\r\n"
            client_socket.send(header.encode() + result)
        except (TypeError, ValueError):
            header = "HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n"  # החזרת 400 במידה ופרמטרים לא תקינים [cite: 22]
            client_socket.send(header.encode())
        return

    # 3. ממשק upload (POST בלבד) [cite: 34]
    if "upload" in uri:
        if method == "POST":
            file_name = params.get('file-name', [None])[0]
            if file_name and body:
                file_path = os.path.join(UPLOAD_DIR, file_name)
                with open(file_path, 'wb') as f:
                    f.write(body)  # שמירת הקובץ בתיקיית upload [cite: 36, 39]
                header = "HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
                client_socket.send(header.encode())
            else:
                header = "HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n"
                client_socket.send(header.encode())
        else:
            header = "HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n"
            client_socket.send(header.encode())
        return

    # 4. ממשק image (שליפת קובץ מתיקיית upload)
    if "image" in uri:
        img_name = params.get('image-name', [None])[0]
        if img_name:
            img_path = os.path.abspath(os.path.join(UPLOAD_DIR, img_name))
            print(f"--- DEBUG: Looking for file at: {img_path} ---")  # שורת בדיקה

            if os.path.exists(img_path) and os.path.isfile(img_path):
                with open(img_path, 'rb') as f:
                    data = f.read()
                ctype, _ = mimetypes.guess_type(img_path)
                header = f"HTTP/1.1 200 OK\r\nContent-Type: {ctype}\r\nContent-Length: {len(data)}\r\n\r\n"
                client_socket.send(header.encode() + data)
                return

        # אם לא נמצא או לא הועבר שם
        print(f"--- DEBUG: File NOT FOUND or invalid name ---")
        header = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
        client_socket.send(header.encode())
        return

    # טיפול רגיל בקבצים מה-ZIP
    if uri in REDIRECTION_DICTIONARY:
        location = REDIRECTION_DICTIONARY[uri]
        header = f"HTTP/1.1 302 Found\r\nLocation: {location}\r\n\r\n"
        client_socket.send(header.encode())
        return

    data = get_file_data(uri)
    if data:
        ctype, _ = mimetypes.guess_type(uri)
        ctype = ctype or 'application/octet-stream'
        header = f"HTTP/1.1 200 OK\r\nContent-Type: {ctype}\r\nContent-Length: {len(data)}\r\n\r\n"
        client_socket.send(header.encode() + data)
    else:
        header = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
        client_socket.send(header.encode())


def handle_client(client_socket):
    logging.info('Client connected')
    try:
        # קריאת ה-Headers תחילה
        request_data = b""
        while b"\r\n\r\n" not in request_data:
            chunk = client_socket.recv(1024)
            if not chunk: break
            request_data += chunk

        if not request_data: return

        header_part, body_start = request_data.split(b"\r\n\r\n", 1)
        header_text = header_part.decode(errors='ignore')
        lines = header_text.splitlines()

        if not lines: return

        # חילוץ מתודה ונתיב [cite: 59]
        parts = lines[0].split()
        if len(parts) < 3: return
        method, resource, version = parts

        # טיפול ב-Body עבור POST [cite: 34]
        body = b""
        if method == "POST":
            content_length = 0
            for line in lines:
                if line.lower().startswith("content-length:"):
                    content_length = int(line.split(":")[1].strip())

            body = body_start
            while len(body) < content_length:
                body += client_socket.recv(1024)
            body = body[:content_length]

        logging.info(f'Request: {method} {resource}')
        handle_client_request(resource, method, client_socket, body)

    except Exception as e:
        logging.error(f'Error: {e}')
    finally:
        client_socket.close()


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((IP, PORT))
        server_socket.listen(QUEUE_SIZE)
        logging.info(f"Server started on {IP}:{PORT}")
        while True:
            client_socket, _ = server_socket.accept()
            client_socket.settimeout(SOCKET_TIMEOUT)
            handle_client(client_socket)
    except Exception as e:
        logging.error(f'Main Error: {e}')
    finally:
        server_socket.close()


if __name__ == "__main__":
    main()