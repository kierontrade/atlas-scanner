# ATLAS — SMC Trade Intelligence Engine

BingX USDT futures piyasasını (805 parite) kurumsal SMC/ICT mantığıyla tarar,
sadece yüksek confluence'lı fırsatları READY olarak işaretler ve BingX'e
elle girilebilecek hazır işlem planı üretir.

Emir göndermez — sinyal ve plan üretir, işlemi sen girersin (demo veya gerçek).

## Kurulum

```
pip install -r requirements.txt
```

## Kullanım

Tek tarama:

```
python main.py
```

Sürekli mod (demo test için önerilen — 15 dakikada bir tarar, yeni READY
çıkınca sesli uyarı verir):

```
python main.py --loop
```

Windows'ta Türkçe karakter sorunu yaşarsan:

```
set PYTHONIOENCODING=utf-8
python main.py --loop
```

## Demo trading akışı

1. `config/settings.py` içinde `ACCOUNT_BALANCE_USDT` değerini BingX demo
   bakiyenle eşitle (`RISK_PER_TRADE` varsayılan %1).
2. `python main.py --loop` ile botu çalışır bırak.
3. 🟢 READY trade card'ı geldiğinde karttaki Entry / Stop Loss / TP
   seviyelerini ve miktarı BingX demo hesabına limit emir olarak gir.
4. Karttaki "Zamanlama" satırına dikkat et — "sweep bekleniyor" diyorsa
   girme, "Sniper entry koşulları aktif" diyorsa plan geçerli.
5. Bot her READY setup'ı journal'a kaydeder ve sonraki taramalarda TP/SL
   sonucunu otomatik etiketler — senin demo sonuçlarınla karşılaştır.

## Pipeline

```
805 futures → likidite/market cap filtresi → hard filters
→ Market Quality → Trend → SMC (BOS/CHOCH/OB/FVG/IFVG/BPR/likidite)
→ MTF (1D/4H/1H/15M) → Entry Sequence (sweep→displacement→CISD/MSS→zone)
→ Setup (entry/stop/TP/RR) → Derivatives (funding/OI/CVD) → Session (killzone)
→ Atlas Score → READY / WATCH / WAIT → Trade Card + Journal
```

## Çıktılar

| Dosya | İçerik |
|---|---|
| `reports/atlas_report.txt` | Tam analiz raporu (her aday, tüm gerekçeler) |
| `data/atlas_ready.json` | READY setuplar + işlem planları |
| `data/atlas_journal.db` | Tarama geçmişi, OI geçmişi, TP/SL sonuçları |
| `logs/atlas.log` | Hata ve çalışma logları |

## Performans takibi

Journal'da biriken gerçek başarı oranları:

```
python -c "from storage import journal; print(journal.get_outcome_stats())"
```

## Testler

```
python test_offline_engines.py
```
