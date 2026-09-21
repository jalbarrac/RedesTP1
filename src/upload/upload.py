import argparse
from enum import IntEnum
from socket import *
import os

class MessageCodes(IntEnum):
	REQUEST_UPLOAD = 1
	ACCEPT_UPLOAD = 2
	REJECT_UPLOAD = 3
	DATA_SEND = 4
	DATA_ACK = 5
	REQUEST_DOWNLOAD = 6
	REJECT_DOWNLOAD = 7
	DATA_DONE = 8

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

#TO DO: Validar que el archivo exista.

if not args.src:
    if "./" not in args.name:
        args.src = "./"
    else:
        args.src = ""

client_socket = socket(AF_INET, SOCK_DGRAM)

file_size_bytes = os.path.getsize(args.src+args.name).to_bytes(4,'big')

#solicitar inicio de upload
message = bytes([MessageCodes.REQUEST_UPLOAD,1]) + file_size_bytes + args.name.encode()
client_socket.sendto(message, (args.host, args.port))

response, server_address = client_socket.recvfrom(1024)

if response[0] == MessageCodes.REJECT_UPLOAD:
    print(response[1:].decode())

#TO DO: Generalizar a ambos protocolos
elif response[0] == MessageCodes.ACCEPT_UPLOAD:
    f = open(args.src+args.name, 'br')
    data = f.read(1019)
    seqnum = 0
    while data:
        message = bytes([MessageCodes.DATA_SEND]) + seqnum.to_bytes(4,'big') + data
        client_socket.sendto(message, (args.host, args.port))
        response, server_address = client_socket.recvfrom(1024)
        
        #si recibo ACK, avanzo
        #TO DO: Timeout
        if response[0] == MessageCodes.DATA_ACK and int.from_bytes(response[1:], 'big') == seqnum:
            data = f.read(1019)
            seqnum = seqnum + 1

    message = bytes([MessageCodes.DATA_DONE])
    client_socket.sendto(message, (args.host, args.port))
    f.close()
client_socket.close()
