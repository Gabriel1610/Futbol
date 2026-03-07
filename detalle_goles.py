import requests
import json
import time
from datetime import datetime, timedelta

# --- CONFIGURACIÓN ---
ID_INDEPENDIENTE = 10078
ID_LIGA_PROFESIONAL = 10128
ID_COPA_LIGA = 10315

# URLs
URL_API_TEAMS = "https://www.fotmob.com/api/teams"
URL_API_LEAGUES = "https://www.fotmob.com/api/leagues"
URL_API_DETALLE = "https://www.fotmob.com/api/matchDetails"

# --- LA PUERTA TRASERA: DISFRAZ DE APP DE ANDROID ---
# Cloudflare rara vez bloquea el tráfico de las apps móviles nativas
# porque sabe que un celular Android no puede resolver un Captcha de seguridad.
HEADERS_MOBILE = {
    "User-Agent": "FotMob/184.0.0.20240101 (Android; 14)",
    "Accept": "application/json",
    "X-FotMob-Platform": "Android"
}

def buscar_partidos():
    print("🔍 Iniciando búsqueda de historial y próximos partidos...")
    jugados = []
    futuros = []
    
    try:
        # Usamos requests normal con los headers de Android
        resp = requests.get(
            URL_API_TEAMS, 
            params={"id": ID_INDEPENDIENTE, "ccode3": "ARG"}, 
            headers=HEADERS_MOBILE,
            timeout=15
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if data:
                fixtures = data.get("fixtures") or {}
                fuentes = [
                    fixtures.get("results", []),
                    fixtures.get("fixtures", []),
                    fixtures.get("allFixtures", [])
                ]
                
                if isinstance(fixtures.get("allFixtures"), dict):
                    for v in fixtures.get("allFixtures").values():
                        if isinstance(v, list): fuentes.append(v)

                for lista in fuentes:
                    if not lista: continue
                    for m in lista:
                        if isinstance(m, dict):
                            hid = m.get("home", {}).get("id")
                            aid = m.get("away", {}).get("id")
                            
                            if hid == ID_INDEPENDIENTE or aid == ID_INDEPENDIENTE:
                                status = m.get("status", {})
                                finished = status.get("finished", False)
                                cancelled = status.get("cancelled", False)
                                
                                if cancelled: continue
                                
                                if finished:
                                    if not any(p['id'] == m['id'] for p in jugados):
                                        jugados.append(m)
                                else:
                                    if not any(p['id'] == m['id'] for p in futuros):
                                        futuros.append(m)
    except Exception as e:
        print(f"   [!] Error en carga standard: {e}")

    if len(jugados) < 5:
        anios_a_buscar = ["2025", "2024", "2023"]
        torneos = [(ID_LIGA_PROFESIONAL, "Liga Profesional"), (ID_COPA_LIGA, "Copa de la Liga")]
        
        for anio in anios_a_buscar:
            if len(jugados) >= 5: break
            print(f"   -> Buscando en temporada {anio}...")
            
            for id_liga, nombre_torneo in torneos:
                try:
                    params = {
                        "id": id_liga, 
                        "season": anio, 
                        "ccode3": "ARG",
                        "timezone": "America/Argentina/Buenos_Aires"
                    }
                    resp = requests.get(URL_API_LEAGUES, params=params, headers=HEADERS_MOBILE, timeout=15)
                    if resp.status_code != 200: continue
                    
                    data = resp.json()
                    if not data: continue
                        
                    matches_obj = data.get("matches") or {}
                    all_matches = matches_obj.get("allMatches") or []
                    
                    for m in all_matches:
                        if not isinstance(m, dict): continue
                        
                        try:
                            hid = int(m.get("home", {}).get("id") or 0)
                            aid = int(m.get("away", {}).get("id") or 0)
                        except: continue
                        
                        if hid == ID_INDEPENDIENTE or aid == ID_INDEPENDIENTE:
                            if m.get("status", {}).get("finished"):
                                if not any(p['id'] == m['id'] for p in jugados):
                                    m['torneo_nombre'] = f"{nombre_torneo} {anio}"
                                    jugados.append(m)
                                    
                except Exception as e:
                    print(f"      Error leyendo {nombre_torneo} {anio}: {e}")
                    continue

    jugados.sort(key=lambda x: x.get("status", {}).get("utcTime", ""), reverse=True)
    futuros.sort(key=lambda x: x.get("status", {}).get("utcTime", ""), reverse=False)
    
    return jugados, futuros

def obtener_detalles_capa_2(match_id, es_jugado):
    try:
        # Pausa súper corta, al ser "celular" el servidor confía más
        time.sleep(0.5) 
        
        # Petición a Capa 2 usando nuestro pasaporte de Android
        resp = requests.get(
            URL_API_DETALLE, 
            params={"matchId": match_id}, 
            headers=HEADERS_MOBILE,
            timeout=15
        )
        
        if resp.status_code != 200: 
            print(f"      [Error de red (Capa 2): Status {resp.status_code}]")
            return

        try:
            data = resp.json()
        except:
            print("      [Error: Cloudflare nos envió un Captcha en lugar del JSON]")
            return

        if not data: return 

        estadio_nombre = None
        
        try: estadio_nombre = data.get("general", {}).get("venue", {}).get("name")
        except: pass
        
        if not estadio_nombre:
            try:
                stadium_node = data.get("content", {}).get("matchFacts", {}).get("infoBox", {}).get("Stadium")
                if isinstance(stadium_node, dict): estadio_nombre = stadium_node.get("name")
                elif isinstance(stadium_node, str): estadio_nombre = stadium_node
            except: pass
        
        if not estadio_nombre:
            def rastrear_estadio(nodo):
                nonlocal estadio_nombre
                if isinstance(nodo, dict):
                    for k, v in nodo.items():
                        if k.lower() in ['venue', 'stadium']:
                            if isinstance(v, dict) and not estadio_nombre:
                                estadio_nombre = v.get('name') or v.get('text')
                            elif isinstance(v, str) and not estadio_nombre:
                                estadio_nombre = v
                        if k == 'title' and v == 'Stadium' and not estadio_nombre:
                            estadio_nombre = nodo.get('name') or nodo.get('text')
                    if not estadio_nombre:
                        for v in nodo.values(): rastrear_estadio(v)
                elif isinstance(nodo, list):
                    for item in nodo:
                        if not estadio_nombre: rastrear_estadio(item)
            rastrear_estadio(data)
        
        if estadio_nombre:
            print(f"   🏟️ Cancha: {estadio_nombre}")
        else:
            print(f"   🏟️ Cancha: A definir / No informado por API")

        if es_jugado:
            content = data.get("content") or {}
            match_facts = content.get("matchFacts") or {}
            events_obj = match_facts.get("events") or {}
            
            if isinstance(events_obj, list): events = events_obj
            else: events = events_obj.get("events", [])

            hubo_goles = False
            for ev in events:
                if not isinstance(ev, dict): continue
                
                tipo = ev.get("type")
                if tipo in ["Goal", "PenaltyGoal", "OwnGoal"]:
                    hubo_goles = True
                    minuto = ev.get("time", 0)
                    
                    p_obj = ev.get("player") or {}
                    if isinstance(p_obj, dict): jugador = p_obj.get("name", "Desconocido")
                    else: jugador = "Desconocido"
                    
                    es_local = ev.get("isHome", False)
                    tag = "(L)" if es_local else "(V)"
                    
                    extra = ""
                    if tipo == "PenaltyGoal": extra = " (Penal)"
                    if tipo == "OwnGoal": extra = " (En contra)"
                    
                    print(f"      ⚽ {minuto}' {jugador}{extra} {tag}")
            
            if not hubo_goles:
                print("      (0-0)")

    except Exception as e:
        print(f"      [Error recuperando Capa 2: {e}]")

def main():
    jugados, futuros = buscar_partidos()
    
    if not jugados and not futuros:
        print("\n❌ No se encontraron partidos tras escanear 2023-2026.")
        return

    ultimos_5 = jugados[:15]
    proximos_5 = futuros[:10]
    
    print(f"\n✅ Se encontraron {len(jugados)} partidos jugados y {len(futuros)} por jugar.")
    
    if ultimos_5:
        print(f"\n📊 Detalle de los últimos {len(ultimos_5)} partidos JUGADOS:\n")
        for match in ultimos_5:
            match_id = match.get('id')
            if not match_id: continue
            
            torneo = match.get("torneo_nombre") or match.get("tournament", {}).get("name") or match.get("league", {}).get("name", "Torneo")
            home = match.get("home", {}).get("name", "Local")
            away = match.get("away", {}).get("name", "Visita")
            score = match.get("status", {}).get("scoreStr", "-")
            
            id_home = match.get("home", {}).get("id")
            es_neutral = match.get("neutralGround", False) or match.get("status", {}).get("neutralGround", False) or match.get("general", {}).get("neutralGround", False)
            
            if es_neutral: condicion = "Neutral"
            elif id_home == ID_INDEPENDIENTE: condicion = "Local"
            else: condicion = "Visitante"
            
            fecha_raw = match.get("status", {}).get("utcTime", "")
            try:
                dt_utc = datetime.fromisoformat(fecha_raw.replace("Z", "+00:00"))
                dt_local = dt_utc.replace(tzinfo=None) - timedelta(hours=3)
                fecha_str = dt_local.strftime("%d/%m/%Y")
            except:
                fecha_str = fecha_raw.split("T")[0] if "T" in fecha_raw else fecha_raw

            print(f"📅 {fecha_str} | {home} vs {away} ({score})")
            print(f"   🏆 {torneo} | 📍 Administrativo: {condicion}")
            
            obtener_detalles_capa_2(match_id, es_jugado=True)
            print("-" * 50)

    if proximos_5:
        print(f"\n🔜 Detalle de los próximos {len(proximos_5)} partidos POR JUGAR:\n")
        for match in proximos_5:
            match_id = match.get('id')
            
            torneo = match.get("torneo_nombre") or match.get("tournament", {}).get("name") or match.get("league", {}).get("name", "Torneo")
            home = match.get("home", {}).get("name", "Local")
            away = match.get("away", {}).get("name", "Visita")
            
            id_home = match.get("home", {}).get("id")
            es_neutral = match.get("neutralGround", False) or match.get("status", {}).get("neutralGround", False) or match.get("general", {}).get("neutralGround", False)
            
            if es_neutral: condicion = "Neutral"
            elif id_home == ID_INDEPENDIENTE: condicion = "Local"
            else: condicion = "Visitante"
            
            fecha_raw = match.get("status", {}).get("utcTime", "")
            try:
                dt_utc = datetime.fromisoformat(fecha_raw.replace("Z", "+00:00"))
                dt_local = dt_utc.replace(tzinfo=None) - timedelta(hours=3)
                fecha_str = dt_local.strftime("%d/%m/%Y a las %H:%M hs")
            except:
                fecha_str = fecha_raw.split("T")[0] if "T" in fecha_raw else fecha_raw

            print(f"📅 {fecha_str} | {home} vs {away}")
            print(f"   🏆 {torneo} | 📍 Administrativo: {condicion}")
            
            if match_id:
                obtener_detalles_capa_2(match_id, es_jugado=False)
            print("-" * 50)

if __name__ == "__main__":
    main()