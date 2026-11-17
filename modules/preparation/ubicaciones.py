"""Motor determinista de enlace de ubicaciones del Módulo 2 (decisión D77).

Resuelve texto libre contra el catálogo pre-cargado sin IA ni red.
Reglas RN-06, RN-07 y RN-08 de la ficha técnica del Módulo 2.
"""

from collections import defaultdict
from typing import Any, Iterable, Mapping, MutableMapping

from loguru import logger

from shared.utilidades import normalizar_texto

PENDIENTE = "N/A"
REMOTOS = frozenset({"remoto", "trabajo remoto", "remote"})
EQUIVALENCIAS = {"distrito capital": "bogota"}


class CatalogoUbicaciones:
    """Catálogo determinista de ubicaciones para el Módulo 2."""

    def __init__(self, filas: Iterable[Mapping[str, Any]]) -> None:
        self.esta_vacio = True
        self.fila_no_aplica_id: str | None = None
        self.fila_pais_id: str | None = None
        self._municipios: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._departamentos: dict[str, str | None] = {}
        self._nombres_departamento: set[str] = set()

        filas_lista = list(filas)
        conte_pais = 0
        fila_pais_id: str | None = None
        dept_sentinelas: dict[str, int] = defaultdict(int)
        dept_sentinel_ids: dict[str, str] = {}
        dept_count = 0
        mun_count = 0
        fila_no_aplica_id: str | None = None

        for fila in filas_lista:
            fila_id = fila.get("id", "")
            if not fila_id:
                continue
            mun_raw = fila.get("municipio", "")
            dept_raw = fila.get("departamento", "")

            if mun_raw == "N/A" and dept_raw == "N/A":
                pais_raw = fila.get("pais", "")
                if pais_raw == "N/A":
                    fila_no_aplica_id = fila_id
                    continue
                conte_pais += 1
                if conte_pais == 1:
                    fila_pais_id = fila_id
                continue
            if mun_raw == "N/A" and dept_raw != "N/A":
                dept_key = normalizar_texto(dept_raw)
                dept_sentinelas[dept_key] += 1
                if dept_key not in dept_sentinel_ids:
                    dept_sentinel_ids[dept_key] = fila_id
                dept_count += 1
                continue

            m_norm = normalizar_texto(mun_raw)
            d_norm = normalizar_texto(dept_raw)
            self._municipios[m_norm].append((fila_id, d_norm))
            self._nombres_departamento.add(d_norm)
            mun_count += 1

        for dept_key, count in dept_sentinelas.items():
            if count > 1:
                self._departamentos[dept_key] = None
            else:
                self._departamentos[dept_key] = dept_sentinel_ids.get(dept_key)
            self._nombres_departamento.add(dept_key)

        self.fila_pais_id = fila_pais_id if conte_pais == 1 else None
        self.fila_no_aplica_id = fila_no_aplica_id

        if mun_count == 0 and dept_count == 0 and conte_pais == 0:
            self.esta_vacio = True
            logger.warning("catalogo_ubicaciones_vacio | todas las ofertas quedaran pendientes")
        else:
            self.esta_vacio = False

    def resolver(
        self, texto_crudo: str, memoria: MutableMapping[str, str] | None = None
    ) -> str:
        """Resuelve texto de ubicación a id de catálogo."""
        # 1. Memoria
        if memoria is not None:
            segmentos = [s for s in texto_crudo.split(",") if normalizar_texto(s.strip())]
            clave = "|".join(normalizar_texto(s) for s in segmentos) if segmentos else ""
            if clave in memoria:
                return memoria[clave]
        else:
            clave = None

        # 2. Vacío, centinela o remoto → fila "no aplica" o PENDIENTE
        texto_stripped = texto_crudo.strip()
        if not texto_stripped or texto_stripped in ("N/A", "N/R"):
            return self._guardar(memoria, clave, self._no_aplica_o_pendiente())

        if normalizar_texto(texto_stripped) in REMOTOS:
            return self._guardar(memoria, clave, self._no_aplica_o_pendiente())

        if self.esta_vacio:
            return PENDIENTE

        # 4-5. Segmentos con equivalencias
        segmentos = []
        for s in texto_crudo.split(","):
            s = s.strip()
            if not s:
                continue
            n = normalizar_texto(s)
            if not n:
                continue
            n = self.limpiar_municipio(n)
            segmentos.append(n)

        if not segmentos:
            return self._guardar(memoria, clave, self._no_aplica_o_pendiente())

        # 6. Clasificar
        paises, dept_cand, mun_cand, desconocidos = [], [], [], []
        for seg in segmentos:
            if seg == "colombia":
                paises.append(seg)
            elif seg in self._nombres_departamento:
                dept_cand.append(seg)
            elif seg in self._municipios:
                mun_cand.append(seg)
            else:
                desconocidos.append(seg)

        # 7. Desconocidos → PENDIENTE
        if desconocidos:
            return self._guardar(memoria, clave, PENDIENTE)

        # 8. Más de un municipio distinto → PENDIENTE
        if len(set(mun_cand)) > 1:
            return self._guardar(memoria, clave, PENDIENTE)

        # 9. Un municipio candidato
        if len(mun_cand) == 1:
            mun = mun_cand[0]
            filas_mun = self._municipios[mun]
            if len(filas_mun) == 1:
                fila_id, fila_dept = filas_mun[0]
                if not dept_cand or set(dept_cand) == {fila_dept}:
                    res = fila_id
                else:
                    res = PENDIENTE
            else:
                coinc = [(fid, fd) for fid, fd in filas_mun if fd in dept_cand]
                if len(coinc) == 1 and set(dept_cand) == {coinc[0][1]}:
                    res = coinc[0][0]
                else:
                    res = PENDIENTE
            return self._guardar(memoria, clave, res)

        # 10. Un departamento candidato
        if len(dept_cand) == 1:
            dept_id = self._departamentos.get(dept_cand[0])
            res = PENDIENTE if dept_id is None else dept_id
            return self._guardar(memoria, clave, res)

        # 11. Dos o más departamentos, homónimo como municipio
        if len(dept_cand) >= 2:
            homonimos = [d for d in dept_cand if d in self._municipios]
            if len(homonimos) == 1:
                otros = [d for d in dept_cand if d != homonimos[0]]
                coinc = [
                    (fid, fd) for fid, fd in self._municipios[homonimos[0]] if fd in otros
                ]
                res = coinc[0][0] if len(coinc) == 1 else PENDIENTE
            else:
                res = PENDIENTE
            return self._guardar(memoria, clave, res)

        # 12. Solo país
        if paises and not dept_cand and not mun_cand:
            res = self.fila_pais_id if self.fila_pais_id is not None else PENDIENTE
            return self._guardar(memoria, clave, res)

        return self._guardar(memoria, clave, PENDIENTE)

    def _no_aplica_o_pendiente(self) -> str:
        """Return the 'no aplica' row id, or the pending sentinel if absent."""
        return self.fila_no_aplica_id if self.fila_no_aplica_id is not None else PENDIENTE

    @staticmethod
    def limpiar_municipio(municipio_normalizado: str) -> str:
        """Clean municipality name: remove trailing D.C./dc suffix, apply equivalences."""
        n = municipio_normalizado
        if n.endswith(" d c"):
            n = n[:-4]
        elif n.endswith(" dc"):
            n = n[:-3]
        if n in EQUIVALENCIAS:
            n = EQUIVALENCIAS[n]
        return n

    def buscar_por_componentes(
        self, municipio: str, departamento: str, pais: str
    ) -> str | None:
        """Search by components for AI-driven linking without creating duplicates.

        Returns the catalogue id or ``None`` when the municipality is unknown
        or ambiguous.  The country parameter is ignored.
        """
        mun_norm = self.limpiar_municipio(normalizar_texto(municipio))
        dept_norm = normalizar_texto(departamento) if departamento not in ("", "N/A", "N/R") else ""

        if not mun_norm:
            return None

        filas = self._municipios.get(mun_norm)
        if filas is None:
            return None

        if len(filas) == 1:
            return filas[0][0]

        # Varios: necesita departamento para desambiguar
        if not dept_norm:
            return None
        coinc = [f for f in filas if f[1] == dept_norm]
        if len(coinc) == 1:
            return coinc[0][0]
        return None

    def municipio_conocido(self, municipio: str) -> bool:
        """True if at least one catalogue row has this municipality (after cleaning)."""
        mun_norm = self.limpiar_municipio(normalizar_texto(municipio))
        if not mun_norm:
            return False
        return mun_norm in self._municipios

    def departamento_en_texto(self, texto: str) -> str | None:
        """Find a department id within free-form text, ignoring equivalences.

        Splits by comma, normalizes each part, and matches against known
        department names.  Returns the department row id when exactly one
        unambiguous department is found; otherwise ``None``.
        """
        dept_cand: list[str] = []
        for s in texto.split(","):
            s = s.strip()
            if not s:
                continue
            n = normalizar_texto(s)
            if not n:
                continue
            # No equivalencias aquí: se busca departamento, no municipio
            if n in self._nombres_departamento and n not in self._municipios:
                dept_cand.append(n)
            elif n in self._nombres_departamento and n in self._municipios:
                # Homónimo: se prefiere como municipio, no como departamento
                continue

        if len(dept_cand) != 1:
            return None

        dept_id = self._departamentos.get(dept_cand[0])
        return dept_id

    @staticmethod
    def _guardar(
        memoria: MutableMapping[str, str] | None, clave: str | None, valor: str
    ) -> str:
        if memoria is not None and clave is not None:
            memoria[clave] = valor
        return valor
