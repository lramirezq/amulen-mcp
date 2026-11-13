# amulen-mcp

Servidor [MCP](https://modelcontextprotocol.io) para **AMULEN**, la plataforma de gestión de
proyectos, tableros y tareas de 3HTP. Permite que asistentes como Claude consulten y
actualicen tu trabajo en AMULEN **con tus mismos permisos**.

- Autenticación con **token personal** (sin contraseña).
- Una llamada por herramienta. Los errores (403, 404, 422…) se devuelven con un mensaje claro.
- Comentarios y descripciones en **Markdown**, que AMULEN muestra con formato.
- **Adjuntos de evidencia**: archivos locales o textos generados por el agente.

## Instalación

### 1. Crea tu token

En AMULEN → **Mi Perfil** → *Tokens de API* → *Crear token*. Copia el valor (`amu_…`):
se muestra una sola vez. Puedes revocarlo desde el mismo lugar.

### 2. Configura tu cliente MCP

Necesitas [uv](https://docs.astral.sh/uv/getting-started/installation/).
`AMULEN_BASE_URL` es la dirección de AMULEN que usas en el navegador.

**Claude Code**

```bash
claude mcp add amulen -s user \
  -e AMULEN_BASE_URL=https://amulen.3htp.cloud \
  -e AMULEN_TOKEN=amu_xxx \
  -- uvx amulen-mcp@1.2.0
```

**Claude Desktop y otros clientes** (`mcpServers` en JSON)

```json
{
  "mcpServers": {
    "amulen": {
      "command": "uvx",
      "args": ["amulen-mcp@1.2.0"],
      "env": {
        "AMULEN_BASE_URL": "https://amulen.3htp.cloud",
        "AMULEN_TOKEN": "amu_xxx"
      }
    }
  }
}
```

Fijar la versión (`@1.2.0`) evita que una actualización te llegue sin aviso. Para actualizar,
cambia el número de versión.

### 3. Pruébalo

Abre una sesión nueva y pregunta: *"¿Tengo tareas en AMULEN?"*

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `amulen_whoami` | Usuario del token |
| `amulen_my_tasks` | Tus tareas en todos los proyectos (filtros: estado, proyecto, texto, vencidas) |
| `amulen_list_projects` / `amulen_get_project` | Proyectos accesibles / detalle con tableros |
| `amulen_project_dashboard` | Métricas: por estado, vencidas, horas, por usuario, bolsas de horas |
| `amulen_list_members` | Miembros con su id (para asignar tareas) |
| `amulen_create_project` / `amulen_update_project` | Crear / editar proyecto |
| `amulen_list_boards` / `amulen_get_board` / `amulen_create_board` | Tableros |
| `amulen_list_tasks` / `amulen_get_task` | Tareas de un tablero / detalle con checklist, comentarios y adjuntos |
| `amulen_create_task` / `amulen_update_task` | Crear / editar (mover de estado, registrar horas reales) |
| `amulen_add_comment` | Comentar una tarea (Markdown) |
| `amulen_add_checklist_items` / `amulen_update_checklist_item` / `amulen_delete_checklist_item` | Checklist |
| `amulen_upload_attachment` | Adjuntar evidencia: archivo local (`file_path`) o texto (`nombre` + `contenido_texto`). Máx. 25 MB |
| `amulen_list_attachments` / `amulen_download_attachment` | Ver y descargar adjuntos (a `~/Downloads/amulen/<tarea>/`, sin sobrescribir) |

No borra tareas, tableros ni proyectos, ni administra usuarios o permisos.

## Seguridad

- El servidor corre en tu máquina y solo habla con la `AMULEN_BASE_URL` que configures.
- El token actúa con tus permisos. AMULEN registra en la auditoría cada cambio hecho con él.
- Si un token se filtra, revócalo en *Mi Perfil*. Si encuentras una vulnerabilidad, repórtala en
  privado a los mantenedores (no en un issue público).

## Solución de problemas

| Mensaje | Causa |
|---|---|
| `unauthorized` | Token mal copiado, revocado o expirado |
| `redirect` | `AMULEN_BASE_URL` no apunta al sitio de tu organización |
| `forbidden` | No tienes permisos sobre ese proyecto o tablero |
| `blocked_by_waf` | El firewall de la red bloqueó la petición antes de llegar a AMULEN |

## Desarrollo

```bash
uv sync
uv run pytest
```

Las versiones se publican en PyPI al crear un tag `vX.Y.Z` (GitHub Actions, Trusted Publishing).

## Licencia

MIT. Ver [LICENSE](LICENSE).
