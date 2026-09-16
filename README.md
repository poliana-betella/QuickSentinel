# QuickSentinel

Plugin QGIS que automatiza a busca e o download de imagens Sentinel-2 usando a API pública do [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) (o sucessor gratuito do antigo Sentinel Hub da Sinergise), direto de dentro do QGIS.

## Motivação

Baixar imagens Sentinel-2 manualmente (procurar cena por cena, checar cobertura de nuvens, baixar banda por banda, montar a composição) é repetitivo. Este plugin automatiza o fluxo inteiro: você define a área e o período de interesse, o plugin busca todas as cenas disponíveis, você escolhe quais baixar e em qual composição, e o plugin baixa tudo em paralelo — já pronto como um raster carregado no QGIS.

## Como funciona

1. **Área de interesse**: usa a extensão atual do mapa (canvas) como bounding box, reprojetada automaticamente para WGS84.
2. **Busca**: consulta a Catalog API do Copernicus Data Space por cenas Sentinel-2 L2A que cruzam essa área, no intervalo de datas e cobertura de nuvens definidos. Cenas duplicadas do mesmo dia (órbitas sobrepostas) são automaticamente filtradas.
3. **Composição**: cada download é gerado sob demanda pela Process API, usando um *evalscript* (script de composição de banda executado no servidor). O plugin já vem com três composições prontas — Cor Real (RGB), Falso-Cor (infravermelho) e NDVI.
4. **Download paralelo com fallback de resolução**: as cenas selecionadas são baixadas simultaneamente (thread pool). Se uma cena falhar na resolução pedida (10 m), o plugin tenta de novo automaticamente numa resolução mais tolerante (20 m, depois 60 m) antes de desistir dela — sem travar o restante do lote.
5. **Carregamento automático**: cada imagem baixada com sucesso é adicionada como camada raster no projeto do QGIS.

## Autenticação

O Copernicus Data Space Ecosystem oferece acesso gratuito via OAuth2 (client credentials). Crie suas próprias credenciais em [dataspace.copernicus.eu](https://dataspace.copernicus.eu/) → Dashboard → OAuth clients, e cole o `client_id`/`client_secret` no plugin. As credenciais ficam salvas localmente nas configurações do QGIS (`QSettings`), nunca no código do plugin nem em nenhum repositório.

## Uso

Menu **QuickSentinel → Buscar imagens Sentinel-2...** (ou ícone na barra de ferramentas Raster).

## Instalação

Copie a pasta do plugin para o diretório de plugins do QGIS (`Configurações → Perfis de usuário → Abrir pasta de perfil ativo → python/plugins`) e ative em **Complementos → Gerenciar e Instalar Complementos**.

## Stack

Python + API do QGIS (PyQt/qgis.core) + `requests`, usando a API REST pública do Copernicus Data Space Ecosystem (Catalog API + Process API). Sem dependências de infraestrutura proprietária.
