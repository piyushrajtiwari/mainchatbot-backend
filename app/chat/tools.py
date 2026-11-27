from math import isfinite

import requests
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException
from langchain_core.tools import tool

from app.core.settings import settings


class ProviderError(Exception):
    """The upstream provider was unavailable or returned unusable data."""


def _get_json(url, params, timeout):
    try:
        response = requests.get(url, params=params, timeout=timeout, allow_redirects=False)
        response.raise_for_status()
        if not 200 <= response.status_code < 300:
            raise ProviderError
        return response.json()
    except (requests.RequestException, ValueError):
        # Provider exceptions can contain request URLs, credentials, and response bodies.
        raise ProviderError from None


def _provider_object(data):
    if not isinstance(data, dict) or data.get("error"):
        raise ProviderError
    return data


def _number(value):
    return type(value) is int or isinstance(value, float) and isfinite(value)


def _text(value, fallback="Unavailable"):
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _get_coordinates(city: str):
    """City name to lat/lon using Open-Meteo Geocoding"""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city, "count": 1, "language": "en", "format": "json"}
    data = _provider_object(_get_json(url, params, 10))
    if "results" not in data and _number(data.get("generationtime_ms")):
        return None
    results = data.get("results")
    if not isinstance(results, list):
        raise ProviderError
    if not results:
        return None
    place = _provider_object(results[0])
    latitude, longitude = place.get("latitude"), place.get("longitude")
    name = _text(place.get("name"), "")
    if not name or not (_number(latitude) and -90 <= latitude <= 90
                        and _number(longitude) and -180 <= longitude <= 180):
        raise ProviderError
    return latitude, longitude, name, _text(place.get("country"), "")


WEATHER_CODES = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Light snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall", 77: "Snow grains",
    80: "Light rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Light snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with light hail",
    97: "Heavy thunderstorm", 99: "Thunderstorm with heavy hail",
}

WEATHER_METRICS = {
    "temperature_2m": "°C",
    "apparent_temperature": "°C",
    "relative_humidity_2m": "%",
    "wind_speed_10m": " km/h",
    "precipitation": " mm",
}


def _get_current_weather(latitude, longitude):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join((*WEATHER_METRICS, "weather_code")),
        "timezone": "auto",
    }
    data = _provider_object(_get_json(url, params, 10))
    current = _provider_object(data.get("current"))
    metrics = {}
    for field, unit in WEATHER_METRICS.items():
        value = current.get(field)
        if value is not None and not _number(value):
            raise ProviderError
        metrics[field] = "Unavailable" if value is None else f"{value}{unit}"

    code = current.get("weather_code")
    if code is not None and type(code) is not int:
        raise ProviderError
    if code is None and all(value == "Unavailable" for value in metrics.values()):
        raise ProviderError
    return WEATHER_CODES.get(code, "Unknown"), metrics

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

def _get_airport_observation(icao_code: str):
    """Return optional METAR context for the departure airport."""
    url = "https://aviationweather.gov/api/data/metar"
    try:
        data = _get_json(url, {"ids": icao_code, "format": "json"}, 10)
        if isinstance(data, list) and data:
            return _text(_provider_object(data[0]).get("rawOb"), "")
    except ProviderError:
        pass
    return ""

@tool
def get_weather(city: str) -> str:
    """
    Get current weather for any city in India or worldwide.
    Use this when user asks: "Delhi me mausam kaisa hai?", "Weather in Mumbai?"

    Args:
        city: City name like "Delhi", "Mumbai", "Bangalore"
    """
    try:
        coords = _get_coordinates(city)
        if coords is None:
            return f"City '{city}' not found. Please try another city name."
        latitude, longitude, name, country = coords
        condition, metrics = _get_current_weather(latitude, longitude)
    except ProviderError:
        return "Current weather is unavailable. Please try again."

    location = f"{name}, {country}" if country else name
    return (
        f"Weather in {location}:\n"
        f"Condition: {condition}\n"
        f"Temperature: {metrics['temperature_2m']} (Feels like {metrics['apparent_temperature']})\n"
        f"Humidity: {metrics['relative_humidity_2m']}\n"
        f"Wind: {metrics['wind_speed_10m']}\n"
        f"Precipitation: {metrics['precipitation']}\n"
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
            results = ddgs.text(query, max_results=5)
        if not isinstance(results, list) or any(not isinstance(row, dict) for row in results):
            raise ProviderError
    except (DuckDuckGoSearchException, ProviderError):
        return "Web search is unavailable. Please try again."

    if not results:
        return f"No results found for '{query}'."

    output = [f"Search results for '{query}':"]
    for index, result in enumerate(results, 1):
        title = _text(result.get("title"), "")
        body = _text(result.get("body"), "")
        href = _text(result.get("href"), "")
        output.append(f"{index}. {title}\n   {body}\n   Source: {href}")
    return "\n\n".join(output)

@tool
def get_flight_delay_prediction(flight_iata: str) -> str:
    """Look up an airline flight's reported departure status, timing, and delay.

    For supported Indian departure airports, include the current airport weather
    as context. Weather alone cannot establish why the flight was delayed.

    Args:
        flight_iata: Flight number like "6E2017", "AI202", "SG123"
    """
    flight_iata = "".join(flight_iata.upper().split())
    params = {"access_key": settings.AVIATIONSTACK_KEY, "flight_iata": flight_iata}
    try:
        payload = _provider_object(_get_json("https://api.aviationstack.com/v1/flights", params, 15))
        flights = payload.get("data")
        if not isinstance(flights, list):
            raise ProviderError
        if not flights:
            return f"Flight {flight_iata} not found. Please check the flight number."

        flight = _provider_object(flights[0])
        departure = _provider_object(flight.get("departure"))
        arrival = _provider_object(flight.get("arrival", {}))
        airline = _provider_object(flight.get("airline", {}))
        flight_info = _provider_object(flight.get("flight", {}))
        status = _text(flight.get("flight_status"), "").lower()
        delay = departure.get("delay")
        if not status or (delay is not None and type(delay) is not int):
            raise ProviderError
    except ProviderError:
        return "Flight status is unavailable. Please try again."

    departure_iata = _text(departure.get("iata"), "")
    departure_airport = _text(departure.get("airport"), departure_iata or "Unknown airport")
    arrival_airport = _text(arrival.get("airport"), _text(arrival.get("iata"), "Unknown airport"))
    flight_number = _text(flight_info.get("iata"), flight_iata)
    airline_name = _text(airline.get("name"), "")
    result = [
        f"Flight: {flight_number} {airline_name}".rstrip(),
        f"Route: {departure_airport} → {arrival_airport}",
        f"Status: {status}",
        f"Scheduled departure: {_text(departure.get('scheduled'))}",
        f"Estimated departure: {_text(departure.get('estimated'))}",
    ]
    if status == "cancelled":
        result.append("The provider reports this flight was cancelled. Confirm with the airline.")
    elif delay is None:
        result.append("Departure delay: Unknown. The provider did not report a delay value.")
    elif delay == 0:
        result.append("Departure delay: 0 minutes reported (on time).")
    elif delay < 0:
        result.append(f"Departure timing: {abs(delay)} minutes early according to the provider.")
    else:
        result.append(f"Departure delay: {delay} minutes reported.")
        result.append("Delay reason: Unconfirmed. Check with the airline for the cause.")

    icao = AIRPORT_ICAO.get(departure_iata)
    if icao and status != "cancelled":
        observation = _get_airport_observation(icao)
        if observation:
            result.append(f"Current departure airport weather (METAR): {observation}")
    return "\n".join(result)

all_tools = [get_weather, search_web, get_flight_delay_prediction]
