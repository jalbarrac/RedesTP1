import argparse
from enum import IntEnum
from socket import *
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
parser.add_argument("-H", "--host", help="server IP address")
parser.add_argument("-p", "--port", help="server port", type=int)
parser.add_argument("-s", "--dst", help="destination file path")
parser.add_argument("-n", "--name", help="file name")
parser.add_argument("-r", "--protocol", help="error recovery protocol")

args = parser.parse_args()

if not args.dst:
	args.dst = "./"

client_socket = socket(AF_INET, SOCK_DGRAM)

#solicitar inicio de download
message = bytes([MessageCodes.REQUEST_DOWNLOAD, ProtocolCodes.STOP_AND_WAIT]) + args.name.encode()
client_socket.sendto(message, (args.host, args.port))

response, server_address = client_socket.recvfrom(1024)

if response[0] == MessageCodes.REJECT_REQUEST:
	print(response[1:].decode())

#TO DO: Generalizar a ambos protocolos
elif response[0] == MessageCodes.ACCEPT_REQUEST:
	f = open(args.dst+args.name, 'ba')

	#recibo el archivo
	while True:
		print("esperando paquete de datos del server")
		response, server_address = client_socket.recvfrom(1024)
		if response[0] == MessageCodes.DATA_SEND:
			print("Recibi DATA_SEND")
			f.write(response[5:])
			message = bytes([MessageCodes.DATA_ACK]) + response[1:5]
			client_socket.sendto(message, server_address)
		elif response[0] == MessageCodes.DATA_DONE:
			print("Recibi DATA_DONE")
			break

	#message = bytes([MessageCodes.DATA_DONE])
	#client_socket.sendto(message, (args.host, args.port))
	f.close()
client_socket.close()
