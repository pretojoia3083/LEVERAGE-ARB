@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "fix: fetch_direct binance e bybit com parsing correto, remover exchanges sem USDT/BRL"
git push origin master:main --force
echo DONE
pause