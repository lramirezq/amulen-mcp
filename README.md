# amulen-mcp

Servidor MCP para AMULEN sobre la **API v1** (`/api/v1`). Reemplaza al paquete
`amulen-mcp-server` 0.4.x, que iniciaba sesión con email y contraseña y fallaba
entero ante un solo 403.

- Autenticación con **token personal** (Bearer). Sin contraseña ni scraping de CSRF.
- Cada herramienta hace **una sola llamada**. `amulen_my_tasks` ya no recorre todos
  los proyectos.
- Los errores de la API (403, 404, 422…) se devuelven como errores de la herramienta,
  con código y mensaje claros.

## 1. Crear un token

AMULEN → **Mi Perfil** → *Tokens de API* → *Crear token*. Copia el valor
(`amu_…`): se muestra una sola vez. Actúa con tus permisos; revócalo desde el mismo
lugar si se filtra.

## 2. Configurar el cliente MCP

### Claude Code

```bash
claude mcp add amulen \
  -e AMULEN_BASE_URL=https://amulen.3htp.cloud \
  -e AMULEN_TOKEN=amu_xxx \
  -- uvx --from "git+ssh://git@github.com/lramirezq/amulen.git#subdirectory=mcp" amulen-mcp
```

### Claude Desktop / otros (JSON)

```json
{
  "mcpServers": {
    "amulen": {
      "command": "uvx",
      "args": ["--from", "git+ssh://git@github.com/lramirezq/amulen.git#subdirectory=mcp", "amulen-mcp"],
      "env": {
        "AMULEN_BASE_URL": "https://amulen.3htp.cloud",
        "AMULEN_TOKEN": "amu_xxx"
      }
    }
  }
}
```

Desde una copia local del repo: `"command": "uv", "args": ["run", "--directory", "/ruta/a/raki/mcp", "amulen-mcp"]`.

`AMULEN_BASE_URL` es el subdominio de tu tenant. Si apunta a otro, la API responde
con una redirección y la herramienta lo explica.

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `amulen_whoami` | Usuario del token |
| `amulen_my_tasks` | Mis tareas en todos los proyectos (filtros: estado, proyecto, texto, vencidas) |
| `amulen_list_projects` / `amulen_get_project` | Proyectos accesibles / detalle con tableros |
| `amulen_project_dashboard` | Métricas: por estado, vencidas, horas, por usuario, bolsas de horas |
| `amulen_list_members` | Miembros con su id (para `user_ids`) |
| `amulen_create_project` / `amulen_update_project` | Crear / editar proyecto |
| `amulen_list_boards` / `amulen_get_board` / `amulen_create_board` | Tableros |
| `amulen_list_tasks` / `amulen_get_task` | Tareas de un tablero / detalle con checklist y comentarios |
| `amulen_create_task` / `amulen_update_task` | Crear / editar (incluye mover de estado y registrar horas reales) |
| `amulen_add_comment` | Comentar una tarea |
| `amulen_add_checklist_items` / `amulen_update_checklist_item` / `amulen_delete_checklist_item` | Checklist |
| `amulen_upload_attachment` | Adjuntar evidencia: un archivo local (`file_path`) o un texto generado (`nombre` + `contenido_texto`). Máx. 25 MB |
| `amulen_list_attachments` / `amulen_download_attachment` | Ver los adjuntos de una tarea y descargarlos (por defecto a `~/Downloads/amulen/<tarea>/`, sin sobrescribir) |

## Desarrollo

```bash
cd mcp
uv sync
uv run pytest
```

La API está documentada en `docs/API_V1.md` en la raíz del repo.
