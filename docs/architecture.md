# ATLAS Architecture

## Amaç

Kurumsal seviyede çalışan Futures Trading Scanner.

## Akış

CoinGecko
↓

MarketCap Filter
↓

BingX Futures

↓

Market Metrics

Funding

Spread

Open Interest

ATR

OrderBook Depth

↓

Hard Filter

↓

Market Quality Score

↓

Trend Engine

↓

SMC Engine

↓

Setup Engine

↓

Atlas Score

↓

READY / WATCH / WAIT

↓

Report

## Modüller

scanner/

API katmanı

scoring/

MQS

Hard Filter

Atlas Score

strategy/

Trend

SMC

Setup

reports/

TXT Report

JSON Export

data/

Scanner çıktıları

## Status

READY

WATCH_NEAR

WATCH

WAIT

## Trend

BULLISH

BEARISH

NEUTRAL

## Trade

LONG

SHORT
