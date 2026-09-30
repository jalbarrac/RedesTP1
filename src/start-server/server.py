from socket import *
import argparse
import threading
import queue
import os
import sys
from enum import IntEnum


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.sack import enviar_archivo_sack, recibir_archivo_sack

class MessageCodes(IntEnum):
    REQUEST_UPLOAD = 1
    ACCEPT_REQUEST = 2
    REJECT_REQUEST = 3
    DATA_SEND = 4
    DATA_ACK = 5
    REQUEST_DOWNLOAD = 6
    DATA_DONE = 7

class ProtocolCodes(IntEnum):
    STOP_AND_WAIT = 1
    SACK = 2

def filename_ok(string):
    return True

def filesize_ok(size):
    return size < 1073741824

TIMEOUT_SEGUNDOS = 1
MAX_REINTENTOS = 10

parser = argparse.ArgumentParser(prog="start-server", description="Upload a file.")
group = parser.add_mutually_exclusive_group()
group.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
group.add_argument("-q", "--quiet", help="decrease output verbosity", action="store_true")
parser.add_argument("-H", "--host", help="service IP address")
parser.add_argument("-p", "--port", help="service port", type=int)
parser.add_argument("-s", "--storage", help="storage dir path")

args = parser.parse_args()

if not args.host:
    args.host = ''

if not args.port:
    args.port = 54321

# Configurar directorio de almacenamiento
storage_dir = args.storage if args.storage else "./"
if not os.path.exists(storage_dir):
    os.makedirs(storage_dir, exist_ok=True)

server_socket = socket(AF_INET, SOCK_DGRAM)
server_socket.bind((args.host, args.port))
print("Listening...")

sesiones_activas = {}
lock_sesiones = threading.Lock()


def atender_upload(mensaje_solicitud, client_address, cola_mensajes):
    try:
        proto_code = mensaje_solicitud[1]
        file_size = int.from_bytes(mensaje_solicitud[2:6], 'big')
        filename = mensaje_solicitud[6:].decode()

        if not filename_ok(filename):
            response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - Filename not ok.".encode()
            server_socket.sendto(response, client_address)
            return
        elif not filesize_ok(file_size):
            response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - File too big.".encode()
            server_socket.sendto(response, client_address)
            return

        response = bytes([MessageCodes.ACCEPT_REQUEST])
        server_socket.sendto(response, client_address)

        filepath = os.path.join(storage_dir, filename)
        f = open(filepath, 'wb')

        if proto_code == ProtocolCodes.SACK:
            recibir_archivo_sack(server_socket, client_address, f, queue_in=cola_mensajes)
            print("Success (SACK). Received file: " + filename)
        else:
            numero_secuencia_esperado = 0
            while True:
                try:
                    mensaje = cola_mensajes.get(timeout=TIMEOUT_SEGUNDOS * MAX_REINTENTOS)
                except queue.Empty:
                    print(f"Timeout esperando datos de {client_address}. Se aborta la sesion.")
                    f.close()
                    return
                if mensaje[0] == MessageCodes.DATA_SEND:
                    numero_secuencia = int.from_bytes(mensaje[1:5], 'big')
                    if numero_secuencia == numero_secuencia_esperado:
                        f.write(mensaje[5:])
                        numero_secuencia_esperado += 1
                    response = bytes([MessageCodes.DATA_ACK]) + numero_secuencia.to_bytes(4, 'big')
                    server_socket.sendto(response, client_address)
                elif mensaje[0] == MessageCodes.DATA_DONE:
                    server_socket.sendto(bytes([MessageCodes.DATA_DONE]), client_address)
                    print("Success (Stop & Wait). Received file: " + filename)
                    break
        f.close()
    finally:
        with lock_sesiones:
            if sesiones_activas.get(client_address) is cola_mensajes:
                del sesiones_activas[client_address]


def atender_download(mensaje_solicitud, client_address, cola_mensajes):
    try:
        proto_code = mensaje_solicitud[1]
        filename = mensaje_solicitud[2:].decode()

        if not filename_ok(filename):
            response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - Filename not ok.".encode()
            server_socket.sendto(response, client_address)
            return

        filepath = os.path.join(storage_dir, filename)
        try:
            f = open(filepath, 'rb')
        except FileNotFoundError:
            response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - File not found.".encode()
            server_socket.sendto(response, client_address)
            return

        response = bytes([MessageCodes.ACCEPT_REQUEST])
        server_socket.sendto(response, client_address)

        if proto_code == ProtocolCodes.SACK:
            enviar_archivo_sack(server_socket, client_address, f, queue_in=cola_mensajes)
            print("Archivo enviado (SACK): " + filename)
        else:
            data = f.read(1019)
            numero_secuencia = 0
            while data:
                paquete = bytes([MessageCodes.DATA_SEND]) + numero_secuencia.to_bytes(4, 'big') + data
                confirmado = False
                intentos = 0
                while not confirmado and intentos < MAX_REINTENTOS:
                    server_socket.sendto(paquete, client_address)
                    try:
                        mensaje = cola_mensajes.get(timeout=TIMEOUT_SEGUNDOS)
                        if (
                            mensaje[0] == MessageCodes.DATA_ACK
                            and int.from_bytes(mensaje[1:], 'big') == numero_secuencia
                        ):
                            confirmado = True
                    except queue.Empty:
                        intentos += 1
                if not confirmado:
                    print(f"Se agotaron los reintentos enviando a {client_address}. Se aborta la sesion.")
                    f.close()
                    return
                data = f.read(1019)
                numero_secuencia += 1

            confirmado = False
            intentos = 0
            while not confirmado and intentos < MAX_REINTENTOS:
                server_socket.sendto(bytes([MessageCodes.DATA_DONE]), client_address)
                try:
                    mensaje = cola_mensajes.get(timeout=TIMEOUT_SEGUNDOS)
                    if mensaje[0] == MessageCodes.DATA_DONE:
                        confirmado = True
                except queue.Empty:
                    intentos += 1
            print("Archivo enviado (Stop & Wait): " + filename)
        f.close()
    finally:
        with lock_sesiones:
            if sesiones_activas.get(client_address) is cola_mensajes:
                del sesiones_activas[client_address]


while True:
    mensaje, client_address = server_socket.recvfrom(1024)
    codigo = mensaje[0]

    if codigo == MessageCodes.REQUEST_UPLOAD:
        cola_mensajes = queue.Queue()
        with lock_sesiones:
            sesiones_activas[client_address] = cola_mensajes
        hilo = threading.Thread(
            target=atender_upload, args=(mensaje, client_address, cola_mensajes), daemon=True
        )
        hilo.start()

    elif codigo == MessageCodes.REQUEST_DOWNLOAD:
        cola_mensajes = queue.Queue()
        with lock_sesiones:
            sesiones_activas[client_address] = cola_mensajes
        hilo = threading.Thread(
            target=atender_download, args=(mensaje, client_address, cola_mensajes), daemon=True
        )
        hilo.start()

    else:
        with lock_sesiones:
            cola_mensajes = sesiones_activas.get(client_address)
        if cola_mensajes is not None:
            cola_mensajes.put(mensaje)

server_socket.close()