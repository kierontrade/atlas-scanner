from scoring.market_metrics import get_market_metrics


symbol = "BTC-USDT"

metrics = get_market_metrics(symbol)

print(metrics)