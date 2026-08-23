@echo off
echo === TESTANDO APIs DIRETAS USDT/BRL ===
echo.
echo --- Binance ---
curl -s "https://api.binance.com/api/v3/ticker/price?symbol=USDTBRL"
echo.
echo.
echo --- Bybit ---
curl -s "https://api.bybit.com/v5/market/tickers?category=spot&symbol=USDTBRL"
echo.
echo.
echo --- OKX (ccxt funciona) ---
echo okx funciona via ccxt
echo.
echo --- Bitget (ccxt funciona) ---
echo bitget funciona via ccxt
echo.
echo --- MercadoBitcoin ---
curl -s "https://api.mercadobitcoin.net/api/v4/tickers?symbol=USDT-BRL"
echo.
echo.
pause