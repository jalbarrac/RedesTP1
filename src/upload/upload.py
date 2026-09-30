import argparse
from enum import IntEnum
import socket
import sys
import os


class MessageCodes(IntEnum):
    REQUEST_UPLOAD = 1
    ACCEPT_REQUEST = 2
    REJECT_REQUEST = 3
    DATA_SEND = 4
    DATA_ACK = 5
    REQUEST_DOWNLOAD = 6
    DATA_DONE = 7


# Tiempo de espera (en segundos) antes de retransmitir un mensaje.
TIMEOUT_SEGUNDOS = 0.3
# Cantidad maxima de reintentos antes de abandonar la transferencia.
MAX_REINTENTOS = 10

class ProtocolCodes(IntEnum):
    STOP_AND_WAIT = 1
    SACK = 2

parser = argparse.ArgumentParser(prog="upload", description="Upload a file.")
group = parser.add_mutually_exclusive_group()
group.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
group.add_argument("-q", "--quiet", help="decrease output verbosity", action="store_true")
parser.add_argument("-H", "--host", help="server IP address")
parser.add_argument("-p", "--port", help="server port", type=int)
parser.add_argument("-s", "--src", help="source file path")
parser.add_argument("-n", "--name", help="file name")
parser.add_argument("-r", "--protocol", help="error recovery protocol")

args = parser.parse_args()

if not args.src:
    if "./" not in args.name:
        args.src = "./"
    else:
        args.src = ""

if not os.path.exists(args.src + args.name):
    sys.exit("Error: Path not found.")

client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

file_size_bytes = os.path.getsize(args.src + args.name).to_bytes(4, 'big')



def enviar_y_esperar(mensaje, direccion, codigos_de_respuesta_validos):
    """
    Manda 'mensaje' a 'direccion' y espera una respuesta cuyo primer byte
    este en 'codigos_de_respuesta_validos'. Si no llega a tiempo,
    retransmite el mismo mensaje (Stop & Wait), hasta MAX_REINTENTOS veces.
    """
    for _intento in range(MAX_REINTENTOS):
        client_socket.sendto(mensaje, direccion)
        client_socket.settimeout(TIMEOUT_SEGUNDOS)
        try:
            respuesta, _direccion_origen = client_socket.recvfrom(1024)
        except socket.timeout:
            continue
        if respuesta[0] in codigos_de_respuesta_validos:
            return respuesta
    return None


message = bytes([MessageCodes.REQUEST_UPLOAD, 1]) + file_size_bytes + args.name.encode()
response = enviar_y_esperar(
    message, (args.host, args.port), (MessageCodes.ACCEPT_REQUEST, MessageCodes.REJECT_REQUEST)
)
if response is None:
    sys.exit("Error: el servidor no respondio a la solicitud de upload.")
if response[0] == MessageCodes.REJECT_REQUEST:
    print(response[1:].decode())
elif response[0] == MessageCodes.ACCEPT_REQUEST:
    f = open(args.src + args.name, 'rb')
    data = f.read(1019)
    seqnum = 0
    while data:
        message = bytes([MessageCodes.DATA_SEND]) + seqnum.to_bytes(4, 'big') + data
        respuesta_ack = enviar_y_esperar(message, (args.host, args.port), (MessageCodes.DATA_ACK,))
        if respuesta_ack is None:
            sys.exit(f"Error: se agotaron los reintentos enviando el fragmento {seqnum}.")
        if int.from_bytes(respuesta_ack[1:], 'big') == seqnum:
            data = f.read(1019)
            seqnum = seqnum + 1
    f.close()
    message = bytes([MessageCodes.DATA_DONE])
    confirmacion = enviar_y_esperar(message, (args.host, args.port), (MessageCodes.DATA_DONE,))
    if confirmacion is None:
        print("Advertencia: no se pudo confirmar el fin de la transferencia con el servidor.")
    else:
        print("Archivo enviado correctamente.")
client_socket.close()