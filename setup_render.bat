@echo off
echo Adicionando chaves API no Render...
echo.

curl -s -X PUT "https://api.render.com/v1/services/srv-da51frbbc2fs73fhaek0/env-vars/BINANCE_API_KEY" -H "Authorization: Bearer rnd_wyivsCOxDi2njuzPGBjjA3In7ZeY" -H "Content-Type: application/json" -d "{\"value\":\"HIWvdNXyUmkDjGIqVujwkGEklkfztETmXLWIiJpOCjV80GjITFo9fvy8MEnFu5vB\"}"
echo.

curl -s -X PUT "https://api.render.com/v1/services/srv-da51frbbc2fs73fhaek0/env-vars/BINANCE_SECRET_KEY" -H "Authorization: Bearer rnd_wyivsCOxDi2njuzPGBjjA3In7ZeY" -H "Content-Type: application/json" -d "{\"value\":\"L3BGUtqUUFACQ7R3eFv1e8YO6FmAHBD5makaNt3MUnq1vnvtdQolf7v4YAcyPeFJ\"}"
echo.

curl -s -X PUT "https://api.render.com/v1/services/srv-da51frbbc2fs73fhaek0/env-vars/BITGET_API_KEY" -H "Authorization: Bearer rnd_wyivsCOxDi2njuzPGBjjA3In7ZeY" -H "Content-Type: application/json" -d "{\"value\":\"bg_f6e6e91c270bae5dada159f64fc2eb18\"}"
echo.

curl -s -X PUT "https://api.render.com/v1/services/srv-da51frbbc2fs73fhaek0/env-vars/BITGET_SECRET_KEY" -H "Authorization: Bearer rnd_wyivsCOxDi2njuzPGBjjA3In7ZeY" -H "Content-Type: application/json" -d "{\"value\":\"95da49454e3beb531955df67477d184d4c8b2f313a54966e9c6ce55ec3bd103a\"}"
echo.

curl -s -X PUT "https://api.render.com/v1/services/srv-da51frbbc2fs73fhaek0/env-vars/BITGET_PASSPHRASE" -H "Authorization: Bearer rnd_wyivsCOxDi2njuzPGBjjA3In7ZeY" -H "Content-Type: application/json" -d "{\"value\":\"\"}"
echo.

echo.
echo DONE!
pause