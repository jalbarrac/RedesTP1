import argparse
import os
import socket
import sys
from enum import IntEnum


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


WINDOW_SIZE = 64
MAX_TIMEOUTS = 20
MAX_SACK_BLOCKS = 32


parser = argparse.ArgumentParser(
    prog="download",
    description="Download a file.")
group = parser.add_mutually_exclusive_group()
group.add_argument(
    "-v", "--verbose",
    help="increase output verbosity",
    action="store_true")
group.add_argument(
    "-q", "--quiet",
    help="decrease output verbosity",
    action="store_true")
parser.add_argument(
    "-H", "--host",
    required=True,
    help="server IP address")
parser.add_argument(
    "-p", "--port",
    type=int,
    default=54321,
    help="server port")
parser.add_argument(
    "-d", "--dst",
    default="./",
    help="destination file path")
parser.add_argument(
    "-n", "--name",
    required=True,
    help="file name")
parser.add_argument(
    "-r", "--protocol",
    default="saw",
    help="error recovery protocol (saw o sack)")

args = parser.parse_args()

os.makedirs(args.dst, exist_ok=True)
dest_file_path = os.path.join(args.dst, args.name)
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_addr = (args.host, args.port)


def enviar_y_esperar(mensaje, codigos_validos, max_intentos=15, timeout=1.0):
    for _ in range(max_intentos):
        client_socket.sendto(mensaje, server_addr)
        client_socket.settimeout(timeout)
        try:
            respuesta, _ = client_socket.recvfrom(1024)
            if respuesta and respuesta[0] in codigos_validos:
                return respuesta
        except socket.timeout:
            continue
    return None


def recibir_sack(file_obj):
    received_chunks = {}
    cum_ack = 0
    timeouts = 0

    while True:
        try:
            client_socket.settimeout(1.5)
            pkt, _ = client_socket.recvfrom(1024)
        except socket.timeout:
            timeouts += 1
            if timeouts >= MAX_TIMEOUTS:
                return False
            continue

        timeouts = 0
        codigo = pkt[0]
        if codigo == MessageCodes.DATA_DONE:
            client_socket.sendto(bytes([MessageCodes.DATA_DONE]), server_addr)
            break

        if codigo == MessageCodes.DATA_SEND:
            if len(pkt) < 5:
                continue
            seqnum = int.from_bytes(pkt[1:5], 'big')
            data = pkt[5:]

            if seqnum not in received_chunks:
                received_chunks[seqnum] = data

            while cum_ack in received_chunks:
                cum_ack += 1

            out_of_order = [
                s for s in range(cum_ack + 1, cum_ack + WINDOW_SIZE + 1)
                if s in received_chunks]
            blocks = []
            if out_of_order:
                start = out_of_order[0]
                prev = start
                for s in out_of_order[1:]:
                    if s == prev + 1:
                        prev = s
                    else:
                        blocks.append((start, prev + 1))
                        start = s
                        prev = s
                blocks.append((start, prev + 1))

            num_blocks = min(len(blocks), MAX_SACK_BLOCKS)
            ack_buf = bytearray([MessageCodes.DATA_ACK])
            ack_buf.extend(cum_ack.to_bytes(4, 'big'))
            ack_buf.append(num_blocks)

            for left, right in blocks[:num_blocks]:
                ack_buf.extend(left.to_bytes(4, 'big'))
                ack_buf.extend(right.to_bytes(4, 'big'))

            client_socket.sendto(bytes(ack_buf), server_addr)

    for seq in sorted(received_chunks.keys()):
        file_obj.write(received_chunks[seq])
    return True


def recibir_stop_and_wait(file_obj):
    seq_esperado = 0
    while True:
        try:
            client_socket.settimeout(10.0)
            pkt, _ = client_socket.recvfrom(1024)
        except socket.timeout:
            return False

        if pkt[0] == MessageCodes.DATA_SEND:
            seq = int.from_bytes(pkt[1:5], 'big')
            if seq == seq_esperado:
                file_obj.write(pkt[5:])
                seq_esperado += 1
            client_socket.sendto(
                (bytes([MessageCodes.DATA_ACK])
                 + seq.to_bytes(4, 'big')), server_addr)
        elif pkt[0] == MessageCodes.DATA_DONE:
            client_socket.sendto(bytes([MessageCodes.DATA_DONE]), server_addr)
            break
    return True


# Handshake
proto_code = (ProtocolCodes.SACK if args.protocol.lower() == 'sack'
              else ProtocolCodes.STOP_AND_WAIT)
req = bytes([MessageCodes.REQUEST_DOWNLOAD, proto_code]) + args.name.encode()
resp = enviar_y_esperar(req,
                        (MessageCodes.ACCEPT_REQUEST,
                         MessageCodes.REJECT_REQUEST))

if resp is None:
    sys.exit("Error: El servidor no respondió a la solicitud.")
if resp[0] == MessageCodes.REJECT_REQUEST:
    sys.exit(f"Rechazado por el servidor: {resp[1:].decode(errors='replace')}")

with open(dest_file_path, 'wb') as f:
    if proto_code == ProtocolCodes.SACK:
        ok = recibir_sack(f)
    else:
        ok = recibir_stop_and_wait(f)

if not args.quiet:
    if ok:
        print("OK: Archivo descargado con éxito.")
    else:
        print("Error: Falló la descarga.")

client_socket.close()
