@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "fix: usar metodos internos ccxt pra binance e bybit direto"
git push origin master:main --force
echo DONE
pause