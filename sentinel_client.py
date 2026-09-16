# -*- coding: utf-8 -*-
"""
Cliente para a API publica do Copernicus Data Space Ecosystem (Sentinel Hub):
autenticacao OAuth2, busca de cenas via Catalog API e download de imagens
via Process API, com paralelismo e fallback automatico de resolucao.

Nenhuma credencial fica gravada neste arquivo: client_id/client_secret sao
fornecidos pelo usuario (gratuitos em https://dataspace.copernicus.eu) e
passados em tempo de execucao.
"""
import concurrent.futures
import datetime
import json
import os
import tempfile

import requests

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOG_URL = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
COLLECTION = "sentinel-2-l2a"

# Resolucoes tentadas em ordem, do melhor caso ate o mais tolerante.
# Cada valor e o tamanho de pixel em metros usado para calcular width/height
# a partir do bbox (fallback automatico: se uma cena falha, tenta a proxima).
RESOLUTION_FALLBACK_CHAIN = [10, 20, 60]

MAX_IMAGE_SIDE_PX = 2500  # limite do Process API por requisicao

# Composicoes de banda prontas (evalscripts do Process API v3).
EVALSCRIPTS = {
    "true_color": """
//VERSION=3
function setup() {
  return { input: ["B04","B03","B02"], output: { bands: 3 } };
}
function evaluatePixel(s) {
  return [2.5*s.B04, 2.5*s.B03, 2.5*s.B02];
}
""",
    "false_color": """
//VERSION=3
function setup() {
  return { input: ["B08","B04","B03"], output: { bands: 3 } };
}
function evaluatePixel(s) {
  return [2.5*s.B08, 2.5*s.B04, 2.5*s.B03];
}
""",
    "ndvi": """
//VERSION=3
function setup() {
  return { input: ["B04","B08"], output: { bands: 1, sampleType: "FLOAT32" } };
}
function evaluatePixel(s) {
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04 + 1e-9);
  return [ndvi];
}
""",
}


class SentinelAuthError(Exception):
    pass


def get_access_token(client_id, client_secret):
    """Troca client_id/client_secret por um token OAuth2 de acesso."""
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    response = requests.post(TOKEN_URL, data=payload, timeout=30)
    if response.status_code != 200:
        raise SentinelAuthError(
            "Falha na autenticacao ({}): {}".format(response.status_code, response.text[:300])
        )
    token = response.json().get("access_token")
    if not token:
        raise SentinelAuthError("Resposta de autenticacao sem access_token.")
    return token


def search_scenes(token, bbox_wgs84, start_date, end_date, max_cloud_cover=100, limit=50):
    """
    Busca cenas Sentinel-2 L2A que interceptam o bbox (WGS84: minx,miny,maxx,maxy)
    dentro do intervalo de datas, filtrando por cobertura maxima de nuvens.
    Retorna uma lista de dicts com id, data e cobertura de nuvens.
    """
    headers = {"Authorization": "Bearer {}".format(token), "Content-Type": "application/json"}
    body = {
        "collections": [COLLECTION],
        "datetime": "{}T00:00:00Z/{}T23:59:59Z".format(start_date.isoformat(), end_date.isoformat()),
        "bbox": list(bbox_wgs84),
        "limit": limit,
        "filter": "eo:cloud_cover < {}".format(max_cloud_cover),
        "filter-lang": "cql2-text",
    }
    response = requests.post(CATALOG_URL, headers=headers, data=json.dumps(body), timeout=30)
    response.raise_for_status()
    features = response.json().get("features", [])

    scenes = []
    seen_dates = set()
    for feature in features:
        props = feature.get("properties", {})
        date_str = (props.get("datetime") or "")[:10]
        # evita baixar duas cenas quase identicas do mesmo dia (orbitas sobrepostas)
        if date_str in seen_dates:
            continue
        seen_dates.add(date_str)
        scenes.append({
            "id": feature.get("id"),
            "date": date_str,
            "cloud_cover": props.get("eo:cloud_cover"),
        })

    scenes.sort(key=lambda s: s["date"])
    return scenes


def _bbox_to_size(bbox_wgs84, resolution_m):
    """Converte um bbox em graus para largura/altura em pixels numa resolucao dada."""
    minx, miny, maxx, maxy = bbox_wgs84
    meters_per_degree_lat = 111320.0
    meters_per_degree_lon = 111320.0 * abs(__import__("math").cos(__import__("math").radians((miny + maxy) / 2.0)))
    width_m = max(abs(maxx - minx) * meters_per_degree_lon, 1.0)
    height_m = max(abs(maxy - miny) * meters_per_degree_lat, 1.0)
    width_px = max(1, min(MAX_IMAGE_SIDE_PX, round(width_m / resolution_m)))
    height_px = max(1, min(MAX_IMAGE_SIDE_PX, round(height_m / resolution_m)))
    return width_px, height_px


def _download_scene(token, bbox_wgs84, date_str, composite, output_dir, resolution_m):
    """Baixa uma unica cena via Process API numa resolucao especifica."""
    width_px, height_px = _bbox_to_size(bbox_wgs84, resolution_m)

    output_format = "image/tiff" if composite != "ndvi" else "image/tiff"
    body = {
        "input": {
            "bounds": {
                "bbox": list(bbox_wgs84),
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [{
                "type": COLLECTION,
                "dataFilter": {
                    "timeRange": {
                        "from": "{}T00:00:00Z".format(date_str),
                        "to": "{}T23:59:59Z".format(date_str),
                    }
                },
            }],
        },
        "output": {
            "width": width_px,
            "height": height_px,
            "responses": [{"identifier": "default", "format": {"type": output_format}}],
        },
        "evalscript": EVALSCRIPTS[composite],
    }

    headers = {"Authorization": "Bearer {}".format(token), "Content-Type": "application/json"}
    response = requests.post(PROCESS_URL, headers=headers, data=json.dumps(body), timeout=120)

    if response.status_code != 200 or not response.content:
        return None

    filename = "sentinel2_{}_{}_{}m.tif".format(date_str.replace("-", ""), composite, resolution_m)
    path = os.path.join(output_dir, filename)
    with open(path, "wb") as f:
        f.write(response.content)

    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return None

    return {"date": date_str, "path": path, "resolution_m": resolution_m}


def download_scenes(token, bbox_wgs84, scenes, composite, output_dir, max_workers=4,
                     resolution_chain=None, progress_callback=None):
    """
    Baixa varias cenas em paralelo (ThreadPoolExecutor). Se, numa dada
    resolucao, TODAS as cenas falharem, cai automaticamente para a proxima
    resolucao da cadeia antes de desistir (a mesma logica de degradacao
    graciosa usada para lidar com cenas muito grandes ou fora do limite de
    tamanho de imagem do servico).
    """
    os.makedirs(output_dir, exist_ok=True)
    resolution_chain = resolution_chain or RESOLUTION_FALLBACK_CHAIN

    results = []
    for resolution_m in resolution_chain:
        pending = [s for s in scenes if s["date"] not in {r["date"] for r in results}]
        if not pending:
            break

        def _task(scene, res=resolution_m):
            return _download_scene(token, bbox_wgs84, scene["date"], composite, output_dir, res)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_scene = {executor.submit(_task, scene): scene for scene in pending}
            for future in concurrent.futures.as_completed(future_to_scene):
                scene = future_to_scene[future]
                outcome = future.result()
                if outcome:
                    results.append(outcome)
                if progress_callback:
                    progress_callback(scene["date"], outcome is not None, resolution_m)

        if results:
            # ao menos uma cena baixou nesta resolucao: nao precisa degradar mais
            continue

    return results
