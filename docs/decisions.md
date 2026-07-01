# Decisions

## Atlas Score V2

MQS = 20%  
Trend = 25%  
Setup = 30%  
SMC = 25%

## Hard Filter

- MarketCap
- USD Volume
- Spread
- Funding
- OI
- ATR
- OrderBook

## Trend Engine

Trend engine 1D, 4H ve 1H verileri üzerinden çalışır.

Kullanılan ana yapı:

- EMA20
- EMA50
- Momentum
- Multi-timeframe trend uyumu

## Setup Engine

Setup durumları:

- READY
- WATCH
- WAIT

Setup engine trend yönü, SMC yapısı, entry bölgesi, stop, target ve RR değerlerini birlikte değerlendirir.

Trend ile SMC yapısı çelişirse setup `WAIT_STRUCTURE_CONFLICT` olur.

## SMC V5

SMC motoru modüler hale getirildi.

Ana klasör:

```text
strategy/smc/