"""Tests for the run-report CLI (D42): read-only functional summary."""

from pathlib import Path

from scripts.reporte_corrida import generar_reporte


def _sembrar() -> None:
    from shared.persistence import (
        actualizar_corrida,
        escribir_evento,
        escribir_fila,
        registrar_corrida,
    )

    registrar_corrida(
        {
            "id_corrida": "COR-0001",
            "fecha_inicio": "2026-08-25 10:00:00",
            "estado": "completada",
            "fecha_fin": "2026-08-25 10:05:00",
            "motivo_terminacion": "corrida_completada",
        },
    )
    registrar_corrida(
        {
            "id_corrida": "COR-0002",
            "fecha_inicio": "2026-08-25 10:00:01",
            "estado": "completada",
            "fecha_fin": "2026-08-25 10:01:00",
            "motivo_terminacion": "corrida_completada",
        },
    )
    actualizar_corrida(
        "COR-0001",
        {
            "fecha_fin": "2026-08-25 10:05:00",
            "motivo_terminacion": "corrida_completada",
        },
    )
    actualizar_corrida(
        "COR-0002",
        {
            "fecha_fin": "2026-08-25 10:01:00",
            "motivo_terminacion": "corrida_completada",
        },
    )
    escribir_evento(
        {
            "id_corrida": "COR-0001",
            "tipo": "suceso",
            "codigo": "corrida_programada",
            "evidencia": "programada ok",
            "marca_temporal": "2026-08-25 10:00:00",
        }
    )
    escribir_evento(
        {
            "id_corrida": "COR-0002",
            "tipo": "error",
            "codigo": "preparacion_fallida",
            "evidencia": "pagina_inalcanzable: timeout",
            "marca_temporal": "2026-08-25 10:00:30",
        }
    )
    for id_oferta, estado, empresa, dup in (
        ("OFE-0001", "preparada", "EMP-0001", None),
        ("OFE-0002", "duplicada", "EMP-0001", "OFE-0001"),
    ):
        datos = {
            "id": id_oferta,
            "titulo": f"Vacante {id_oferta}",
            "enlace": f"https://x/{id_oferta}",
            "descripcion_original": "texto",
            "estado": estado,
            "empresa_id": empresa,
            "ubicacion_id": "UBI-0001",
            "modalidad": "remoto",
            "empresa": "Acme Corp",
            "id_corrida": "COR-0002",
            "id_sesion": "SES-0001",
            "fuente_id": "linkedin",
            "indice_set": 0,
            "fecha_descubrimiento": "2026-08-25 10:00:02",
            "id_duplicidad": dup or "N/A",
        }
        if dup is not None:
            datos["observaciones"] = "dup"
        escribir_fila("ofertas_descubiertas", datos)
    escribir_fila("empresas", {"nombre": "Acme Corp", "nombre_normalizado": "acme corp"})
    escribir_fila(
        "ubicaciones",
        {
            "municipio": "Bogota",
            "departamento": "Cundinamarca",
            "pais": "Colombia",
        },
    )


def test_reporte_sin_corridas(temp_db_file: Path) -> None:
    lineas = generar_reporte()
    assert lineas == ["No hay corridas registradas en la base de datos."]


def test_reporte_completo_por_defecto_toma_programada(temp_db_file: Path) -> None:
    _sembrar()
    texto = "\n".join(generar_reporte())
    assert "== CORRIDA COR-0001 ==" in texto
    assert "COR-0002" in texto
    assert "'preparada': 1" in texto and "'duplicada': 1" in texto
    assert "[preparacion_fallida] pagina_inalcanzable" in texto
    assert "OFE-0002 -> OFE-0001" in texto
    assert "columna empresa 'N/R'=0" in texto
    assert "== REGLA NO VACIOS == cumple" in texto


def test_reporte_corrida_inexistente(temp_db_file: Path) -> None:
    _sembrar()
    assert generar_reporte("COR-9999") == ["No existe la corrida COR-9999."]
