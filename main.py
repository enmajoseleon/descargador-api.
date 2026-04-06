import httpx
import yt_dlp
import asyncio
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# --- CONFIGURACIÓN DE RECURSOS (MÁXIMA EFICIENCIA) ---
executor = ThreadPoolExecutor(max_workers=4)
extraction_semaphore = asyncio.Semaphore(2) # Bajamos a 2 para evitar picos de RAM en Render

@app.get("/")
def home():
    return {"status": "Hyper Blindado 🛡️", "engine": "yt-dlp + HTTPX Stream"}

async def stream_video(url: str, headers: dict) -> AsyncGenerator[bytes, None]:
    """Flujo de datos ultra-seguro con bypass de 0 bytes."""
    try:
        # Usamos un cliente con límites de conexión optimizados
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, limits=limits) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    print(f"❌ Error de Origen: {response.status_code}")
                    return

                # Si no hay Content-Length, TikTok nos está engañando
                if not response.headers.get("Content-Length") and "tiktok" in url:
                    print("⚠️ Advertencia: TikTok envió flujo sin tamaño definido.")

                async for chunk in response.aiter_bytes(chunk_size=1024 * 64): # Chunks más pequeños (64KB)
                    yield chunk
    except Exception as e:
        print(f"⚠️ Error en el Stream: {e}")

def extraer_info_hyper(url: str):
    """Extracción con limpieza de metadatos y bypass de cookies."""
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'cachedir': False,
        'no_check_certificate': True,
        'socket_timeout': 20,
        # USER AGENT ACTUALIZADO A CHROME 122
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'http_headers': {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.tiktok.com/',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return ydl.sanitize_info(info)

@app.get("/descargar")
async def descargar_video(url: str = Query(...)):
    async with extraction_semaphore:
        try:
            loop = asyncio.get_event_loop()
            # PASO 1: Extracción con limpieza de datos
            info = await loop.run_in_executor(executor, extraer_info_hyper, url)
            
            # Buscamos la URL en 'url' o en la lista de formatos
            video_url = info.get('url')
            if not video_url and info.get('formats'):
                # Filtramos para obtener el formato que NO tenga marca de agua (si aplica)
                video_url = info['formats'][-1].get('url')

            if not video_url:
                raise HTTPException(status_code=404, detail="No se encontró el flujo de video")

            # PASO 2: CLONACIÓN DE CABECERAS (El "Hyper" Blindaje)
            # Copiamos los headers exactos que yt-dlp usó para que TikTok no sospeche
            headers_de_vuelo = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'identity', # Crucial para no recibir 0 bytes comprimidos
                'Referer': 'https://www.tiktok.com/' if 'tiktok' in url else 'https://www.instagram.com/',
                'Connection': 'keep-alive',
                'Range': 'bytes=0-', # Fuerza el inicio del flujo
            }

            # Si yt-dlp nos dio cookies o headers específicos, los inyectamos
            if info.get('http_headers'):
                headers_de_vuelo.update(info['http_headers'])

            print(f"✅ Link extraído con éxito para: {url[:30]}...")

            # PASO 3: Respuesta de flujo con headers de descarga
            return StreamingResponse(
                stream_video(video_url, headers_de_vuelo),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": "attachment; filename=video_emmanuel.mp4",
                    "Content-Type": "video/mp4",
                    "Accept-Ranges": "bytes"
                }
            )

        except Exception as e:
            print(f"🔥 Error Crítico: {str(e)}")
            raise HTTPException(status_code=500, detail="El motor no pudo procesar este link.")