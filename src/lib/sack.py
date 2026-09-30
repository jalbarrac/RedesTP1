import time
import socket
from enum import IntEnum

class MessageCodes(IntEnum):
    REQUEST_UPLOAD = 1
    ACCEPT_REQUEST = 2
    REJECT_REQUEST = 3
    DATA_SEND = 4
    DATA_ACK = 5
    REQUEST_DOWNLOAD = 6
    DATA_DONE = 7

WINDOW_SIZE = 10
TIMEOUT_SEC = 0.5
MAX_PAYLOAD = 1019

def enviar_archivo_sack(sock, dest_addr, file_obj, queue_in=None):
    """
    Envía datos leídos de 'file_obj' hacia 'dest_addr' usando SACK.
    Si 'queue_in' no es None, lee ACKs de esa Queue (modo Servidor Multithread).
    Si es None, los lee directamente de 'sock' (modo Cliente).
    """
    chunks = []
    while True:
        chunk = file_obj.read(MAX_PAYLOAD)
        if not chunk:
            break
        chunks.append(chunk)

    total_chunks = len(chunks)
    base = 0             # Primer paquete sin confirmar
    next_seqnum = 0      # Próximo paquete a enviar
    acks_recibidos = set()
    timer_start = None

    def recibir_ack_nonblocking():
        if queue_in is not None:
            try:
                return queue_in.get_nowait()
            except Exception:
                return None
        else:
            try:
                sock.settimeout(0.01)
                data, _ = sock.recvfrom(1024)
                return data
            except socket.timeout:
                return None

    while base < total_chunks:
        # 1. Enviar datos respetando el tamaño de ventana
        while next_seqnum < base + WINDOW_SIZE and next_seqnum < total_chunks:
            if next_seqnum not in acks_recibidos:
                pkt = bytes([MessageCodes.DATA_SEND]) + next_seqnum.to_bytes(4, 'big') + chunks[next_seqnum]
                sock.sendto(pkt, dest_addr)
                if base == next_seqnum:
                    timer_start = time.time()
            next_seqnum += 1

        # 2. Procesar respuestas/ACKs entrantes
        ack_pkt = recibir_ack_nonblocking()
        if ack_pkt and ack_pkt[0] == MessageCodes.DATA_ACK:
            cum_ack = int.from_bytes(ack_pkt[1:5], 'big')
            num_blocks = ack_pkt[5]
            
            # Registrar bloques ACK acumulativos y fuera de orden
            for i in range(cum_ack):
                acks_recibidos.add(i)

            offset = 6
            for _ in range(num_blocks):
                left = int.from_bytes(ack_pkt[offset:offset+4], 'big')
                right = int.from_bytes(ack_pkt[offset+4:offset+8], 'big')
                for seq in range(left, right):
                    acks_recibidos.add(seq)
                offset += 8

            # Avanzar la base
            while base in acks_recibidos:
                base += 1
                timer_start = time.time() if base < next_seqnum else None

        # 3. Control de Timeout (Retransmisión Selectiva)
        if timer_start and (time.time() - timer_start > TIMEOUT_SEC):
            # Retransmitir solo los paquetes de la ventana no confirmados
            for seq in range(base, min(base + WINDOW_SIZE, total_chunks)):
                if seq not in acks_recibidos:
                    pkt = bytes([MessageCodes.DATA_SEND]) + seq.to_bytes(4, 'big') + chunks[seq]
                    sock.sendto(pkt, dest_addr)
            timer_start = time.time()

    # --- AGREGADO: Enviar señal DATA_DONE al finalizar la transferencia de datos ---
    done_pkt = bytes([MessageCodes.DATA_DONE])
    confirmado = False
    for _ in range(10):
        sock.sendto(done_pkt, dest_addr)
        if queue_in is not None:
            try:
                res = queue_in.get(timeout=0.2)
                if res[0] == MessageCodes.DATA_DONE:
                    confirmado = True
                    break
            except Exception:
                pass
        else:
            try:
                sock.settimeout(0.2)
                res, _ = sock.recvfrom(1024)
                if res[0] == MessageCodes.DATA_DONE:
                    confirmado = True
                    break
            except socket.timeout:
                pass


def recibir_archivo_sack(sock, dest_addr, file_obj, queue_in=None):
    """
    Recibe paquetes de datos usando SACK y los escribe en 'file_obj'.
    """
    received_chunks = {}
    cum_ack = 0

    def recibir_pkt():
        if queue_in is not None:
            try:
                return queue_in.get(timeout=2.0)
            except Exception:
                return None
        else:
            try:
                sock.settimeout(2.0)
                data, _ = sock.recvfrom(1024)
                return data
            except socket.timeout:
                return None

    while True:
        pkt = recibir_pkt()
        if not pkt:
            continue

        codigo = pkt[0]
        if codigo == MessageCodes.DATA_DONE:
            # Confirmar fin de transmisión enviando DATA_DONE de regreso
            ack = bytes([MessageCodes.DATA_DONE])
            sock.sendto(ack, dest_addr)
            break

        if codigo == MessageCodes.DATA_SEND:
            seqnum = int.from_bytes(pkt[1:5], 'big')
            data = pkt[5:]

            if seqnum not in received_chunks:
                received_chunks[seqnum] = data

            # Actualizar Cumulative ACK
            while cum_ack in received_chunks:
                cum_ack += 1

            # Armar Bloques SACK con secuencias fuera de orden > cum_ack
            out_of_order = sorted([s for s in received_chunks.keys() if s > cum_ack])
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

            # Construir paquete ACK SACK
            num_blocks = min(len(blocks), 4) # Limitar a 4 bloques máximo
            ack_buf = bytearray([MessageCodes.DATA_ACK])
            ack_buf.extend(cum_ack.to_bytes(4, 'big'))
            ack_buf.append(num_blocks)

            for left, right in blocks[:num_blocks]:
                ack_buf.extend(left.to_bytes(4, 'big'))
                ack_buf.extend(right.to_bytes(4, 'big'))

            sock.sendto(ack_buf, dest_addr)

    # Escribir el archivo ordenado al finalizar
    for seq in sorted(received_chunks.keys()):
        file_obj.write(received_chunks[seq])