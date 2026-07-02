"""
Session Engine (Killzones / Macro Sessions)

Kurumsal hacim belirli saat pencerelerinde yoğunlaşır (UTC):

    ASIA          00:00 - 06:00  -> düşük volatilite, genelde birikim
    LONDON_KZ     07:00 - 10:00  -> Londra killzone
    NY_AM_KZ      12:00 - 15:00  -> New York AM killzone (en likit pencere)
    LONDON_CLOSE  15:00 - 17:00  -> Londra kapanış dönüş penceresi
    OFF_HOURS     diğer saatler  -> killzone dışı, sinyal güvenilirliği düşer

Tarama başına bir kez hesaplanır ve Atlas Score'a şeffaf bir
bonus/ceza olarak eklenir. Zaman UTC'dir; yerel saat kullanılmaz.
"""

from datetime import datetime, timezone


KILLZONES = [
    {
        "name": "LONDON_KZ",
        "start_hour": 7,
        "end_hour": 10,
        "bonus": 5,
        "note": "Londra killzone — kurumsal hacim penceresi",
    },
    {
        "name": "NY_AM_KZ",
        "start_hour": 12,
        "end_hour": 15,
        "bonus": 5,
        "note": "New York AM killzone — en likit pencere",
    },
    {
        "name": "LONDON_CLOSE",
        "start_hour": 15,
        "end_hour": 17,
        "bonus": 2,
        "note": "Londra kapanışı — dönüş/devam penceresi",
    },
    {
        "name": "ASIA",
        "start_hour": 0,
        "end_hour": 6,
        "bonus": 0,
        "note": "Asya seansı — düşük volatilite, range eğilimi",
    },
]

OFF_HOURS_PENALTY = -3
OFF_HOURS_NOTE = "Killzone dışı saat — sinyal güvenilirliği düşük"


def get_session_context(now=None):
    """
    Şu anki (veya verilen) UTC zamana göre seans bağlamını döndürür.

    Dönüş:
        session_name   : aktif pencere adı (OFF_HOURS dahil)
        in_killzone    : yüksek öncelikli pencerede miyiz
        session_bonus  : Atlas Score'a eklenecek puan (negatif olabilir)
        session_reason : açıklama
        utc_hour       : değerlendirilen saat
    """
    if now is None:
        now = datetime.now(timezone.utc)

    hour = now.hour

    for zone in KILLZONES:
        if zone["start_hour"] <= hour < zone["end_hour"]:
            return {
                "session_name": zone["name"],
                "in_killzone": zone["bonus"] > 0,
                "session_bonus": zone["bonus"],
                "session_reason": zone["note"],
                "utc_hour": hour,
            }

    return {
        "session_name": "OFF_HOURS",
        "in_killzone": False,
        "session_bonus": OFF_HOURS_PENALTY,
        "session_reason": OFF_HOURS_NOTE,
        "utc_hour": hour,
    }
