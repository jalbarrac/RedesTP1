import time
import socket
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


WINDOW_SIZE = 10
TIMEOUT_SEC = 0.5
MAX_PAYLOAD = 1019
MAX_TIMEOUTS = 10          # timeouts seguidos antes de abortar
MAX_SACK_BLOCKS = 4


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
    timeouts_seguidos = 0

    def armar_pkt(seq):
        return bytes([MessageCodes.DATA_SEND]) + seq.to_bytes(4, 'big') + chunks[seq]

    def recibir_ack_nonblocking():
        if queue_in is not None:
            try:
                return queue_in.get_nowait()
            except queue.Empty:
                return None
        else:
            try:
                sock.settimeout(0.01)
                data, _ = sock.recvfrom(1024)
                return data
            except (socket.timeout, ConnectionResetError):
                return None

    while base < total_chunks:
        # 1. Enviar datos respetando el tamaño de ventana
        while next_seqnum < base + WINDOW_SIZE and next_seqnum < total_chunks:
            if next_seqnum not in acks_recibidos:
                sock.sendto(armar_pkt(next_seqnum), dest_addr)
            next_seqnum += 1
        if timer_start is None and base < next_seqnum:
            timer_start = time.time()

        # 2. Procesar TODOS los ACKs disponibles
        while True:
            ack_pkt = recibir_ack_nonblocking()
            if ack_pkt is None:
                break
            if len(ack_pkt) < 6 or ack_pkt[0] != MessageCodes.DATA_ACK:
                continue

            cum_ack = int.from_bytes(ack_pkt[1:5], 'big')
            num_blocks = ack_pkt[5]

            for i in range(base, min(cum_ack, total_chunks)):
                acks_recibidos.add(i)

            offset = 6
            for _ in range(num_blocks):
                if offset + 8 > len(ack_pkt):
                    break
                left = int.from_bytes(ack_pkt[offset:offset + 4], 'big')
                right = int.from_bytes(ack_pkt[offset + 4:offset + 8], 'big')
                for seq in range(left, min(right, total_chunks)):
                    acks_recibidos.add(seq)
                offset += 8

        # 3. Avanzar la base (una sola vez, después de drenar los ACKs)
        base_anterior = base
        while base in acks_recibidos:
            base += 1
        if base != base_anterior:
            timeouts_seguidos = 0
            timer_start = time.time() if base < next_seqnum else None

        # 4. Control de Timeout (Retransmisión Selectiva)
        if timer_start is not None and (time.time() - timer_start > TIMEOUT_SEC):
            timeouts_seguidos += 1
            if timeouts_seguidos >= MAX_TIMEOUTS:
                print("Timeout: el receptor dejó de responder. Se aborta el envío.")
                return False
            for seq in range(base, min(base + WINDOW_SIZE, total_chunks)):
                if seq not in acks_recibidos:
                    sock.sendto(armar_pkt(seq), dest_addr)
            timer_start = time.time()

    # Enviar DATA_DONE y esperar la confirmación, ignorando ACKs viejos
    done_pkt = bytes([MessageCodes.DATA_DONE])
    for _ in range(10):
        sock.sendto(done_pkt, dest_addr)
        deadline = time.time() + 0.5
        while time.time() < deadline:
            restante = max(0.01, deadline - time.time())
            try:
                if queue_in is not None:
                    res = queue_in.get(timeout=restante)
                else:
                    sock.settimeout(restante)
                    res, _ = sock.recvfrom(1024)
            except (queue.Empty, socket.timeout, ConnectionResetError):
                break
            if res and res[0] == MessageCodes.DATA_DONE:
                return True
    return False


def recibir_archivo_sack(sock, dest_addr, file_obj, queue_in=None):
    """
    Recibe paquetes de datos usando SACK y los escribe en 'file_obj'.
    Devuelve True si terminó bien, False si abortó por timeouts.
    """
    received_chunks = {}
    cum_ack = 0
    timeouts_seguidos = 0

    def recibir_pkt():
        if queue_in is not None:
            try:
                return queue_in.get(timeout=2.0)
            except queue.Empty:
                return None
        else:
            try:
                sock.settimeout(2.0)
                data, _ = sock.recvfrom(1024)
                return data
            except (socket.timeout, ConnectionResetError):
                return None

    while True:
        pkt = recibir_pkt()
        if not pkt:
            timeouts_seguidos += 1
            if timeouts_seguidos >= MAX_TIMEOUTS:
                print("Timeout: el emisor dejó de responder. Se aborta la recepción.")
                return False
            continue
        timeouts_seguidos = 0

        codigo = pkt[0]
        if codigo == MessageCodes.DATA_DONE:
            # Confirmar fin de transmisión
            sock.sendto(bytes([MessageCodes.DATA_DONE]), dest_addr)
            break

        if codigo == MessageCodes.DATA_SEND:
            seqnum = int.from_bytes(pkt[1:5], 'big')
            data = pkt[5:]

            if seqnum not in received_chunks:
                received_chunks[seqnum] = data

            # Actualizar Cumulative ACK
            while cum_ack in received_chunks:
                cum_ack += 1

            # Bloques SACK: solo se mira la ventana cercana a cum_ack
            out_of_order = [s for s in range(cum_ack + 1, cum_ack + WINDOW_SIZE + 1)
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

            sock.sendto(bytes(ack_buf), dest_addr)

    # Escribir el archivo ordenado al finalizar
    for seq in sorted(received_chunks.keys()):
        file_obj.write(received_chunks[seq])
    return True