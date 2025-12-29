import sys
import os
import socket
import threading
import hashlib
import binascii

LISTEN_HOST = '0.0.0.0'
LISTEN_PORT = 9000

SKIP_FILES = {'.DS_Store', 'Thumbs.db', "settings.json"}

def get_folder_path():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return 'sample-content'

def get_file_length_and_hash(filename):
    stat = os.stat(filename)
    file_length = stat[6]
    buffer = bytearray(file_length)
    open(filename, 'rb').readinto(buffer)
    file_hash = hashlib.md5(buffer).digest()
    file_hash = binascii.hexlify(file_hash).decode()
    return file_length, file_hash

def scan_files():
    folder_path = get_folder_path()
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file in SKIP_FILES:
                continue
            full_path = os.path.join(root, file)
            yield full_path

def handle_connection(conn, addr):
    print(f"Connection from {addr}")
    with conn.makefile('rwb') as client_file:
        for filename in scan_files():
            file_length, file_hash = get_file_length_and_hash(filename)
            client_file.write(f"HEAD {filename}\n".encode())
            client_file.flush()
            result = client_file.readline().split()
            if result[0] == b"200":
                server_length = int(result[1])
                server_hash = result[2].decode()
                # print(f"File {filename}: server length {server_length}, server hash {server_hash}")
                # print(f"Local length {file_length}, local hash {file_hash}")
                if server_length == file_length and server_hash == file_hash:
                    print(f"File {filename} is up to date.")
                else:
                    print(f"Updating {filename}...")
                    upload_file(client_file, filename, file_length, file_hash)
            elif result[0] == b"404":
                print(f"Uploading {filename}...")
                upload_file(client_file, filename, file_length, file_hash)
            else:
                print(f"Unexpected response for file {filename}: {result}")
    print("finished syncing.")
    conn.close()

def upload_file(client_file, filename, file_length, file_hash):
    client_file.write(f"PUT {filename} {file_length} {file_hash}\n".encode())
    client_file.write(open(filename, 'rb').read())
    client_file.flush()

def listen_for_connections():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    print(f"Listening on port {LISTEN_PORT}...")
    server.listen(5)
    
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_connection, args=(conn, addr))
        thread.start()

def main():
    listen_for_connections()

if __name__ == "__main__":
    main()
