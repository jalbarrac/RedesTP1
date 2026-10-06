# TP1 - Transferencia Confiable de Archivos sobre UDP

Implementación de un protocolo de capa de aplicación para transferencia confiable de datos (RDT) sobre UDP, soportando los mecanismos **Stop & Wait** y **Selective ACK (SACK)** con capacidad de atención concurrente.

---

## Guía Rápida de Ejecución en Mininet (3 Terminales)

Para simular las condiciones de red exigidas (10% de pérdida por sentido y 40 ms de RTT), se utilizan 3 terminales independientes.

### Terminal 1: Entorno de Red (Mininet)
 
Inicia la topología con 5 hosts conectados a un switch. Elegir **uno** de los dos entornos:
 
**Entorno 1 (RTT = 300 ms, pérdida ≈ 10%):**
```bash
sudo mn --topo single,5 --link tc,loss=5,delay=75ms
```
 
**Entorno 2 (RTT = 40 ms, pérdida ≈ 10%):**
```bash
sudo mn --topo single,5 --link tc,loss=5,delay=10ms
```

```

Una vez que aparezca el prompt `mininet>`, consultá los PIDs (identificadores de proceso) de los hosts virtuales:

```text
mininet> dump
```
*Tomá nota de los números que figuran en `pid=` para `h1` (cliente) y `h5` (servidor).*

---

### Terminal 2: Servidor (Host `h5`)
Abrí una terminal nueva, pasá a usuario root y entrá al espacio de red de `h5`:
trabajar en la raiz del tp 

```bash
sudo su
mnexec -a <PID_H5> bash
cd "/RedesTP1"
python3 src/start-server/server.py -s ./storage -v
```
*El servidor quedará a la escucha en el puerto `54321`.*

---

### Terminal 3: Cliente (Host `h1`)
Abrí otra terminal nueva, pasá a usuario root y entrá al espacio de red de `h1`:

```bash
sudo su
mnexec -a <PID_H1> bash
cd "/ruta/al/proyecto"
```

#### 1. Probar Upload (Subida)
Genera un archivo de prueba y lo envía al servidor (`10.0.0.5`):
```bash
dd if=/dev/urandom of=prueba.bin bs=1 count=5000000
python3 src/upload/upload.py -H 10.0.0.5 -p 54321 -s ./ -n prueba.bin -r sack -v
```

#### 2. Probar Download (Descarga)
Descarga el archivo desde el almacenamiento del servidor a una carpeta local:
```bash
python3 src/download/download.py -H 10.0.0.5 -p 54321 -d ./descargas -n prueba.bin -r sack -v
```

#### 3. Verificar Integridad (Hashes)
Comprueba que el archivo original, el guardado en el servidor y el descargado sean idénticos:
```bash
sha256sum prueba.bin storage/prueba.bin descargas/prueba.bin
```

---

## Verificación de Red y Diagnóstico para la Demo

Comandos útiles para demostrar el comportamiento del canal y del protocolo durante la presentación:

* **Inspeccionar pérdida y retransmisiones en la interfaz:**
  En la terminal del cliente o del servidor, ejecuta:
  ```bash
  ip -s link show h1-eth0
  ```
  *(Permite contrastar los paquetes transmitidos `TX packets` antes y después de transferir para comprobar el volumen de retransmisiones debido al 10% de drop).*

* **Verificar latencia y pérdida en el enlace:**
  Desde la consola de Mininet:
  ```text
  mininet> h1 ping -c 10 h5
  ```

* **Inspeccionar las colas y reglas de `tc` aplicadas por Mininet:**
  En cualquier terminal:
  ```bash
  tc qdisc show dev s1-eth1
  ```

* **Limpiar el entorno al terminar:**
  Al salir de Mininet, cerrá las terminales y limpiá los procesos residuales:
  ```bash
  sudo mn -c
  ```

  ultima versionn
