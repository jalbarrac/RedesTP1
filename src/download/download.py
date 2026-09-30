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

class ProtocolCodes(IntEnum):
    STOP_AND_WAIT = 1
    SACK = 2

parser = argparse.ArgumentParser(prog="download", description="Download a file.")
group = parser.add_mutually_exclusive_group()
group.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
group.add_argument("-q", "--quiet", help="decrease output verbosity", action="store_true")
parser.add_argument("-H", "--host", help="server IP address", required=True)
parser.add_argument("-p", "--port", help="server port", type=int, required=True)
parser.add_argument("-d", "--dst", help="destination file path")
parser.add_argument("-n", "--name", help="file name", required=True)
parser.add_argument("-r", "--protocol", help="error recovery protocol")

args = parser.parse_args()

if not args.dst:
	args.dst = "./"

client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

MAX_REINTENTOS = 5
TIMEOUT_SEGUNDOS = 1.0

def stop_and_wait(mensaje, direccion, codigos_de_respuesta_validos):	
	for intento in range(MAX_REINTENTOS):
		client_socket.sendto(mensaje, direccion)
		client_socket.settimeout(TIMEOUT_SEGUNDOS)
		try:
			respuesta, _direccion_origen = client_socket.recvfrom(1024)
		except socket.timeout:
			continue
		if respuesta[0]  in codigos_de_respuesta_validos:
			return respuesta
	return None


#solicitar inicio de download

message = bytes([MessageCodes.REQUEST_DOWNLOAD, 1]) + args.name.encode()
response = stop_and_wait(
    message, (args.host, args.port), (MessageCodes.ACCEPT_REQUEST, MessageCodes.REJECT_REQUEST)
)


if response is None:
	sys.exit("Error: el servidor no respondió a la solicitud de download.")

if response[0] == MessageCodes.REJECT_REQUEST:
	print(response[1:].decode())


elif response[0] == MessageCodes.ACCEPT_REQUEST:
	f = open(args.dst+args.name, 'wb')
	numero_secuencia_esperado = 0
	#recibo el archivo
	while True:
		client_socket.settimeout(TIMEOUT_SEGUNDOS * MAX_REINTENTOS)
		try : 
			print("esperando paquete de datos del server")
			response, server_address = client_socket.recvfrom(1024)
		except socket.timeout:
			f.close()
			sys.exit("Error: timeout esperando datos del servidor. Se aborta la descarga.")
		if response[0] == MessageCodes.DATA_SEND:
			numero_secuencia = int.from_bytes(response[1:5], 'big')
			if numero_secuencia == numero_secuencia_esperado:
				f.write(response[5:])
				numero_secuencia_esperado += 1
			
			message = bytes([MessageCodes.DATA_ACK]) + numero_secuencia.to_bytes(4, 'big')
			client_socket.sendto(message, server_address)
		elif response[0] == MessageCodes.DATA_DONE:
			client_socket.sendto(bytes([MessageCodes.DATA_DONE]), server_address)
			print("Archivo descargado correctamente.")
			break
	f.close()
client_socket.close()
