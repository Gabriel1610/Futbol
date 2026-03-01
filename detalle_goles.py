import requests
import json
from datetime import datetime, timedelta

# --- CONFIGURACIÓN ---
ID_INDEPENDIENTE = 10078
ID_LIGA_PROFESIONAL = 10128
ID_COPA_LIGA = 10315

# URLs
URL_API_TEAMS = "https://www.fotmob.com/api/teams"
URL_API_LEAGUES = "https://www.fotmob.com/api/leagues"
URL_API_DETALLE = "https://www.fotmob.com/api/matchDetails"

# HEADERS 
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

def buscar_partidos():
    """
    Busca partidos del historial y próximos a jugar.
    Separa los resultados en dos listas distintas.
    """
    print("🔍 Iniciando búsqueda de historial y próximos partidos...")
    
    jugados = []
    futuros = []
    
    # 1. Intentamos primero con la API de Equipos (Trae tanto pasados como futuros)
    try:
        resp = requests.get(URL_API_TEAMS, headers=HEADERS, params={"id": ID_INDEPENDIENTE, "ccode3": "ARG"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                fixtures = data.get("fixtures") or {}
                
                # Buscamos en todas las listas posibles
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
                            # Verificar que sea de Independiente
                            hid = m.get("home", {}).get("id")
                            aid = m.get("away", {}).get("id")
                            
                            if hid == ID_INDEPENDIENTE or aid == ID_INDEPENDIENTE:
                                status = m.get("status", {})
                                finished = status.get("finished", False)
                                cancelled = status.get("cancelled", False)
                                
                                if cancelled: continue
                                
                                # Separar jugados de futuros sin duplicados
                                if finished:
                                    if not any(p['id'] == m['id'] for p in jugados):
                                        jugados.append(m)
                                else:
                                    if not any(p['id'] == m['id'] for p in futuros):
                                        futuros.append(m)
    except Exception as e:
        print(f"   [!] Error en carga standard: {e}")

    # 2. Si no encontramos suficientes jugados, buscamos en el archivo histórico
    if len(jugados) < 5:
        anios_a_buscar = ["2025", "2024", "2023"]
        torneos = [
            (ID_LIGA_PROFESIONAL, "Liga Profesional"), 
            (ID_COPA_LIGA, "Copa de la Liga")
        ]
        
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
                    resp = requests.get(URL_API_LEAGUES, headers=HEADERS, params=params, timeout=10)
                    
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

    # Ordenar jugados (descendente, el más reciente arriba)
    jugados.sort(key=lambda x: x.get("status", {}).get("utcTime", ""), reverse=True)
    # Ordenar futuros (ascendente, el más próximo arriba)
    futuros.sort(key=lambda x: x.get("status", {}).get("utcTime", ""), reverse=False)
    
    return jugados, futuros

def obtener_detalle_goles(match_id):
    """Consulta el endpoint de detalle para sacar minuto y autor."""
    try:
        resp = requests.get(URL_API_DETALLE, headers=HEADERS, params={"matchId": match_id}, timeout=10)
        if resp.status_code != 200: return

        data = resp.json()
        if not data: return 

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
        print(f"      [Error recuperando goles: {e}]")

def main():
    jugados, futuros = buscar_partidos()
    
    if not jugados and not futuros:
        print("\n❌ No se encontraron partidos tras escanear 2023-2026.")
        return

    # Tomar los últimos 5 y los próximos 5
    ultimos_5 = jugados[:10]
    proximos_5 = futuros[:10]
    
    print(f"\n✅ Se encontraron {len(jugados)} partidos jugados y {len(futuros)} por jugar.")
    
    # --- 1. MOSTRAR JUGADOS ---
    if ultimos_5:
        print(f"\n📊 Detalle de los últimos {len(ultimos_5)} partidos JUGADOS:\n")
        
        for match in ultimos_5:
            match_id = match.get('id')
            if not match_id: continue
            
            torneo = match.get("torneo_nombre") or match.get("tournament", {}).get("name") or match.get("league", {}).get("name", "Torneo")
            home = match.get("home", {}).get("name", "Local")
            away = match.get("away", {}).get("name", "Visita")
            score = match.get("status", {}).get("scoreStr", "-")
            
            # Fecha procesada
            fecha_raw = match.get("status", {}).get("utcTime", "")
            try:
                dt_utc = datetime.fromisoformat(fecha_raw.replace("Z", "+00:00"))
                dt_local = dt_utc.replace(tzinfo=None) - timedelta(hours=3)
                fecha_str = dt_local.strftime("%d/%m/%Y")
            except:
                fecha_str = fecha_raw.split("T")[0] if "T" in fecha_raw else fecha_raw

            print(f"📅 {fecha_str} | {home} vs {away} ({score})")
            print(f"   🏆 {torneo}")
            
            obtener_detalle_goles(match_id)
            print("-" * 50)

    # --- 2. MOSTRAR PRÓXIMOS ---
    if proximos_5:
        print(f"\n🔜 Detalle de los próximos {len(proximos_5)} partidos POR JUGAR:\n")
        
        for match in proximos_5:
            torneo = match.get("torneo_nombre") or match.get("tournament", {}).get("name") or match.get("league", {}).get("name", "Torneo")
            home = match.get("home", {}).get("name", "Local")
            away = match.get("away", {}).get("name", "Visita")
            
            # Fecha procesada al horario de Argentina con la Hora incluida
            fecha_raw = match.get("status", {}).get("utcTime", "")
            try:
                dt_utc = datetime.fromisoformat(fecha_raw.replace("Z", "+00:00"))
                dt_local = dt_utc.replace(tzinfo=None) - timedelta(hours=3)
                fecha_str = dt_local.strftime("%d/%m/%Y a las %H:%M hs")
            except:
                fecha_str = fecha_raw.split("T")[0] if "T" in fecha_raw else fecha_raw

            print(f"📅 {fecha_str} | {home} vs {away}")
            print(f"   🏆 {torneo}")
            print("-" * 50)

if __name__ == "__main__":
    main()