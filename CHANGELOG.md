# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/) e [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-16

### Adicionado
- Autenticação OAuth2 (client credentials) contra o Copernicus Data Space Ecosystem, com credenciais salvas localmente via QSettings.
- Definição de área de interesse a partir da extensão atual do mapa, com reprojeção automática para WGS84.
- Busca de cenas Sentinel-2 L2A via Catalog API, filtrando por intervalo de datas e cobertura máxima de nuvens, com deduplicação de cenas do mesmo dia.
- Três composições de banda prontas via evalscript (Process API): Cor Real (RGB), Falso-Cor (infravermelho) e NDVI.
- Download paralelo (thread pool) das cenas selecionadas, com fallback automático de resolução (10 m → 20 m → 60 m) por cena.
- Carregamento automático das imagens baixadas como camadas raster no projeto do QGIS.
