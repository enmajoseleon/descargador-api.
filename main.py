import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

class VideoRequest(BaseModel):
    url: str

def es_url_valida(url_a_validar: str) -> bool:
    dominios_permitidos = [
        "tiktok.com", "x.com", "twitter.com", 
        "instagram.com", "facebook.com", "fb.watch"
    ]
    return any(dominio in url_a_validar.lower() for dominio in dominios_permitidos)

@app.post("/extraer")
async def extraer_video(request: VideoRequest):
    url_original = request.url.strip()
    
    if not es_url_valida(url_original):
        raise HTTPException(status_code=403, detail="Plataforma no soportada.")

    # --- 🛠️ CONFIGURACIÓN DE INGENIERÍA PARA TIKTOK ---
    ydl_opts = {
        # 'format': 'b' fuerza a buscar el mejor video con audio integrado (SINGLE FILE)
        # Esto evita que te mande links separados de video y audio.
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extract_flat': False, # Necesitamos entrar al video, no solo ver el link
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.tiktok.com/',
        }
    }

    try:
        loop = asyncio.get_running_loop()
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 🚀 Extracción asíncrona
            info = await loop.run_in_executor(
                None, 
                lambda: ydl.extract_info(url_original, download=False)
            )
            
            # TikTok a veces guarda la URL real dentro de 'url' o dentro de 'formats'
            url_final = info.get('url')
            
            # Si 'url' no está, buscamos en los formatos el que sea mp4 y tenga audio y video
            if not url_final and 'formats' in info:
                for f in reversed(info['formats']):
                    if f.get('acodec') != 'none' and f.get('vcodec') != 'none':
                        url_final = f.get('url')
                        break

            return {
                "status": "success",
                "titulo": info.get('title', 'Video de Emmanuel'),
                "url_descarga": url_final,
                "plataforma": info.get('extractor_key'),
            }
            
    except Exception as e:
        print(f"Error técnico: {str(e)}")
        raise HTTPException(status_code=400, detail="Error en el motor de extracción.")