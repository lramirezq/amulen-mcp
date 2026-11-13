"""Servidor MCP de AMULEN.

Cada herramienta hace una sola llamada a la API v1 (/api/v1). Los errores de
la API (403, 404, 422...) se devuelven como errores de la herramienta con un
mensaje claro, sin interrumpir al resto.

Configuración (variables de entorno):
  AMULEN_BASE_URL  p. ej. https://amulen.3htp.cloud
  AMULEN_TOKEN     token personal (AMULEN → Mi Perfil → Tokens de API)
  AMULEN_TIMEOUT   segundos (opcional, 30 por defecto)
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from .client import AmulenClient, AmulenError, Settings, seg

Estado = Literal["TO DO", "DOING", "DONE", "PENDING", "BACKLOG"]
Formato = Literal["markdown", "html", "texto"]

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)

mcp = FastMCP(
    "amulen",
    instructions=(
        "AMULEN: gestión de proyectos, tableros y tareas (tarjetas). "
        "Jerarquía: proyecto (project_slug) → tablero (board_slug) → tarea (task_slug). "
        "Para 'mis tareas' usa amulen_my_tasks (una sola llamada). "
        "Los slugs que devuelven las herramientas se usan tal cual en las siguientes llamadas. "
        "Para asignar usuarios, obtén sus ids con amulen_list_members. "
        "Comentarios y descripciones se escriben en Markdown (negritas, listas, tablas, código): "
        "AMULEN los muestra con formato. Al leer, usa los campos *_markdown."
    ),
)

_client: AmulenClient | None = None


def _get_client() -> AmulenClient:
    global _client
    if _client is None:
        try:
            _client = AmulenClient(Settings.from_env())
        except AmulenError as e:
            raise ToolError(str(e)) from e
    return _client


def set_client(client: AmulenClient | None) -> None:
    """Permite inyectar un cliente (tests)."""
    global _client
    _client = client


async def _call(method: str, path: str, **kwargs: Any) -> Any:
    client = _get_client()
    try:
        return await getattr(client, method)(path, **kwargs)
    except AmulenError as e:
        raise ToolError(str(e)) from e


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _estados(estado: list[str] | None) -> str | None:
    return ",".join(estado) if estado else None


def _task_path(project_slug: str, board_slug: str, task_slug: str | None = None) -> str:
    path = f"/proyectos/{seg(project_slug)}/tableros/{seg(board_slug)}/tareas"
    return f"{path}/{seg(task_slug)}" if task_slug else path


# --- Usuario --------------------------------------------------------------


@mcp.tool(annotations=READ)
async def amulen_whoami() -> dict:
    """Show the AMULEN user behind the configured token (name, email, roles, tenant)."""
    return await _call("get", "/me")


@mcp.tool(annotations=READ)
async def amulen_my_tasks(
    estado: list[str] | None = None,
    project_slug: str | None = None,
    q: str | None = None,
    vencidas: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List tasks assigned to me across all projects and boards, in a single call.

    estado: states to include (TO DO, DOING, DONE, PENDING, BACKLOG, or ALL). Default: TO DO + DOING.
    project_slug: limit to one project. q: text search in title/description.
    vencidas: only tasks whose due date (fecha_fin) already passed.
    Sorted by due date (soonest first). Use meta.next_offset to paginate.
    """
    return await _call(
        "get", "/me/tasks", estado=_estados(estado), proyecto=project_slug, q=q,
        vencidas="true" if vencidas else None, limit=limit, offset=offset,
    )


# --- Proyectos ------------------------------------------------------------


@mcp.tool(annotations=READ)
async def amulen_list_projects(q: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    """List the projects I can access (optionally filtered by name with q)."""
    return await _call("get", "/proyectos", q=q, limit=limit, offset=offset)


@mcp.tool(annotations=READ)
async def amulen_get_project(project_slug: str) -> dict:
    """Get a project with the boards I can see in it."""
    return await _call("get", f"/proyectos/{seg(project_slug)}")


@mcp.tool(annotations=READ)
async def amulen_project_dashboard(project_slug: str) -> dict:
    """Project metrics: tasks by state, overdue tasks, hours (projected/real), tasks per user, and per-board hour budgets."""
    return await _call("get", f"/proyectos/{seg(project_slug)}/dashboard")


@mcp.tool(annotations=READ)
async def amulen_list_members(project_slug: str) -> dict:
    """List active project members with their user id and role. Use the ids for task assignment (user_ids)."""
    return await _call("get", f"/proyectos/{seg(project_slug)}/members")


@mcp.tool(annotations=WRITE)
async def amulen_create_project(nombre: str, descripcion: str | None = None) -> dict:
    """Create a project. The creator becomes its admin."""
    return await _call("post", "/proyectos", json=_clean({"nombre": nombre, "descripcion": descripcion}))


@mcp.tool(annotations=WRITE)
async def amulen_update_project(project_slug: str, nombre: str | None = None, descripcion: str | None = None) -> dict:
    """Rename a project or change its description (project admins only). Note: renaming changes the slug."""
    return await _call("patch", f"/proyectos/{seg(project_slug)}", json=_clean({"nombre": nombre, "descripcion": descripcion}))


# --- Tableros -------------------------------------------------------------


@mcp.tool(annotations=READ)
async def amulen_list_boards(project_slug: str) -> dict:
    """List the boards of a project that I can see, with their columns (valid states) and whether I can edit them."""
    return await _call("get", f"/proyectos/{seg(project_slug)}/tableros")


@mcp.tool(annotations=READ)
async def amulen_get_board(project_slug: str, board_slug: str) -> dict:
    """Get a board with task counts per state and its hour budget (bolsa de horas: total, spent, scheduled, available)."""
    return await _call("get", f"/proyectos/{seg(project_slug)}/tableros/{seg(board_slug)}")


@mcp.tool(annotations=WRITE)
async def amulen_create_board(
    project_slug: str, nombre: str, bolsa_horas: bool = False, horas_totales: float | None = None
) -> dict:
    """Create a board in a project. bolsa_horas + horas_totales turn it into an hour-budget board."""
    return await _call(
        "post", f"/proyectos/{seg(project_slug)}/tableros",
        json=_clean({"nombre": nombre, "bolsa_horas": bolsa_horas, "horas_totales": horas_totales}),
    )


# --- Tareas ---------------------------------------------------------------


@mcp.tool(annotations=READ)
async def amulen_list_tasks(
    project_slug: str,
    board_slug: str,
    estado: list[str] | None = None,
    mias: bool = False,
    asignado_a: int | None = None,
    q: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List tasks in a board.

    estado: states to include. mias: only tasks assigned to me. asignado_a: user id.
    fecha_desde / fecha_hasta: due-date range, format YYYY-MM-DD. q: text search.
    """
    return await _call(
        "get", _task_path(project_slug, board_slug), estado=_estados(estado),
        mias="true" if mias else None, asignado_a=asignado_a, q=q,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, limit=limit, offset=offset,
    )


@mcp.tool(annotations=READ)
async def amulen_get_task(project_slug: str, board_slug: str, task_slug: str) -> dict:
    """Get a task with description (HTML and plain text), assignees, checklist (with item ids) and comments."""
    return await _call("get", _task_path(project_slug, board_slug, task_slug))


@mcp.tool(annotations=WRITE)
async def amulen_create_task(
    project_slug: str,
    board_slug: str,
    titulo: str,
    descripcion: str | None = None,
    estado: Estado | None = None,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
    horas_proyectadas: float | None = None,
    puntuacion: int | None = None,
    user_ids: list[int] | None = None,
    formato: Formato = "markdown",
) -> dict:
    """Create a task. descripcion is Markdown by default (formato: markdown | html | texto).
    Dates YYYY-MM-DD. estado defaults to the board's first column.
    user_ids must be active project members (see amulen_list_members)."""
    return await _call(
        "post", _task_path(project_slug, board_slug),
        json=_clean({
            "titulo": titulo, "descripcion": descripcion, "estado": estado,
            "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
            "horas_proyectadas": horas_proyectadas, "puntuacion": puntuacion, "user_ids": user_ids,
            "formato": formato if descripcion is not None else None,
        }),
    )


@mcp.tool(annotations=WRITE)
async def amulen_update_task(
    project_slug: str,
    board_slug: str,
    task_slug: str,
    titulo: str | None = None,
    descripcion: str | None = None,
    estado: Estado | None = None,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
    horas_proyectadas: float | None = None,
    horas_reales: float | None = None,
    puntuacion: int | None = None,
    user_ids: list[int] | None = None,
    formato: Formato = "markdown",
) -> dict:
    """Update a task; only the fields you pass change. descripcion is Markdown by default. Use it to move a task (estado) or log real hours (horas_reales).
    user_ids replaces the whole assignee list."""
    return await _call(
        "patch", _task_path(project_slug, board_slug, task_slug),
        json=_clean({
            "titulo": titulo, "descripcion": descripcion, "estado": estado,
            "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin, "horas_proyectadas": horas_proyectadas,
            "horas_reales": horas_reales, "puntuacion": puntuacion, "user_ids": user_ids,
            "formato": formato if descripcion is not None else None,
        }),
    )


@mcp.tool(annotations=WRITE)
async def amulen_add_comment(
    project_slug: str, board_slug: str, task_slug: str, contenido: str, formato: Formato = "markdown"
) -> dict:
    """Add a comment to a task. Write it in Markdown (bold, lists, tables, code blocks, links):
    AMULEN renders it formatted. formato: markdown (default) | html | texto (no formatting)."""
    return await _call(
        "post", f"{_task_path(project_slug, board_slug, task_slug)}/comentarios",
        json={"contenido": contenido, "formato": formato},
    )


# --- Checklist ------------------------------------------------------------


@mcp.tool(annotations=WRITE)
async def amulen_add_checklist_items(
    project_slug: str, board_slug: str, task_slug: str, items: list[dict[str, str]]
) -> dict:
    """Add one or more checklist items to a task. items: [{"titulo": "...", "descripcion": "..."}] (descripcion optional)."""
    return await _call(
        "post", f"{_task_path(project_slug, board_slug, task_slug)}/checklist", json={"items": items}
    )


@mcp.tool(annotations=WRITE)
async def amulen_update_checklist_item(
    project_slug: str,
    board_slug: str,
    task_slug: str,
    item_id: int,
    completado: bool | None = None,
    titulo: str | None = None,
    descripcion: str | None = None,
) -> dict:
    """Update a checklist item (mark completed/uncompleted, rename). Get item ids from amulen_get_task."""
    return await _call(
        "patch", f"{_task_path(project_slug, board_slug, task_slug)}/checklist/{int(item_id)}",
        json=_clean({"completado": completado, "titulo": titulo, "descripcion": descripcion}),
    )


@mcp.tool(annotations=DELETE)
async def amulen_delete_checklist_item(project_slug: str, board_slug: str, task_slug: str, item_id: int) -> dict:
    """Delete a checklist item from a task."""
    return await _call("delete", f"{_task_path(project_slug, board_slug, task_slug)}/checklist/{int(item_id)}")


# --- Adjuntos (evidencia) -------------------------------------------------

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@mcp.tool(annotations=READ)
async def amulen_list_attachments(project_slug: str, board_slug: str, task_slug: str) -> dict:
    """List a task's attachments (id, file name, content type, size)."""
    return await _call("get", f"{_task_path(project_slug, board_slug, task_slug)}/adjuntos")


@mcp.tool(annotations=WRITE)
async def amulen_upload_attachment(
    project_slug: str,
    board_slug: str,
    task_slug: str,
    file_path: str | None = None,
    nombre: str | None = None,
    contenido_texto: str | None = None,
) -> dict:
    """Attach evidence to a task (max 25 MB).

    Either file_path: a local file (screenshot, PDF, log, zip...) on this machine; nombre optionally renames it.
    Or nombre + contenido_texto: a text document you write (e.g. "evidencia.md" with a summary of the work done).
    """
    path = _task_path(project_slug, board_slug, task_slug) + "/adjuntos"
    if file_path:
        local = Path(file_path).expanduser()
        if not local.is_file():
            raise ToolError(f"No existe el archivo: {local}")
        size = local.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            raise ToolError(f"too_large: {local.name} pesa {size / 1048576:.1f} MB (máximo 25 MB)")
        filename = nombre or local.name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        client = _get_client()
        try:
            return await client.upload(path, filename=filename, content=local.read_bytes(), content_type=content_type)
        except AmulenError as e:
            raise ToolError(str(e)) from e
    if nombre and contenido_texto is not None:
        return await _call("post", path, json={"nombre": nombre, "contenido_texto": contenido_texto})
    raise ToolError("Indica file_path, o bien nombre + contenido_texto")


@mcp.tool(annotations=WRITE)
async def amulen_download_attachment(
    project_slug: str, board_slug: str, task_slug: str, attachment_id: int, destino: str | None = None
) -> dict:
    """Download a task attachment to a local folder (default: ~/Downloads/amulen/<task_slug>/).
    Returns the saved path so you can open or analyze the file. Never overwrites existing files."""
    client = _get_client()
    try:
        content, filename = await client.download(
            f"{_task_path(project_slug, board_slug, task_slug)}/adjuntos/{int(attachment_id)}"
        )
    except AmulenError as e:
        raise ToolError(str(e)) from e
    folder = Path(destino).expanduser() if destino else Path.home() / "Downloads" / "amulen" / task_slug
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename or f"adjunto-{attachment_id}").name or f"adjunto-{attachment_id}"
    target = folder / safe_name
    n = 1
    while target.exists():
        target = folder / f"{Path(safe_name).stem} ({n}){Path(safe_name).suffix}"
        n += 1
    target.write_bytes(content)
    return {"ruta": str(target), "bytes": len(content)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
