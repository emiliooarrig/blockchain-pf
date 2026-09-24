# blockchain-pf · LabChain

Blockchain de **sellado de tiempo para cuadernos de laboratorio**, pensado para demostrar prioridad científica. Cada entrada del cuaderno se resume con **SHA-256**, recibe un sello de tiempo UTC y se guarda en un bloque que se mina con **prueba de trabajo** en una carrera entre dos mineros: **Alice** y **Bob**.

Hecho con **Flask** siguiendo el patrón **MVC**. Toda la lógica (hashes, minado, validación) corre en Python con `hashlib` y `hmac`; el navegador solo muestra el estado que calcula el servidor.

## Funcionalidades

- **Registro de entradas:** investigador, título y contenido. Se calcula el SHA-256 del contenido y se guarda la fecha y hora de recepción.
- **Minado Alice vs Bob:** cada uno mina en su propio hilo; el primero que encuentra un hash con N ceros iniciales detiene a ambos y la página anuncia quién ganó.
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

Abre **http://127.0.0.1:5000** en el navegador.

Opcionalmente define una clave fija para las sesiones de Flask (si no, se genera una aleatoria en cada arranque):

```bash
export SECRET_KEY="una-clave-larga-y-secreta"   # Windows: set SECRET_KEY=...
```

## Uso

1. **Registrar entrada:** llena investigador, título y contenido y pulsa *Registrar y calcular SHA-256*. La entrada aparece en *Entradas pendientes de sellar*.
2. **Minar:** elige la dificultad (3 a 6 ceros) y pulsa *Iniciar minado*. Verás en vivo el nonce, los intentos y los hashes por segundo de Alice y Bob. Cuando uno encuentra el hash, ambos se detienen y aparece el ganador; la página se recarga con el nuevo bloque.
3. **Revisar la cadena:** en *Cadena de bloques* cada bloque muestra sus datos y las entradas que selló (despliega *entrada(s) sellada(s)*).
4. **Verificar prioridad:** en la sección 4 pega el contenido **exacto** de un documento. Si está sellado, se muestra el bloque y la fecha; un solo carácter distinto produce otro hash.
5. **Demostrar integridad:** pulsa *Simular alteración* en un bloque; ese bloque y los siguientes se marcan como inválidos.
6. **Empezar de cero:** *Reiniciar cadena* crea un nuevo bloque génesis y borra las entradas pendientes.

Tiempos aproximados de minado: dificultad 5 ≈ 1–2 s, dificultad 6 ≈ 20 s (varía según el equipo y la suerte).

## Estructura

```
blockchain-pf/
├── app.py                              # Punto de entrada: crea la app Flask
├── requirements.txt
├── models/                             # Modelo
│   ├── crypto.py                       # SHA-256, raíz de Merkle, sellos de tiempo
│   ├── block.py                        # Bloque y entradas del cuaderno
│   ├── blockchain.py                   # Cadena, validación, verificación y persistencia
│   └── mining.py                       # Carrera de minado Alice vs Bob
├── controllers/
│   └── blockchain_controller.py        # Controlador: rutas HTTP
├── views/                              # Vista
│   ├── templates/index.html
│   └── static/
│       ├── styles.css                  # Paleta de azules y estilos
│       └── mining.js                   # Solo consulta el estado del minado
└── data/chain.json                     # Cadena guardada (se crea al arrancar, ignorada por git)
```

## Cómo funciona

- **Entrada:** `content_hash = SHA-256(contenido)`. El hash de la entrada combina autor, título, `content_hash` y fecha de recepción.
- **Bloque:** la cabecera contiene índice, sello de tiempo, hash previo, raíz de Merkle de las entradas, dificultad y minero. `hash = SHA-256(cabecera + nonce)`.
- **Prueba de trabajo:** se busca un `nonce` tal que el hash empiece con N ceros. Alice y Bob minan la misma cabecera (con su nombre como minero) desde hilos distintos; un `threading.Event` detiene a los dos en cuanto uno gana, y un candado garantiza un solo ganador.
- **Validación:** se recalculan los hashes de contenido, la raíz de Merkle y el hash de cada bloque, y se comprueba la dificultad, el enlace con el bloque anterior y el orden de los sellos de tiempo.

## Rutas

| Método | Ruta                      | Descripción                          |
|--------|---------------------------|--------------------------------------|
| GET    | `/`                       | Página principal                     |
| POST   | `/entries`                | Registrar una entrada                |
| POST   | `/mine`                   | Iniciar la carrera de minado         |
| POST   | `/mine/stop`              | Detener el minado                    |
| GET    | `/api/mining/status`      | Estado del minado en JSON            |
| POST   | `/verify`                 | Verificar un documento               |
| POST   | `/blocks/<index>/tamper`  | Simular alteración de un bloque      |
| POST   | `/chain/reset`            | Reiniciar la cadena                  |

## Notas

- La cadena se guarda en `data/chain.json`, así que se conserva entre reinicios del servidor.
- `app.py` usa el servidor de desarrollo de Flask sin recargador automático (los hilos de minado viven en un solo proceso). Es un proyecto académico y no está pensado para producción.
