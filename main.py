import mimetypes
import urllib.parse
import json
import logging
import socket
import os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from multiprocessing import Process
from datetime import datetime
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(processName)s - %(message)s")

BASE_DIR = Path(__file__).parent
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 3000

SOCKET_HOST = "127.0.0.1"
SOCKET_PORT = 5000

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongodb:27017/")


class HttpHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        pr_url = urllib.parse.urlparse(self.path)

        if pr_url.path == "/":
            self.send_html_file("index.html")
        elif pr_url.path == "/message.html" or pr_url.path == "/message":
            self.send_html_file("message.html")
        else:
            file_path = BASE_DIR.joinpath(pr_url.path[1:])
            if file_path.exists() and file_path.is_file():
                self.send_static(file_path)
            else:
                self.send_html_file("error.html", 404)

    def do_POST(self):
        pr_url = urllib.parse.urlparse(self.path)

        if pr_url.path == "/message":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)

            self.send_data_to_socket(post_data)
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self.send_html_file("error.html", 404)

    def send_html_file(self, filename, status=200):
        self.send_response(status)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        with open(BASE_DIR.joinpath(filename), "rb") as fd:
            self.wfile.write(fd.read())

    def send_static(self, file_path):
        self.send_response(200)
        mt = mimetypes.guess_type(file_path)
        if mt and mt[0]:
            self.send_header("Content-type", mt[0])
        else:
            self.send_header("Content-type", "application/octet-stream")
        self.end_headers()
        with open(file_path, "rb") as file:
            self.wfile.write(file.read())

    def send_data_to_socket(self, data):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(data, (SOCKET_HOST, SOCKET_PORT))
        sock.close()


def run_http_server():
    server_address = (HTTP_HOST, HTTP_PORT)
    http = HTTPServer(server_address, HttpHandler)
    logging.info(f"HTTP-server started on port {HTTP_PORT}")
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        http.server_close()


def save_to_mongodb(data_bytes):
    try:
        data_parse = urllib.parse.unquote_plus(data_bytes.decode("utf-8"))
        data_dict = {key: value for key, value in [el.split("=", 1) for el in data_parse.split("&") if "=" in el]}

        document = {
            "date": str(datetime.now()),
            "username": data_dict.get("username", ""),
            "message": data_dict.get("message", ""),
        }

        client = MongoClient(MONGO_URI)
        db = client.messages_db
        collection = db.messages
        collection.insert_one(document)
        logging.info(f"Saved to MongoDB: {document}")
        client.close()

    except Exception as e:
        logging.error(f"Error saving data to MongoDB: {e}")


def run_socket_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SOCKET_HOST, SOCKET_PORT))
    logging.info(f"Socket server (UDP) started on port {SOCKET_PORT}")
    try:
        while True:
            data, address = sock.recvfrom(1024)
            logging.info(f"Received data via socket from {address}")
            save_to_mongodb(data)
    except KeyboardInterrupt:
        logging.info("Socket server stopped")
    finally:
        sock.close()


if __name__ == "__main__":
    http_process = Process(target=run_http_server, name="HTTP-Server")
    socket_process = Process(target=run_socket_server, name="Socket-Server")

    http_process.start()
    socket_process.start()

    http_process.join()
    socket_process.join()