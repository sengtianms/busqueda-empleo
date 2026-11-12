---
sessionId: session-261112-171742-yeco
---

# Descripción

### Objetivo
Eliminar todos los registros de todas las tablas en la base de datos `data/job_search.db`, dejando las tablas vacías pero intactas (estructura conservada).

### Alcance
- **Incluye**: Borrar todos los registros de las 10 tablas existentes en `job_search.db`.
- **Excluye**: Borrar tablas, borrar la base de datos, hacer backup, modificar cualquier otro archivo del proyecto.

### Tablas afectadas
Según la documentación del proyecto, las tablas son:
1. `bloqueo`
2. `corridas`
3. `eventos`
4. `ofertas_descubiertas`
5. `empresas`
6. `ubicaciones`
7. `sesiones`
8. `listas_busquedas`
9. `duplicados_descubiertas`
10. `auditoria` (si existe)

### Enfoque
Ejecutar `DELETE FROM` en cada tabla en el orden correcto (respectando dependencias) y luego `VACUUM` para liberar espacio. Sin backup.

# Delivery Steps

### ✓ Step 1: Limpiar todos los registros de la base de datos
Ejecutar comandos SQL directamente en `data/job_search.db` para vaciar todas las tablas.
- Desactivar claves foráneas temporalmente (`PRAGMA foreign_keys=OFF`) para evitar conflictos de orden.
- Ejecutar `DELETE FROM` en cada tabla: `duplicados_descubiertas`, `eventos`, `ofertas_descubiertas`, `empresas`, `ubicaciones`, `sesiones`, `listas_busquedas`, `corridas`, `bloqueo`, `auditoria`.
- Ejecutar `VACUUM` para compactar y liberar espacio.
- Verificar que todas las tablas queden con 0 registros.