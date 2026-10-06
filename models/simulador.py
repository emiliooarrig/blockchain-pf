"""Contenedor de las dos simulaciones (PoW y PoS), cada una con su propia red de nodos."""
import threading

from models.errores import ErrorEntrada
from models.red import PARAMETROS_INICIALES, Red

VERSIONES = ("pow", "pos")


class Simulador:
    def __init__(self, reproducible: bool = False):
        self._lock = threading.Lock()
        self.redes = {v: Red(v, **{**PARAMETROS_INICIALES[v], "reproducible": reproducible}) for v in VERSIONES}

    def red(self, version: str) -> Red:
        if version not in self.redes:
            raise ErrorEntrada(f"Versión desconocida «{str(version)[:20]}»; usa pow o pos.")
        return self.redes[version]

    def reiniciar(self, version: str, **parametros) -> Red:
        """Crea una red nueva. Si los parámetros son inválidos se conserva la actual."""
        anterior = self.red(version)
        nueva = Red(version, **parametros)
        with self._lock:
            with anterior.lock:
                anterior.motor.detener()
            self.redes[version] = nueva
        return nueva
