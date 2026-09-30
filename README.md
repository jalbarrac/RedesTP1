# Ejecutar

/RedesTP1/src/start-server$ python3 -p 54321 server.py

/RedesTP1/src/upload$ python3 upload.py -H 127.0.0.1 -p 54321 -n nombre_archivo

/RedesTP1/src/download$ python3 download.py -H 127.0.0.1 -p 54321 -n nombre_archivo

---

# Ejecución de Mininet

/RedesTP1/src$ python3 topology.py 

> Nota: si ven necesario, agregar sudo

Se abre la consola de mininet, mostrando la información de la topología

Si usan XTERM, se pueden tener dos terminales abiertas en simultaneo para ejecutar en uno el servidor y en el otro el cliente

Comando: xterm h1 h2

## Ejemplo:

h1 (cliente): /RedesTP1/src/upload$ python3 upload.py -H 10.0.0.2 -p 54321 -n nombre_archivo

h2 (server):  /RedesTP1/src/start-server$ python3 server.py -p 54321 

---

# Cuestionario

1. **Describa la arquitectura Cliente-Servidor.**

En la arquitectura Cliente-Servidor existe un host siempre activo, denominado servidor, que da servicio a las solicitudes de muchos otros hosts, que son los clientes. Generalmente, la comunicación siempre es iniciada por un cliente, quien le manda una petición al servidor y éste la responde. Otra característica importante del modelo es que los clientes normalmente no pueden comunicarse entre sí. En muchas ocasiones, un único host servidor es incapaz de responder a todas las peticiones de los clientes, por ello se suele utilizar un datacenter, que alberga un gran número de hosts, para crear un servidor virtual de gran capacidad.

2. ¿Cuál es la función de un protocolo de capa de aplicación?

Un protocolo de la capa de aplicación define como los procesos de una aplicación, que se ejecutan en distintos end systems, se pasan los mensajes entre si. En ese sentido, se definen los tipos de mensajes intercambiados (ya sean requests y responses), los campos de un mensaje y como se delimitan, su semántica e información y las reglas para determinar cuando y como un proceso envia mensajes y responde a los mismos.

3. Detalle el protocolo de aplicación desarrollado en este trabajo.



4. La capa de transporte del stack TCP/IP ofrece dos protocolos: TCP y UDP. ¿Qué servicios proveen dichos protocolos?
¿Cuáles son sus características? ¿Cuándo es apropiado utilizar cada uno?

El protocolo TCP es un protocolo proporciona un servicio de transferencia de datos fiable, lo cual significa que asegura que los datos enviados del origen lleguen a destino sin perderse en el camino, en el orden correcto y sin errores. Este protocolo es orientado a la conexión, es decir que TCP antes de enviar los datos establece una conexión entre los dos procesos (se realiza mediante Three-way Handshake), también ofrece un control de congestión (su objetivo es evitar que el emisor envíe datos a una velocidad que termine saturando la red) y un control de flujo (regular la cantidad de datos enviados para evitar saturar al receptor).
Por otro lado, UDP es un protocolo mucho más simple y ligero, que se destaca por su velocidad pero que proporciona unos servicios mínimos. No está orientado a la conexión, no ofrece un servicio transferencia de datos fiable, es decir que UDP no ofrece ninguna garantía de que los datos lleguen al receptor. Tampoco dispone de control de congestión ni de control de flujo.
Lo ideal, es utilizar TCP cuando cuando la integridad de los datos es crítica y no se puede permitir la pérdida de un solo bit, aunque esto implique sacrificar velocidad. Por ejemplo: navegación web, transferencia de archivos, envío de correos electrónicos, etc.
Mientras que, conviene elegir UDP por sobre TCP para aplicaciones en tiempo real donde la velocidad es la prioridad absoluta y perder algunos paquetes no arruina la experiencia del usuario. Por ejemplo: streaming, videojuegos online, DNS, etc.

5. Justifique si el protocolo desarrollado cuenta con mecanismos de control de congestión, en caso de tenerlos, descríbalos.



6. ¿Cuál de los dos protocolos desarrollados envía archivos en la menor cantidad de tiempo? ¿Es siempre el mismo?
