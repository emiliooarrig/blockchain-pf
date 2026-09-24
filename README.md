# blockchain-pf · LabChain

Blockchain de **sellado de tiempo para cuadernos de laboratorio**, pensado para demostrar prioridad científica. Cada entrada del cuaderno se resume con **SHA-256**, recibe un sello de tiempo UTC y se guarda en un bloque que se mina con **prueba de trabajo** en una carrera entre dos mineros: **Alice** y **Bob**.

Hecho con **Flask** siguiendo el patrón **MVC**. Toda la lógica (hashes, minado, validación) corre en Python con `hashlib` y `hmac`; el navegador solo muestra el estado que calcula el servidor.

## Funcionalidades

- **Registro de entradas:** investigador, título y contenido. Se calcula el SHA-256 del contenido y se guarda la fecha y hora de recepción.
- **Conexión TCP/IP entre dos PCs:** cada PC es un minero (Alice o Bob). Una se conecta a la IP de la otra dentro de la red local; la página muestra el esquema de conexión, la latencia y un registro de eventos.
- **Minado distribuido Alice vs Bob:** solo se habilita con la conexión activa. Cada PC mina con su minero; la primera que encuentra un hash con N ceros iniciales se lo envía a la otra, que se detiene, y ambas anuncian quién ganó.
- **Cadena visual:** bloques enlazados con su sello de tiempo, minero, dificultad, nonce, hash previo, raíz de Merkle y hash SHA-256.
- **Validación:** cada bloque se revisa (contenido, raíz de Merkle, hash, dificultad, enlace y orden de fechas) y se marca como válido o inválido.
- **Simular alteración:** modifica el contenido de un bloque para ver cómo se invalida la cadena a partir de ese punto.
- **Verificar prioridad:** pega un documento y el sistema indica si su SHA-256 está sellado, en qué bloque y con qué fecha.

## Requisitos

- Python **3.10 o superior**
- `pip`

## Instalación

```bash
git clone https://github.com/emiliooarrig/blockchain-pf.git
cd blockchain-pf

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Ejecución

```bash
python app.py
```

Abre **http://127.0.0.1:5000** en el navegador. Además de la página, la app abre un servidor **TCP en el puerto 5050** para conectarse con la otra PC.

Opciones:

| Opción | Por defecto | Descripción |
|---|---|---|
| `--port` | `5000` | Puerto de la página web |
| `--peer-port` | `5050` | Puerto TCP para la otra PC |
| `--miner` | — | Identidad inicial: `Alice` o `Bob` |
| `--data` | `data/chain.json` | Archivo donde se guarda la cadena |
| `--host` | `127.0.0.1` | Interfaz de la página web |

Opcionalmente define una clave fija para las sesiones de Flask (si no, se genera una aleatoria en cada arranque):

```bash
export SECRET_KEY="una-clave-larga-y-secreta"   # Windows: set SECRET_KEY=...
```

## Minado con dos PCs

1. Conecta **ambas PCs a la misma red** (mismo Wi-Fi o switch).
2. En cada PC instala el proyecto y ejecuta `python app.py`.
3. **Firewall:** permite conexiones entrantes al puerto **5050**. En macOS acepta el aviso "¿Permitir conexiones entrantes a Python?"; en Windows, "Permitir acceso" en el aviso de Windows Defender.
4. En la sección **2 · Conexión TCP/IP** de cada PC:
   - **a.** Elige la identidad: una PC es **Alice** y la otra **Bob** (si la que recibe la conexión no eligió, se le asigna la contraria).
   - **b.** Toma nota de la **IP** y el **puerto** que muestra la PC receptora.
   - **c.** En la **otra** PC escribe esa IP y ese puerto y pulsa **Conectar**. Solo una de las dos necesita conectarse.
5. Al conectarse, ambas PCs muestran **Conectado**, el diagrama se enlaza y se sincronizan la cadena y las entradas pendientes.
6. Registra una entrada en cualquiera de las dos PCs (aparece en ambas) y pulsa **Iniciar minado** en cualquiera. Las dos empiezan a minar a la vez; cada pantalla muestra a Alice y a Bob en vivo, y ambas anuncian quién encontró el bloque primero.

Para probarlo en **una sola computadora**, abre dos terminales con puertos y archivos distintos y conecta una con la otra usando `127.0.0.1` y el puerto `5051`:

```bash
python app.py --miner Alice
python app.py --miner Bob --port 5001 --peer-port 5051 --data data/bob.json
```

## Uso

1. **Registrar entrada:** llena investigador, título y contenido y pulsa *Registrar proyecto*. La entrada aparece en *Entradas pendientes de sellar* (también en la otra PC si están conectadas).
2. **Conectar:** sigue los pasos de [Minado con dos PCs](#minado-con-dos-pcs). Mientras no haya conexión, el minado está bloqueado.
3. **Minar:** elige la dificultad (3 a 6 ceros) y pulsa *Iniciar minado*. Verás en vivo el nonce, los intentos y los hashes por segundo de Alice y de Bob (cada tarjeta indica si es esta PC o la remota). Cuando uno encuentra el hash, ambos se detienen y aparece el ganador; la página se recarga con el nuevo bloque.
4. **Revisar la cadena:** en *Cadena de bloques* cada bloque muestra sus datos y las entradas que selló (despliega *entrada(s) sellada(s)*).
5. **Verificar prioridad:** en la sección 5 pega el contenido **exacto** de un documento. Si está sellado, se muestra el bloque y la fecha; un solo carácter distinto produce otro hash.
6. **Demostrar integridad:** pulsa *Simular alteración* en un bloque; ese bloque y los siguientes se marcan como inválidos.
7. **Empezar de cero:** desconéctate y pulsa *Reiniciar cadena*; se crea un nuevo bloque génesis y se borran las entradas pendientes.

Tiempos aproximados de minado con dos PCs: dificultad 5 ≈ 0.5–1 s, dificultad 6 ≈ 5–15 s (varía según los equipos y la suerte). Con dificultad 3 el hash aparece en milisegundos y es común que ambas PCs lo encuentren casi a la vez (se resuelve por hash menor).

## Estructura

```
blockchain-pf/
├── app.py                              # Punto de entrada: crea la app Flask
├── requirements.txt
├── models/                             # Modelo
│   ├── crypto.py                       # SHA-256, raíz de Merkle, sellos de tiempo
│   ├── block.py                        # Bloque y entradas del cuaderno
│   ├── blockchain.py                   # Cadena, validación, verificación y persistencia
│   ├── mining.py                       # Carrera de minado distribuida Alice vs Bob
│   └── network.py                      # Conexión TCP/IP con la otra PC (protocolo y sincronización)
├── controllers/
│   ├── blockchain_controller.py        # Rutas de entradas, minado, cadena y verificación
│   └── network_controller.py           # Rutas de identidad, conexión y desconexión
├── views/                              # Vista
│   ├── templates/index.html
│   └── static/
│       ├── styles.css                  # Paleta de azules y estilos
│       └── mining.js                   # Solo consulta y muestra el estado (minado y conexión)
└── data/chain.json                     # Cadena guardada (se crea al arrancar, ignorada por git)
```

## Cómo funciona

- **Entrada:** `content_hash = SHA-256(contenido)`. El hash de la entrada combina autor, título, `content_hash` y fecha de recepción.
- **Bloque:** la cabecera contiene índice, sello de tiempo, hash previo, raíz de Merkle de las entradas, dificultad y minero. `hash = SHA-256(cabecera + nonce)`.
- **Prueba de trabajo:** se busca un `nonce` tal que el hash empiece con N ceros. Alice y Bob minan la misma cabecera (mismo sello de tiempo y raíz de Merkle, con su nombre como minero), cada uno en su PC.
- **Conexión TCP/IP:** cada PC abre un socket TCP (puerto 5050). Los mensajes son JSON, uno por línea, sobre una conexión persistente:

  | Mensaje | Uso |
  |---|---|
  | `HELLO` / `HELLO_ACK` / `HELLO_REJECT` | Saludo con identidad, cadena y entradas pendientes |
  | `PING` / `PONG` | Latencia y detección de caídas (se desconecta tras 12 s sin respuesta) |
  | `ENTRY` / `PENDING` / `CHAIN_SYNC` | Sincronización de entradas y de la cadena |
  | `MINE_START` / `MINE_ACK` | Inicio coordinado del minado con la plantilla del bloque |
  | `PROGRESS` | Progreso del minero (cada 0.25 s) para verlo en la otra PC |
  | `BLOCK_FOUND` | Bloque encontrado: la otra PC lo valida, se detiene y lo agrega |
  | `MINE_STOP` / `BYE` | Detener el minado / desconexión voluntaria |

- **Sincronización:** al conectarse, ambas PCs adoptan la misma cadena: la válida más larga y, si empatan, la de hash de punta menor. Las entradas de una cadena descartada vuelven a pendientes.
- **Empates:** si ambas encuentran un bloque de la misma altura casi a la vez, las dos conservan el de **hash menor**, así que siempre coinciden en el ganador.
- **Datos de la red:** todo bloque o entrada recibido se valida (estructura, SHA-256 del contenido, raíz de Merkle, hash, dificultad y enlace) antes de aceptarse.
- **Validación:** se recalculan los hashes de contenido, la raíz de Merkle y el hash de cada bloque, y se comprueba la dificultad, el enlace con el bloque anterior y el orden de los sellos de tiempo.

## Rutas

| Método | Ruta                      | Descripción                          |
|--------|---------------------------|--------------------------------------|
| GET    | `/`                       | Página principal                     |
| POST   | `/entries`                | Registrar una entrada                |
| POST   | `/mine`                   | Iniciar la carrera de minado         |
| POST   | `/mine/stop`              | Detener el minado                    |
| GET    | `/api/status`             | Estado del minado y de la conexión en JSON |
| POST   | `/network/identity`       | Elegir identidad (Alice o Bob)       |
| POST   | `/network/connect`        | Conectar con la otra PC (IP y puerto) |
| POST   | `/network/disconnect`     | Cerrar la conexión                   |
| POST   | `/verify`                 | Verificar un documento               |
| POST   | `/blocks/<index>/tamper`  | Simular alteración de un bloque      |
| POST   | `/chain/reset`            | Reiniciar la cadena                  |

## Notas

- La cadena se guarda en `data/chain.json`, así que se conserva entre reinicios del servidor.
- `app.py` usa el servidor de desarrollo de Flask sin recargador automático (los hilos de minado y de red viven en un solo proceso). Es un proyecto académico y no está pensado para producción.
- La página web solo escucha en `127.0.0.1`; lo único expuesto a la red es el puerto TCP 5050, y la conexión **no está cifrada ni autenticada**. Úsalo solo en una red local de confianza.
