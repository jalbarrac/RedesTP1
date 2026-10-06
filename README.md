
# TP1 - Transferencia Confiable de Archivos sobre UDP

Implementación de un protocolo de capa de aplicación para transferencia confiable de datos (RDT) sobre UDP con **Stop & Wait** y **Selective ACK (SACK)** concurrente.

---

## Guía Rápida de Simulación en Mininet

### 1. Iniciar Mininet

Ejecutá uno de los siguientes comandos según el escenario a probar:

* **Escenario RTT = 40 ms (Pérdida ≈ 10% total):**
  ```bash
  sudo mn --topo single,5 --link tc,loss=5,delay=10ms
  ```
* **Escenario RTT = 300 ms (Pérdida ≈ 10% total):**
  ```bash
  sudo mn --topo single,5 --link tc,loss=5,delay=75ms
  ```

---

### 2. Abrir Terminales de los Hosts (`xterm`)

En la consola de `mininet>`, abrí las terminales interactivas para el servidor (`h5`) y el cliente (`h1`):

```text
mininet> xterm h1 h5
```

Esto abrirá dos ventanas independientes: una correspondiente a **h1** y otra a **h5**.

---

### 3. Ejecución del Servidor (Terminal `h5`)

En la ventana emergente de **h5**:

```bash
python3 src/start-server/server.py -s ./storage -v
```

---

### 4. Pruebas desde el Cliente (Terminal `h1`)

La IP de `h5` en Mininet es `10.0.0.5`.

#### A. Crear Archivo de Prueba (5 MB)
```bash
dd if=/dev/urandom of=prueba.bin bs=1M count=5
```

#### B. Probar Upload (Subida)
* **SACK:**
  ```bash
  python3 src/upload/upload.py -H 10.0.0.5 -p 54321 -s ./ -n prueba.bin -r sack -v
  ```
* **Stop & Wait:**
  ```bash
  python3 src/upload/upload.py -H 10.0.0.5 -p 54321 -s ./ -n prueba.bin -r saw -v
  ```

#### C. Probar Error (Archivo que excede tamaño)
```bash
truncate -s 1100M grande.bin
python3 src/upload/upload.py -H 10.0.0.5 -p 54321 -s ./ -n grande.bin -r sack -v
```

#### D. Probar Download (Descarga)
```bash
python3 src/download/download.py -H 10.0.0.5 -p 54321 -d ./descargas -n prueba.bin -r sack -v
```

#### E. Verificar Integridad de Datos
```bash
sha256sum prueba.bin storage/prueba.bin descargas/prueba.bin
```

---

### 5. Finalizar y Limpiar
Para cerrar la simulación, salí del prompt de Mininet (`quit` o `exit`) y ejecutá:
```bash
sudo mn -c
```
