import os
import requests
from langchain_core.tools import tool
from app.core.settings import settings
from duckduckgo_search import DDGS


def _get_coordinates(city: str):
    """City name to lat/lon using Open-Meteo Geocoding"""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    res = requests.get(url, params={"name": city, "count": 1, "language": "en", "format": "json"}, timeout=10)
    data = res.json()
    if not data.get("results"):
        return None
    r = data["results"][0]
    return r["latitude"], r["longitude"], r["name"], r.get("country", "")

AIRPORT_ICAO = {
    "DEL": "VIDP",  # Delhi
    "BOM": "VABB",  # Mumbai
    "BLR": "VOBL",  # Bangalore
    "HYD": "VOHS",  # Hyderabad
    "MAA": "VOMM",  # Chennai
    "CCU": "VECC",  # Kolkata
    "AMD": "VAAH",  # Ahmedabad
    "PNQ": "VAPO",  # Pune
    "GOI": "VOGO",  # Goa
    "JAI": "VIJP",  # Jaipur
}

def _get_weather_reason(icao_code: str):
    """Fetch live METAR weather for an airport."""
    try:
        url = f"https://aviationweather.gov/api/data/metar?ids={icao_code}&format=json"
        res = requests.get(url, timeout=10)
        data = res.json()

        if not data:
            return None

        metar = data[0]
        return {
            "raw": metar.get("rawOb", ""),
            "visibility_km": metar.get("visib", 10),
            "weather": metar.get("wxString", ""),
            "temp": metar.get("temp"),
            "wind_speed": metar.get("wspd"),
        }
    except Exception:
        return None

@tool
def get_weather(city: str) -> str:
    """
    Get current weather for any city in India or worldwide.
    Use this when user asks: "Delhi me mausam kaisa hai?", "Weather in Mumbai?"

    Args:
        city: City name like "Delhi", "Mumbai", "Bangalore"
    """
    coords = _get_coordinates(city)
    if not coords:
        return f"City '{city}' not found. Please try another city name."

    lat, lon, name, country = coords

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
        "timezone": "auto",
    }
    res = requests.get(url, params=params, timeout=10)
    data = res.json()
    cur = data.get("current", {})

    # Weather code to readable text
    code_map = {
        0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
        45: "Fog", 48: "Fog", 51: "Light Drizzle", 61: "Light Rain",
        63: "Moderate Rain", 65: "Heavy Rain", 71: "Light Snow",
        80: "Light Rain Showers", 95: "Thunderstorm", 99: "Thunderstorm with Hail"
    }
    condition = code_map.get(cur.get("weather_code"), "Unknown")

    return (
        f"\n Weather in {name}, {country}:\n"
        f"Condition: {condition}\n"
        f"Temperature: {cur.get('temperature_2m')}°C (Feels like {cur.get('apparent_temperature')}°C)\n"
        f"Humidity: {cur.get('relative_humidity_2m')}%\n"
        f"Wind: {cur.get('wind_speed_10m')} km/h\n"
        f"Rain: {cur.get('precipitation')} mm\n"
    )


@tool
def search_web(query: str) -> str:
    """
    Search the web for current news, latest information, or any general question.
    Use this when user asks about news, current events, or something you don't know.
    Use this when get_weather or get_flight_delay_prediction cannot answer.

    Args:
        query: Search query like "India vs Australia match result", "latest iPhone price in India"
    """
    try:
        with DDGS() as ddgs:
            # Get top 5 results
            results = list(ddgs.text(query, max_results=5))

        if not results:
            return f"No results found for '{query}'."

        output = f"\n🔍 Search results for '{query}':\n\n"
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            output += f"{i}. {title}\n   {body}\n   Source: {href}\n\n"

        return output

    except Exception as e:
        return f"Search failed: {e}"

@tool
def get_flight_delay_prediction(flight_iata: str) -> str:
    """
    Get delay status and reason for any Indian flight.
    Use this when user asks: "Why is 6E2017 late?", "How much delay for AI202?", "When will my flight arrive?"

    Args:
        flight_iata: Flight number like "6E2017", "AI202", "SG123"
    """
    # 1. Get flight status from AviationStack
    try:
        params = {
            "access_key": settings.AVIATIONSTACK_KEY,
            "flight_iata": flight_iata.upper().replace(" ", ""),
        }
        res = requests.get(
            "http://api.aviationstack.com/v1/flights", params=params, timeout=15
        )
        data = res.json()
    except Exception as e:
        return f"Flight API error: {e}"

    if not data.get("data"):
        return f"Flight {flight_iata} not found. Please enter a valid flight number like 6E2017."

    flight = data["data"][0]

    dep = flight.get("departure", {})
    arr = flight.get("arrival", {})
    airline = flight.get("airline", {}).get("name", "")
    flight_no = flight.get("flight", {}).get("iata", flight_iata)

    dep_airport = dep.get("airport", "")
    dep_iata = dep.get("iata", "")
    arr_airport = arr.get("airport", "")
    arr_iata = arr.get("iata", "")

    delay = dep.get("delay") or 0  # in minutes
    status = flight.get("flight_status", "unknown")
    scheduled = dep.get("scheduled", "")
    estimated = dep.get("estimated", "")

    # 2. Get departure airport weather
    icao = AIRPORT_ICAO.get(dep_iata, "")
    weather = _get_weather_reason(icao) if icao else None

    # 3. Build response
    result = f"\n✈️ Flight: {airline} {flight_no}\n"
    result += f"Route: {dep_airport} ({dep_iata}) -> {arr_airport} ({arr_iata})\n"
    result += f"Status: {status}\n"
    result += f"Scheduled: {scheduled}\n"
    result += f"Estimated: {estimated}\n\n"

    if status == "cancelled":
        return result + "❌ Flight has been CANCELLED. Please contact the airline."

    if delay == 0 and status in ["scheduled", "active"]:
        result += "✅ Flight is ON-TIME, no delay."
        if weather:
            result += f"\nWeather: {weather['raw']}"
        return result

    # Delay exists, find the reason
    result += f"⏰ Delay: {delay} minutes late.\n\n"
    result += "📌 Reason:\n"

    # Reason 1: Fog - Low visibility
    if weather and weather["visibility_km"] is not None and weather["visibility_km"] < 1:
        result += f"- FOG at {dep_airport}. Visibility is only {weather['visibility_km']} km.\n"
        result += "- Flight is delayed due to fog.\n"
        result += f"- Live METAR: {weather['raw']}\n"

    # Reason 2: Rain / Thunderstorm
    elif weather and ("RA" in weather["weather"] or "TS" in weather["weather"]):
        result += f"- Rain / Thunderstorm at {dep_airport}.\n"
        result += f"- Weather: {weather['weather']}\n"
        result += f"- Live METAR: {weather['raw']}\n"

    # Reason 3: High Wind
    elif weather and weather["wind_speed"] and weather["wind_speed"] > 25:
        result += f"- High wind at {dep_airport} ({weather['wind_speed']} knots).\n"
        result += "- ATC has kept the flight on hold for safety.\n"

    # Reason 4: Rotational Delay - Late incoming aircraft
    else:
        result += "- Weather is clear.\n"
        result += "- Delay is likely due to late arrival of incoming aircraft (Rotational Delay).\n"
        result += "- The aircraft assigned to this flight arrived late from its previous destination.\n"

    return result

all_tools = [get_weather, search_web, get_flight_delay_prediction]