from socket import *
import argparse
import threading
import queue
from enum import IntEnum

class MessageCodes(IntEnum):
	REQUEST_UPLOAD = 1
	ACCEPT_REQUEST = 2
	REJECT_REQUEST = 3
	DATA_SEND = 4
	DATA_ACK = 5
	REQUEST_DOWNLOAD = 6
	DATA_DONE = 7

def filename_ok(string):
	return True

def filesize_ok(size):
	return size < 1073741824

#Tiempo de espera (segundos) antes de considerar que un mensaje se perdió
TIMEOUT_SEGUNDOS = 1

# Cantidad maxima de reintentos antes de abandonar una sesion con un cliente
MAX_REINTENTOS = 10

parser = argparse.ArgumentParser(prog="start-server", description="Upload a file.")
group = parser.add_mutually_exclusive_group()
group.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
group.add_argument("-q", "--quiet", help="decrease output verbosity", action="store_true")
parser.add_argument("-H", "--host", help="service IP address")
parser.add_argument("-p", "--port", help="service port", type=int)
parser.add_argument("-s", "--storage", help="storage dir path")

args = parser.parse_args()

#cfg
if not args.host:
	args.host = ''

if not args.port:
	args.port = 54321

server_socket = socket(AF_INET, SOCK_DGRAM)
server_socket.bind((args.host, args.port))
print("Listening...")

# Diccionario que asocia la direccion (IP, puerto) de cada cliente con la
# cola de mensajes que su hilo dedicado va leyendo. Con esto alcanza UN
# SOLO socket para atender a varios clientes en simultaneo: el hilo
# principal solo recibe datagramas y los reparte; cada hilo hijo procesa
# su propia transferencia sin bloquear a los demas clientes.
sesiones_activas = {}
lock_sesiones = threading.Lock()

 
"""
Atiende una transferencia de UPLOAD completa para un cliente:
valida el pedido, responde ACCEPT/REJECT y despues recibe el
archivo con Stop & Wait, controlando duplicados por numero de
secuencia.
"""
def atender_upload(mensaje_solicitud, client_address, cola_mensajes):
    try:
        if not filename_ok(mensaje_solicitud[6:].decode()):
            response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - Filename not ok.".encode()
            server_socket.sendto(response, client_address)
            return
        elif not filesize_ok(int.from_bytes(mensaje_solicitud[2:6], 'big')):
            response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - File too big.".encode()
            server_socket.sendto(response, client_address)
            return
        response = bytes([MessageCodes.ACCEPT_REQUEST])
        server_socket.sendto(response, client_address)
 
        filename = mensaje_solicitud[6:].decode()
        # TO DO: variar segun el protocolo (Stop & Wait / SACK)
        # 'wb' y no 'ba': si el archivo ya existia, lo sobreescribe en vez
        # de pegarle los datos nuevos atras (lo que lo dejaria corrupto).
        f = open(filename, 'wb')
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
                print("Success. Received file: " + filename)
                f.close()
                return
    finally:
        with lock_sesiones:
            if sesiones_activas.get(client_address) is cola_mensajes:
                del sesiones_activas[client_address]
 

"""
Atiende una transferencia de DOWNLOAD completa para un cliente:
valida el pedido, responde ACCEPT/REJECT y despues envia el
archivo con Stop & Wait, reintentando ante perdida de paquetes.
"""
def atender_download(mensaje_solicitud, client_address, cola_mensajes):
    try:
        filename = mensaje_solicitud[2:].decode()
        if not filename_ok(filename):
            response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - Filename not ok.".encode()
            server_socket.sendto(response, client_address)
            return
        try:
            f = open(filename, 'rb')
        except FileNotFoundError:
            response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - File not found.".encode()
            server_socket.sendto(response, client_address)
            return
        response = bytes([MessageCodes.ACCEPT_REQUEST])
        server_socket.sendto(response, client_address)
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
                    ack_es_de_este_fragmento = (
                        mensaje[0] == MessageCodes.DATA_ACK
                        and int.from_bytes(mensaje[1:], 'big') == numero_secuencia
                    )
                    if ack_es_de_este_fragmento:
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
        print("Archivo enviado: " + filename)
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
        # Mensaje de una transferencia en curso (DATA_SEND, DATA_ACK, DATA_DONE):
        # se lo entregamos a la cola del hilo que esta atendiendo a ese cliente.
        with lock_sesiones:
            cola_mensajes = sesiones_activas.get(client_address)
        if cola_mensajes is not None:
            cola_mensajes.put(mensaje)
        # si no hay sesion activa para esa direccion, el mensaje llego
        # tarde (la sesion ya termino) y simplemente se descarta.
 
server_socket.close()