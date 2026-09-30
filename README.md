# Redes TP1

Trabajo Práctico 1 de Redes. Implementación de transferencia de archivos mediante UDP, con dos protocolos de recuperación de errores: **Stop & Wait** y **Selective Repeat con SACK**.

## Requisitos

- Python 3
- Mininet
- XTerm

## Estructura

```text
src/
├── lib/sack.py            # Emisor y receptor SACK (compartido por cliente y servidor)
├── start-server/server.py # Servidor
├── upload/upload.py       # Cliente de upload
├── download/download.py   # Cliente de download
└── topology.py            # Topología de Mininet
```

## Parámetros

| Programa | Parámetro | Descripción |
|----------|-----------|-------------|
| server | `-H`, `--host` | IP en la que escucha (por defecto, todas) |
| server | `-p`, `--port` | Puerto (por defecto, 54321) |
| server | `-s`, `--storage` | Directorio donde se guardan los archivos |
| upload | `-H`, `--host` / `-p`, `--port` | IP y puerto del servidor |
| upload | `-s`, `--src` | Directorio del archivo a subir |
| upload | `-n`, `--name` | Nombre del archivo |
| upload | `-r`, `--protocol` | `sack` para usar SACK. Si se omite, usa Stop & Wait |
| download | `-H`, `--host` / `-p`, `--port` | IP y puerto del servidor |
| download | `-d`, `--dst` | Directorio donde se guarda el archivo descargado |
| download | `-n`, `--name` | Nombre del archivo |
| download | `-r`, `--protocol` | `sack` para usar SACK. Si se omite, usa Stop & Wait |

Todos aceptan `-v` (verbose) y `-q` (quiet).

## Ejecución local

### Servidor

```bash
cd src/start-server
python3 server.py -p 54321 -s ./storage
```

### Upload

```bash
cd src/upload
# Stop & Wait (por defecto)
python3 upload.py -H 127.0.0.1 -p 54321 -s ./client_files -n nombre_archivo

# SACK
python3 upload.py -H 127.0.0.1 -p 54321 -s ./client_files -n nombre_archivo -r sack
```

### Download

```bash
cd src/download
# Stop & Wait (por defecto)
python3 download.py -H 127.0.0.1 -p 54321 -d ./downloads -n nombre_archivo

# SACK
python3 download.py -H 127.0.0.1 -p 54321 -d ./downloads -n nombre_archivo -r sack
```

El protocolo lo elige el cliente. El servidor lo lee del mensaje de solicitud y usa el mismo para esa transferencia.

## Ejecución con Mininet

Iniciar la topología:

```bash
cd src
python3 topology.py
```

Luego, en la consola de Mininet:

```text
xterm h1 h2
```

### h2 — Servidor

```bash
cd src/start-server
python3 server.py -p 54321 -s ./storage
```

### h1 — Cliente

La IP que se usa en `-H` es la del host donde corre el servidor (en este caso h2, `10.0.0.2`).

**Upload:**

```bash
cd src/upload
python3 upload.py -H 10.0.0.2 -p 54321 -s ./client_files -n nombre_archivo -r sack
```

**Download:**

```bash
cd src/download
python3 download.py -H 10.0.0.2 -p 54321 -d ./downloads -n nombre_archivo -r sack
```

Para verificar que la transferencia salió idéntica al original:

```bash
cmp client_files/nombre_archivo downloads/nombre_archivo && echo "OK: archivos idénticos"
```

## Protocolos de recuperación de errores

### Stop & Wait

Se envía un paquete de datos por vez. El emisor no manda el siguiente hasta recibir el ACK del actual. Si el ACK no llega dentro del timeout, retransmite el mismo paquete, hasta un máximo de reintentos. Es simple, pero solo hay un paquete en vuelo, por lo que el caudal queda limitado por el RTT.

### SACK (Selective Acknowledgment)

El emisor mantiene una **ventana deslizante** y puede tener varios paquetes en vuelo a la vez. El receptor acepta paquetes fuera de orden y los guarda hasta completar la secuencia. En cada paquete recibido responde con un ACK que informa:

- **ACK acumulativo** (`cum_ack`): todos los paquetes con número de secuencia menor que este valor ya fueron recibidos.
- **Bloques SACK**: rangos `[left, right)` de paquetes recibidos fuera de orden, por encima de `cum_ack`. Se informan hasta 4 bloques por ACK.

Con esa información el emisor sabe exactamente qué paquetes faltan y, ante un timeout, **retransmite solo los que no fueron confirmados** dentro de la ventana, en lugar de todos los posteriores a la pérdida.

Parámetros (definidos en `src/lib/sack.py`):

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `WINDOW_SIZE` | 64 | Paquetes máximos en vuelo |
| `TIMEOUT_SEC` | 0.5 s | Timeout de retransmisión |
| `MAX_PAYLOAD` | 1019 bytes | Datos por paquete |
| `MAX_SACK_BLOCKS` | 4 | Bloques SACK máximos por ACK |
| `MAX_TIMEOUTS` | 10 | Timeouts seguidos sin progreso antes de abortar |

Si el emisor o el receptor acumulan `MAX_TIMEOUTS` timeouts seguidos sin avanzar, la transferencia se aborta con un mensaje de error en lugar de quedar colgada.

**Fin de la transferencia:** el emisor manda `DATA_DONE` con reintentos y espera que el receptor lo devuelva como confirmación. El receptor escribe el archivo en disco recién cuando recibe `DATA_DONE`, ordenando los fragmentos por número de secuencia.


# Cuestionario

1. **Describa la arquitectura Cliente-Servidor.**

En la arquitectura Cliente-Servidor existe un host siempre activo, denominado servidor, que da servicio a las solicitudes de muchos otros hosts, que son los clientes. Generalmente, la comunicación siempre es iniciada por un cliente, quien le manda una petición al servidor y éste la responde. Otra característica importante del modelo es que los clientes normalmente no pueden comunicarse entre sí. En muchas ocasiones, un único host servidor es incapaz de responder a todas las peticiones de los clientes, por ello se suele utilizar un datacenter, que alberga un gran número de hosts, para crear un servidor virtual de gran capacidad.

2. ¿Cuál es la función de un protocolo de capa de aplicación?

Un protocolo de la capa de aplicación define como los procesos de una aplicación, que se ejecutan en distintos end systems, se pasan los mensajes entre si. En ese sentido, se definen los tipos de mensajes intercambiados (ya sean requests y responses), los campos de un mensaje y como se delimitan, su semántica e información y las reglas para determinar cuando y como un proceso envia mensajes y responde a los mismos.

3. Detalle el protocolo de aplicación desarrollado en este trabajo.

El protocolo corre sobre UDP. El primer byte de cada mensaje es un código que indica su tipo:

| Código | Mensaje | Formato |
|--------|---------|---------|
| 1 | `REQUEST_UPLOAD` | `[1][protocolo: 1B][tamaño del archivo: 4B][nombre]` |
| 6 | `REQUEST_DOWNLOAD` | `[6][protocolo: 1B][nombre]` |
| 2 | `ACCEPT_REQUEST` | `[2]` |
| 3 | `REJECT_REQUEST` | `[3][mensaje de error]` |
| 4 | `DATA_SEND` | `[4][nº de secuencia: 4B][datos: hasta 1019B]` |
| 5 | `DATA_ACK` (Stop & Wait) | `[5][nº de secuencia: 4B]` |
| 5 | `DATA_ACK` (SACK) | `[5][cum_ack: 4B][cantidad de bloques: 1B][bloques: (left: 4B, right: 4B) × n]` |
| 7 | `DATA_DONE` | `[7]` |

El byte de protocolo vale 1 para Stop & Wait y 2 para SACK. Los enteros se codifican en big endian. Cada datagrama tiene como máximo 1024 bytes.

Flujo de una transferencia:

1. El cliente envía `REQUEST_UPLOAD` (con el tamaño del archivo) o `REQUEST_DOWNLOAD`. Si no recibe respuesta, reintenta hasta un máximo de veces.
2. El servidor responde `ACCEPT_REQUEST`, o `REJECT_REQUEST` con el motivo (por ejemplo, archivo demasiado grande o inexistente).
3. El emisor manda los fragmentos del archivo en mensajes `DATA_SEND` numerados y el receptor los confirma con `DATA_ACK`, según el protocolo elegido (Stop & Wait o SACK).
4. Al terminar, el emisor envía `DATA_DONE` y el receptor lo devuelve como confirmación.

El servidor atiende cada cliente en un hilo propio. El hilo principal recibe los datagramas y los reparte, según la dirección del cliente, a una cola por sesión.

4. La capa de transporte del stack TCP/IP ofrece dos protocolos: TCP y UDP. ¿Qué servicios proveen dichos protocolos?
¿Cuáles son sus características? ¿Cuándo es apropiado utilizar cada uno?

El protocolo TCP es un protocolo proporciona un servicio de transferencia de datos fiable, lo cual significa que asegura que los datos enviados del origen lleguen a destino sin perderse en el camino, en el orden correcto y sin errores. Este protocolo es orientado a la conexión, es decir que TCP antes de enviar los datos establece una conexión entre los dos procesos (se realiza mediante Three-way Handshake), también ofrece un control de congestión (su objetivo es evitar que el emisor envíe datos a una velocidad que termine saturando la red) y un control de flujo (regular la cantidad de datos enviados para evitar saturar al receptor).
Por otro lado, UDP es un protocolo mucho más simple y ligero, que se destaca por su velocidad pero que proporciona unos servicios mínimos. No está orientado a la conexión, no ofrece un servicio transferencia de datos fiable, es decir que UDP no ofrece ninguna garantía de que los datos lleguen al receptor. Tampoco dispone de control de congestión ni de control de flujo.
Lo ideal, es utilizar TCP cuando cuando la integridad de los datos es crítica y no se puede permitir la pérdida de un solo bit, aunque esto implique sacrificar velocidad. Por ejemplo: navegación web, transferencia de archivos, envío de correos electrónicos, etc.
Mientras que, conviene elegir UDP por sobre TCP para aplicaciones en tiempo real donde la velocidad es la prioridad absoluta y perder algunos paquetes no arruina la experiencia del usuario. Por ejemplo: streaming, videojuegos online, DNS, etc.

5. Justifique si el protocolo desarrollado cuenta con mecanismos de control de congestión, en caso de tenerlos, descríbalos.

El protocolo desarrollado **no cuenta con un control de congestión**, en el sentido en que lo tiene TCP, que ajusta dinámicamente su tasa de envío según el estado de la red. Lo que sí tiene son mecanismos de recuperación de errores y de limitación de la tasa de envío:

- **Stop & Wait** tiene un solo paquete en vuelo, por lo que nunca puede generar ráfagas. Esto limita la carga sobre la red, pero no es un mecanismo adaptativo. Si hay pérdidas, retransmite con el mismo timeout fijo.
- **SACK** usa una ventana deslizante de tamaño fijo (64 paquetes). Esto acota la cantidad de datos en vuelo, pero el tamaño no se ajusta cuando hay pérdidas: no hay reducción multiplicativa ni crecimiento gradual (como en AIMD), y el timeout de retransmisión tampoco crece con los reintentos.
- Ante pérdidas persistentes, ambos protocolos abortan la transferencia después de un número máximo de reintentos o timeouts consecutivos, en vez de reducir la velocidad.

6. ¿Cuál de los dos protocolos desarrollados envía archivos en la menor cantidad de tiempo? ¿Es siempre el mismo?

_Completar con las mediciones propias._ Se puede medir el tiempo de cada transferencia con:

```bash
time python3 upload.py -H 10.0.0.2 -p 54321 -s ./client_files -n test5mb.bin
time python3 upload.py -H 10.0.0.2 -p 54321 -s ./client_files -n test5mb.bin -r sack
```

Conviene repetir la prueba con distintos tamaños de archivo y distintos porcentajes de pérdida en la topología de Mininet, y volcar los resultados en una tabla:

| Tamaño | Pérdida | Stop & Wait | SACK |
|--------|---------|-------------|------|
|        |         |             |      |
