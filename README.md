# Sellalo · Blockchain de sellado de prioridad científica

Red **blockchain con Proof of Work** para demostrar **quién tuvo primero un resultado científico**. Cada laboratorio
es un nodo: sella el **hash SHA-256** de un documento (el contenido nunca sale de su PC), sus co-autores lo firman
(**multifirma k-de-n**), la red lo mina y lo **replica** en todos los nodos, y cualquiera puede comprobar la prioridad
con un **certificado verificable sin conexión**.

Hecho en **Python + Flask**. El proyecto tiene dos modos:

| Modo | Para qué | Cómo se abre |
|---|---|---|
| **Nodo Sellalo** (proyecto final) | Red real de laboratorios por TCP: sellos, co-firmas, minado, cadena, verificación, certificados, ataques, rúbrica y auditoría | `python app.py --modo nodo …` (o los scripts de abajo) |
| **Simulador** (medio término) | 10–20 nodos en memoria compitiendo con PoW por rondas | `python app.py` o `flask run` |

> **¿Abriste `http://127.0.0.1:5000` y no ves la rúbrica?** Estás en el **modo simulador**. La red Sellalo, la rúbrica,
> el laboratorio de ataques y la auditoría están en el **modo nodo**: sigue el [inicio rápido](#inicio-rápido).

---

## Requisitos

- **Python 3.10 o superior** (probado con 3.14) y `pip`.
- Windows, macOS o Linux. Para usar varias PCs: misma red local y el puerto P2P abierto en el firewall.

## Instalación

```bash
git clone https://github.com/emiliooarrig/blockchain-pf.git
cd blockchain-pf

python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# macOS / Linux:         source .venv/bin/activate

pip install -r requirements.txt
```

> Todos los comandos de este README se ejecutan **desde la carpeta del proyecto y con el entorno virtual activado**.

---

## Inicio rápido

### Opción 1 · Demostración completa en un comando (recomendada)

Levanta 3 laboratorios (LAB-A, LAB-B, LAB-C) en tu PC, recorre todo el caso de uso (sello multifirma, co-firma,
minado, réplica, certificado, ataque rechazado, partición de red y reinicio de un nodo) y **deja los nodos abiertos**:

```bash
python scripts/demo_e2e.py --dejar-abiertos
```

Abre en el navegador:

| Laboratorio | URL |
|---|---|
| LAB-A | http://127.0.0.1:5101 |
| LAB-B | http://127.0.0.1:5102 |
| LAB-C | http://127.0.0.1:5103 |

Los nodos quedan desbloqueados y con datos. Para cerrarlos, pulsa **Ctrl+C** en la terminal.
Si quieres poder volver a desbloquearlos desde la interfaz, fija tú la contraseña con una variable de entorno:

```bash
# Windows (PowerShell)
$env:SELLALO_PW = "una-contraseña-larga"
python scripts/demo_e2e.py --dejar-abiertos --contrasena-env SELLALO_PW

# macOS / Linux
SELLALO_PW="una-contraseña-larga" python scripts/demo_e2e.py --dejar-abiertos --contrasena-env SELLALO_PW
```

Sin `--dejar-abiertos`, el script recorre el guion, imprime la evidencia de cada paso y cierra los nodos (sirve como
**plan B** de la presentación).

### Opción 2 · Red local vacía para usarla tú mismo

```bash
python scripts/lanzar_red_local.py --labs 3 --lanzar
```

- La primera vez pide una **contraseña** (mínimo 10 caracteres) y crea, en `data/demo/`, la identidad cifrada de cada
  laboratorio y el **génesis** compartido. Las siguientes veces reutiliza esos archivos.
- Arranca un proceso por laboratorio: LAB-A en http://127.0.0.1:5001, LAB-B en :5002, LAB-C en :5003
  (P2P en 6001–6003). **Ctrl+C** los cierra todos.
- En cada página: **Identidad → Desbloquear** con la contraseña. Al desbloquearse, el nodo se conecta solo con los
  otros dos.

Opciones útiles: `--labs 4`, `--carpeta data/otra-red`, `--puerto-base 5201 --puerto-p2p-base 6201`
(para tener dos redes a la vez) y `--contrasena-env VAR`.

### Opción 3 · Simulador del medio término

```bash
python app.py        # o: flask run
```

Abre http://127.0.0.1:5000. Simulación en memoria de 10 a 20 nodos con PoW (nonces disjuntos, desempate por hash
menor, recompensa con 6 confirmaciones). No tiene red real ni rúbrica.

---

## Recorrido por la interfaz del nodo

Cada nodo tiene cuatro vistas, en las pestañas del encabezado (**Nodo · Rúbrica · Ataques · Auditoría**) más el
**Simulador**:

| Vista | Qué hay |
|---|---|
| **Nodo** (`/`) | Barra de 5 grupos: **Identidad y red** (desbloqueo, protección de la clave, pares, consistencia, consenso) · **Sellos** (sellar un documento, co-firmas, prioridad y certificados) · **Minado y cadena** (con el panel **Dificultad de la red**) · **Verificación** (auditar tu copia y simular alteraciones) · **Cuentas** (saldos y bitácora) |
| **Rúbrica** (`/rubrica`) | Tablero en vivo de cada criterio de la rúbrica (R1–R8 y punto excepcional) con su evidencia, y el recorrido del caso de uso |
| **Ataques** (`/ataques`) | Laboratorio de ataques: fabrica una manipulación sobre una copia (sello alterado, firma falsa, raíz de Merkle falsa, multifirma incompleta…) y muestra cómo la rechazan este nodo o sus pares. Requiere arrancar con `--laboratorio-ataques` (los scripts ya lo hacen) |
| **Auditoría** (`/auditoria`) | Hallazgos de la auditoría del código con IA, su decisión, el commit que los corrige y la prueba |

**Flujo típico** (con la opción 2):

1. Desbloquea los tres nodos.
2. En LAB-A, **Sellos → Sellar documento**: elige un archivo, título, investigador, autores (LAB-A, LAB-B, LAB-C) y umbral 2.
3. En LAB-B, **Co-firmas → Firmar**. El sello pasa a pendientes en los tres nodos.
4. En cualquier nodo, **Minado → Iniciar minado**. El bloque se replica y los tres muestran la misma punta.
5. **Prioridad y certificado**: sube el documento para ver quién lo selló primero y descarga el certificado.
6. **Verificación → Simular alteración** y la vista **Ataques**: comprueba que los datos alterados se rechazan.
7. La vista **Rúbrica** se va marcando sola a medida que demuestras cada criterio.

### Cambiar la dificultad de la red

La dificultad (ceros hexadecimales iniciales del hash) la fija el génesis, pero se puede cambiar **en la red viva y
conservando la cadena**, siempre por acuerdo de la mayoría de los laboratorios:

1. En un nodo, **Minado y cadena → Dificultad de la red**: elige la nueva dificultad (1 a 6) y pulsa **Proponer ajuste**.
   El panel muestra el tiempo esperado por bloque (con la velocidad de hashes de tu PC si ya minaste).
2. En otro nodo aparece la propuesta en **Propuestas en firma**: pulsa **Firmar**. Con la mayoría (2 de 3) el ajuste pasa
   a pendientes en todos los nodos.
3. Cualquiera mina un bloque: el ajuste queda registrado en la cadena y **se aplica desde el bloque siguiente**. El
   historial de ajustes y el detalle del bloque lo muestran, y los certificados nuevos lo incluyen para que el verificador
   independiente lo compruebe.

Cada nivel multiplica el trabajo por 16: la dificultad 6 son ≈ 16,7 millones de hashes por bloque (16^6).

## Verificar un certificado sin conexión

El certificado descargado se comprueba con un script independiente (sólo biblioteca estándar y `cryptography`; no
usa el resto del proyecto):

```bash
python verificar_certificado.py certificado-xxxxxxxx.json --documento articulo.pdf --genesis <hash-del-génesis>
```

El hash del génesis aparece en el encabezado de cada nodo. Sin `--genesis` el resultado es **no concluyente**, porque
cualquiera podría fabricar una red propia. Códigos de salida: 0 válido · 1 no válido · 2 archivo ilegible · 3 no concluyente.

## Varias PCs en la misma red

Ejemplo con dos laboratorios, `LAB-A` (PC 1, IP 192.168.1.10) y `LAB-B` (PC 2, IP 192.168.1.11):

1. **En cada PC**, crea su identidad. La clave privada se guarda **cifrada** con tu contraseña y nunca sale de esa PC:
   ```bash
   python scripts/crear_identidad.py LAB-A --salida data/LAB-A/clave.json     # en la PC 1
   python scripts/crear_identidad.py LAB-B --salida data/LAB-B/clave.json     # en la PC 2
   ```
2. **En una sola PC**, crea el génesis. Copia antes ahí el `clave.json` del otro laboratorio: el script sólo lee su
   clave pública.
   ```bash
   python scripts/inicializar_red.py --lab LAB-A=data/LAB-A/clave.json --lab LAB-B=data/LAB-B/clave.json \
       --salida red/genesis.json --dificultad 4 --nombre "Red Sellalo"
   ```
   Después copia `red/genesis.json` a la otra PC, en la misma ruta.
3. **En cada PC**, arranca su nodo:
   ```bash
   # PC 1
   python app.py --modo nodo --nodo LAB-A --datos data/LAB-A --genesis red/genesis.json \
       --puerto 5001 --puerto-p2p 6001 --pares 192.168.1.11:6001 --laboratorio-ataques
   # PC 2
   python app.py --modo nodo --nodo LAB-B --datos data/LAB-B --genesis red/genesis.json \
       --puerto 5001 --puerto-p2p 6001 --pares 192.168.1.10:6001 --laboratorio-ataques
   ```
4. Abre http://127.0.0.1:5001 en cada PC y desbloquea el nodo. También puedes conectar pares a mano en **Identidad y red**.

**Firewall:** permite conexiones entrantes al puerto P2P (6001). En Windows acepta el aviso de Windows Defender; en
macOS, "Permitir conexiones entrantes a Python". La página web sólo escucha en `127.0.0.1`: lo único expuesto a la red
es el puerto P2P, y su saludo va autenticado con la clave de cada laboratorio.

### Opciones de `app.py`

| Opción | Por defecto | Descripción |
|---|---|---|
| `--modo simulador\|nodo` | `simulador` | Modo de la aplicación |
| `--host` | `127.0.0.1` | Interfaz de la página web |
| `--puerto` (`--port`) | `5000` | Puerto de la página web |
| `--nodo` | — | Id del laboratorio (p. ej. `LAB-A`) |
| `--datos` | — | Carpeta del nodo (cadena, pendientes, sellos en firma) |
| `--genesis` | — | Archivo `genesis.json` de la red |
| `--clave` | `<datos>/clave.json` | Almacén de claves cifrado |
| `--puerto-p2p` | `6000` | Puerto TCP de la red entre nodos |
| `--pares` | — | Pares iniciales `ip:puerto,ip:puerto` |
| `--laboratorio-ataques` | desactivado | Habilita la vista y la ruta de ataques de demostración |

---

## Pruebas

```bash
python -m pytest -q
```

Unas 840 pruebas (≈ 2 min). Incluyen una red real de 3 procesos que recorre el caso de uso completo
(`tests/test_e2e_red.py`), pruebas adversariales de la red y de la API, y una prueba por cada hallazgo corregido de la
auditoría (`tests/test_auditoria_g*.py`).

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| En `:5000` no aparecen la rúbrica ni las pestañas nuevas | Es el **modo simulador**. Usa la opción 1 o 2. Si el servidor estaba abierto antes de actualizar el código, reinícialo: Flask no recarga plantillas en caliente. |
| `Address already in use` / el puerto está ocupado | Ya hay otra red o servidor abierto. Ciérralo con Ctrl+C o usa otros puertos (`--puerto-base`, `--http-base`). |
| "Contraseña incorrecta" al desbloquear | La identidad se creó con otra contraseña. Para la demo local basta borrar `data/demo/` y volver a lanzar (se crea una red nueva). |
| Los nodos no se conectan entre PCs | Revisa el firewall del puerto P2P, que ambos usen **el mismo** `genesis.json` y que las IP de `--pares` sean las correctas. |
| `/ataques` dice que el laboratorio está desactivado | Arranca el nodo con `--laboratorio-ataques`. |

## Estructura

```
blockchain-pf/
├── app.py                      # Flask: modo simulador o modo nodo
├── verificar_certificado.py    # verificador independiente de certificados
├── controllers/                # rutas: simulador (api.py) y nodo Sellalo (sellalo.py)
├── models/                     # núcleo, se prueba sin Flask
│   ├── cripto.py, keystore.py  # SHA-256, Ed25519, almacén de claves (scrypt + AES-256-GCM)
│   ├── bloque.py, validacion.py, merkle.py, pow.py
│   ├── multifirma.py           # sellos k-de-n
│   ├── nodo_completo.py        # nodo real: cadena, persistencia, minado, reorganización
│   ├── red_p2p.py              # red TCP entre nodos (saludo autenticado, difusión, sincronización)
│   ├── coordinador_sellos.py   # co-firmas entre laboratorios
│   ├── certificado.py, verificacion_detallada.py, rubrica.py, ataques_sellalo.py
│   └── red.py, simulador.py, ataques.py   # simulador PoW en memoria
├── views/                      # plantillas y JS/CSS de las vistas
├── scripts/                    # demo_e2e, lanzar_red_local, crear_identidad, inicializar_red, estado_auditoria
├── tests/                      # pytest
└── docs/                       # plan, contratos, evidencia por rubro, auditoría con IA
```

## Documentación

- [docs/EVIDENCIA_RUBRICA.md](docs/EVIDENCIA_RUBRICA.md): cada criterio de la rúbrica → código, pruebas y paso de la demo.
- [docs/RUBRICA_EN_INTERFAZ.md](docs/RUBRICA_EN_INTERFAZ.md): cómo se visualiza cada criterio en la interfaz.
- [docs/diseno/CONTRATOS.md](docs/diseno/CONTRATOS.md): formatos de bloque, sello, almacén de claves, protocolo P2P y API.
- [docs/auditoria/](docs/auditoria/): auditoría del código con IA (instrucciones, respuestas, hallazgos, triaje y estado).
- [docs/PLAN_PROYECTO_FINAL.md](docs/PLAN_PROYECTO_FINAL.md): plan del proyecto final.
- [docs/REPORTE.md](docs/REPORTE.md): reporte del medio término (simulador).

## Notas

- El único consenso es **Proof of Work**. Proof of Stake se eliminó el 2026-11-27.
- `data/` está en `.gitignore`: ahí viven las identidades cifradas y las cadenas de cada nodo. Nunca se versionan.
- Proyecto académico: usa el servidor de desarrollo de Flask y está pensado para una red local de confianza.
