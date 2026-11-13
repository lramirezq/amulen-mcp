import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from amulen_mcp import server
from amulen_mcp.client import AmulenClient, AmulenError, Settings


class Recorder:
    """Transport falso: registra las requests y responde según una tabla."""

    def __init__(self, routes):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        status, body = self.routes.get(key, (404, {"error": {"code": "not_found", "message": "Recurso no encontrado"}}))
        return httpx.Response(status, json=body)


@pytest.fixture
def fake():
    def make(routes):
        rec = Recorder(routes)
        client = AmulenClient(Settings("https://acme.3htp.cloud", "amu_test"), transport=httpx.MockTransport(rec))
        server.set_client(client)
        return rec

    yield make
    server.set_client(None)


async def test_my_tasks_una_sola_llamada_con_filtros(fake):
    rec = fake({("GET", "/api/v1/me/tasks"): (200, {"data": [{"slug": "t1"}], "meta": {"total": 1}})})
    result = await server.amulen_my_tasks(estado=["TO DO", "DOING"], project_slug="sura", vencidas=True)
    assert result["data"][0]["slug"] == "t1"
    assert len(rec.requests) == 1
    req = rec.requests[0]
    assert req.headers["Authorization"] == "Bearer amu_test"
    assert req.url.params["estado"] == "TO DO,DOING"
    assert req.url.params["proyecto"] == "sura"
    assert req.url.params["vencidas"] == "true"
    assert "q" not in req.url.params


async def test_error_de_api_se_convierte_en_tool_error_legible(fake):
    fake({("GET", "/api/v1/proyectos/x/tableros/y/tareas"): (403, {"error": {"code": "forbidden", "message": "No tienes permisos para ver este tablero"}})})
    with pytest.raises(ToolError) as exc:
        await server.amulen_list_tasks("x", "y")
    assert "forbidden" in str(exc.value)
    assert "No tienes permisos" in str(exc.value)


async def test_validacion_incluye_detalles(fake):
    fake({("POST", "/api/v1/proyectos/p/tableros/b/tareas"): (422, {"error": {"code": "validation_failed", "message": "Estado inválido", "details": {"estado": ["TO DO"]}}})})
    with pytest.raises(ToolError) as exc:
        await server.amulen_create_task("p", "b", "Titulo", estado="TO DO")
    assert "validation_failed" in str(exc.value) and "TO DO" in str(exc.value)


async def test_update_task_envia_solo_campos_presentes(fake):
    rec = fake({("PATCH", "/api/v1/proyectos/p/tableros/b/tareas/t"): (200, {"data": {"estado": "DONE"}})})
    await server.amulen_update_task("p", "b", "t", estado="DONE", horas_reales=2.5)
    assert json.loads(rec.requests[0].content) == {"estado": "DONE", "horas_reales": 2.5}


async def test_slugs_se_escapan_en_la_url(fake):
    rec = fake({})
    with pytest.raises(ToolError):
        await server.amulen_get_project("a/../b")
    assert rec.requests[0].url.raw_path == b"/api/v1/proyectos/a%2F..%2Fb"


async def test_checklist_en_lote(fake):
    rec = fake({("POST", "/api/v1/proyectos/p/tableros/b/tareas/t/checklist"): (201, {"data": [{"id": 1}, {"id": 2}], "progreso": 0})})
    result = await server.amulen_add_checklist_items("p", "b", "t", [{"titulo": "Uno"}, {"titulo": "Dos"}])
    assert [i["id"] for i in result["data"]] == [1, 2]
    assert json.loads(rec.requests[0].content) == {"items": [{"titulo": "Uno"}, {"titulo": "Dos"}]}


async def test_redireccion_indica_base_url_incorrecta():
    def handler(request):
        return httpx.Response(302, headers={"location": "https://admin-amulen.3htp.cloud"})

    client = AmulenClient(Settings("https://3htp.cloud", "amu_x"), transport=httpx.MockTransport(handler))
    with pytest.raises(AmulenError) as exc:
        await client.get("/me")
    assert exc.value.code == "redirect"
    assert "AMULEN_BASE_URL" in exc.value.message


async def test_sin_configuracion_da_error_claro(monkeypatch):
    monkeypatch.delenv("AMULEN_BASE_URL", raising=False)
    monkeypatch.delenv("AMULEN_TOKEN", raising=False)
    server.set_client(None)
    with pytest.raises(ToolError) as exc:
        await server.amulen_whoami()
    assert "AMULEN_TOKEN" in str(exc.value)


async def test_todas_las_herramientas_registradas():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    esperadas = {
        "amulen_whoami", "amulen_my_tasks", "amulen_list_projects", "amulen_get_project",
        "amulen_project_dashboard", "amulen_list_members", "amulen_create_project", "amulen_update_project",
        "amulen_list_boards", "amulen_get_board", "amulen_create_board", "amulen_list_tasks",
        "amulen_get_task", "amulen_create_task", "amulen_update_task", "amulen_add_comment",
        "amulen_add_checklist_items", "amulen_update_checklist_item", "amulen_delete_checklist_item",
        "amulen_list_attachments", "amulen_upload_attachment", "amulen_download_attachment",
    }
    assert esperadas <= set(tools)
    assert tools["amulen_my_tasks"].annotations.readOnlyHint is True
    assert tools["amulen_delete_checklist_item"].annotations.destructiveHint is True


async def test_subir_archivo_local_multipart(fake, tmp_path):
    rec = fake({("POST", "/api/v1/proyectos/p/tableros/b/tareas/t/adjuntos"): (201, {"data": {"id": 7, "nombre": "captura.png"}})})
    f = tmp_path / "captura.png"
    f.write_bytes(b"\x89PNG fake")
    result = await server.amulen_upload_attachment("p", "b", "t", file_path=str(f))
    assert result["data"]["id"] == 7
    req = rec.requests[0]
    assert req.headers["content-type"].startswith("multipart/form-data")
    assert b'name="archivo"; filename="captura.png"' in req.content
    assert b"Content-Type: image/png" in req.content
    assert b"\x89PNG fake" in req.content


async def test_subir_texto_generado(fake):
    rec = fake({("POST", "/api/v1/proyectos/p/tableros/b/tareas/t/adjuntos"): (201, {"data": {"id": 8}})})
    await server.amulen_upload_attachment("p", "b", "t", nombre="evidencia.md", contenido_texto="# Hecho")
    assert json.loads(rec.requests[0].content) == {"nombre": "evidencia.md", "contenido_texto": "# Hecho"}


async def test_subir_valida_archivo_y_tamano(fake, tmp_path, monkeypatch):
    rec = fake({})
    with pytest.raises(ToolError, match="No existe"):
        await server.amulen_upload_attachment("p", "b", "t", file_path=str(tmp_path / "nada.png"))
    grande = tmp_path / "grande.bin"
    grande.write_bytes(b"x" * 11)
    monkeypatch.setattr(server, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(ToolError, match="too_large"):
        await server.amulen_upload_attachment("p", "b", "t", file_path=str(grande))
    with pytest.raises(ToolError, match="file_path"):
        await server.amulen_upload_attachment("p", "b", "t")
    assert rec.requests == []


async def test_descargar_sin_sobrescribir(tmp_path):
    def handler(request):
        return httpx.Response(200, content=b"datos", headers={"content-disposition": 'attachment; filename="log.txt"'})

    server.set_client(AmulenClient(Settings("https://acme.3htp.cloud", "amu_x"), transport=httpx.MockTransport(handler)))
    try:
        r1 = await server.amulen_download_attachment("p", "b", "t", 5, destino=str(tmp_path))
        r2 = await server.amulen_download_attachment("p", "b", "t", 5, destino=str(tmp_path))
    finally:
        server.set_client(None)
    assert r1["ruta"].endswith("log.txt") and r2["ruta"].endswith("log (1).txt")
    assert (tmp_path / "log.txt").read_bytes() == b"datos"


async def test_descarga_no_escapa_de_la_carpeta(tmp_path):
    def handler(request):
        return httpx.Response(200, content=b"x", headers={"content-disposition": 'attachment; filename="../../etc/evil"'})

    server.set_client(AmulenClient(Settings("https://acme.3htp.cloud", "amu_x"), transport=httpx.MockTransport(handler)))
    try:
        r = await server.amulen_download_attachment("p", "b", "t", 1, destino=str(tmp_path))
    finally:
        server.set_client(None)
    assert r["ruta"] == str(tmp_path / "evil")


async def test_bloqueo_del_waf_se_identifica(fake):
    def handler(request):
        return httpx.Response(403, text="<html>403 Forbidden</html>", headers={"server": "awselb/2.0"})

    server.set_client(AmulenClient(Settings("https://acme.3htp.cloud", "amu_x"), transport=httpx.MockTransport(handler)))
    with pytest.raises(ToolError, match="blocked_by_waf"):
        await server.amulen_list_attachments("p", "b", "t")
