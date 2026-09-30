import argparse
from enum import IntEnum
import socket
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.sack import enviar_archivo_sack

MAX_REINTENTOS = 5
TIMEOUT_SEGUNDOS = 1.0

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

file_path = os.path.join(args.src, args.name)
if not os.path.exists(file_path):
    sys.exit("Error: Path not found.")

client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
file_size_bytes = os.path.getsize(file_path).to_bytes(4, 'big')

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

# Determinar el protocolo elegido
proto_code = ProtocolCodes.SACK if args.protocol and args.protocol.lower() == 'sack' else ProtocolCodes.STOP_AND_WAIT

# Solicitud inicial (Handshake)
message = bytes([MessageCodes.REQUEST_UPLOAD, proto_code]) + file_size_bytes + args.name.encode()
response = enviar_y_esperar(
    message, (args.host, args.port), (MessageCodes.ACCEPT_REQUEST, MessageCodes.REJECT_REQUEST)
)

if response is None:
    sys.exit("Error: el servidor no respondio a la solicitud de upload.")

if response[0] == MessageCodes.REJECT_REQUEST:
    print(response[1:].decode())

elif response[0] == MessageCodes.ACCEPT_REQUEST:
    f = open(file_path, 'rb')
    
    # SELECCIÓN DE PROTOCOLO
    if proto_code == ProtocolCodes.SACK:
        # Transferencia usando SACK
        ok = enviar_archivo_sack(client_socket, (args.host, args.port), f)
        if ok:
            print("Archivo enviado correctamente con SACK.")
        else:
            print("Error: no se pudo completar el envío con SACK.")
    else:
        # Transferencia usando Stop & Wait
        data = f.read(1019)
        seqnum = 0
        while data:
            message = bytes([MessageCodes.DATA_SEND]) + seqnum.to_bytes(4, 'big') + data
            respuesta_ack = enviar_y_esperar(message, (args.host, args.port), (MessageCodes.DATA_ACK,))
            if respuesta_ack is None:
                f.close()
                sys.exit(f"Error: se agotaron los reintentos enviando el fragmento {seqnum}.")
            if int.from_bytes(respuesta_ack[1:], 'big') == seqnum:
                data = f.read(1019)
                seqnum += 1
        
        message = bytes([MessageCodes.DATA_DONE])
        confirmacion = enviar_y_esperar(message, (args.host, args.port), (MessageCodes.DATA_DONE,))
        if confirmacion is None:
            print("Advertencia: no se pudo confirmar el fin de la transferencia con el servidor.")
        else:
            print("Archivo enviado correctamente con Stop & Wait.")
            
    f.close()

client_socket.close()