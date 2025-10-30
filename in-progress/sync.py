import socket
import os
import hashlib
import binascii

SYNC_HOST = '192.168.100.187'
PORT = 9000

def get_file_length_and_hash(filename):
    stat = os.stat(filename)
    file_length = stat[6]
    buffer = bytearray(file_length)
    open(filename, 'rb').readinto(buffer)
    file_hash = hashlib.md5(buffer).digest()
    file_hash = binascii.hexlify(file_hash).decode()
    return file_length, file_hash

def makedirs(filename):
    paths = filename.split(b'/')
    for p in range(len(paths) - 1):
        path = b"/".join(paths[0:p+1])
        try:
            os.stat(path)
        except OSError:
            os.mkdir(path)
 
def sync_with_server(host, port):
    server_file = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_file.connect((host, port))
        while True:
            line = server_file.readline().split()
            print("Received from server:", line)
            if not line:
                break
            if line[0] == b"HEAD":
                filename = line[1]
                try:
                    file_length, file_hash = get_file_length_and_hash(filename)
                    server_file.write(f"200 {file_length} {file_hash}\n".encode())
                except OSError:
                    server_file.write(b"404\n")
            elif line[0] == b"PUT":
                filename = line[1]
                file_length = int(line[2])
                file_hash = line[3]
                print(f"Receiving file {filename} of length {file_length} and hash {file_hash}")
                makedirs(filename)
                with open(filename, 'wb') as f:
                    remaining = file_length
                    while remaining > 0:
                        chunk_size = min(4096, remaining)
                        chunk = server_file.recv(chunk_size)
                        if not chunk:
                            raise Exception("Connection lost while receiving file")
                        f.write(chunk)
                        remaining -= len(chunk)
                print(f"File {filename} received successfully.")
            else:
                print("Unknown command from server", line)
    finally:
        server_file.close()


def main():
    sync_with_server(SYNC_HOST, PORT)


if __name__ == '__main__':
    main()